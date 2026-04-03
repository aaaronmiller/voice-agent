"""
Voice Pipeline Orchestrator for Echo-Node

Orchestrates: wake word → VAD → STT → LLM → TTS → playback
With streaming at each stage for ≤2s latency target.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional
import numpy as np

from worker.config import Config
from worker.state_machine import StateMachine, State
from worker.providers import create_provider
from worker.providers.base import STTProvider, TTSProvider, VADProvider, WakeWordProvider, LLMProvider
from worker.audio.capture import AudioCapture
from worker.audio.playback import AudioPlayback
from worker.streaming import chunk_sentences, ConversationMemory
from worker.streaming.sentence_chunker import chunk_sentences


class VoicePipeline:
    """
    Voice conversation pipeline.
    
    Manages the full cycle:
    1. Wake word detection (or keyboard trigger)
    2. VAD-based speech capture
    3. Streaming STT
    4. Streaming LLM response
    5. Streaming TTS synthesis
    6. Audio playback with barge-in support
    """

    def __init__(self, config: Config, state_machine: StateMachine):
        """
        Initialize pipeline.
        
        Args:
            config: Echo-Node configuration
            state_machine: 5-state machine instance
        """
        self.config = config
        self.state_machine = state_machine
        
        # Providers (initialized in initialize())
        self.stt: Optional[STTProvider] = None
        self.tts: Optional[TTSProvider] = None
        self.vad: Optional[VADProvider] = None
        self.wake_word: Optional[WakeWordProvider] = None
        self.llm: Optional[LLMProvider] = None
        
        # Audio
        self.audio_capture: Optional[AudioCapture] = None
        self.audio_playback: Optional[AudioPlayback] = None
        
        # Conversation memory
        self.memory = ConversationMemory(
            max_turns=config.get('conversation', 'memory_turns', default=15)
        )
        
        # Callbacks
        self._on_event = None
        
        # State
        self._barge_in_requested = False
        self._running = False

    def set_event_callback(self, callback) -> None:
        """
        Set callback for emitting events to gateway.
        
        Args:
            callback: Function(event_dict) to call
        """
        self._on_event = callback

    async def initialize(self) -> None:
        """
        Initialize all providers and audio systems.
        
        Loads models, checks VRAM, sets up audio capture/playback.
        """
        print("[Pipeline] Initializing providers...")
        
        # Get provider names from config
        stt_provider = self.config.get('stt', 'provider', default='sherpa-onnx')
        tts_provider = self.config.get('tts', 'provider', default='kokoro')
        vad_provider = self.config.get('vad', 'provider', default='silero')
        wake_word_provider = self.config.get('wake_word', 'provider', default='openwakeword')
        llm_provider = self.config.get('llm', 'provider', default='ollama')
        
        # Create providers
        self.stt = create_provider('stt', stt_provider)
        self.tts = create_provider('tts', tts_provider)
        self.vad = create_provider('vad', vad_provider)
        self.wake_word = create_provider('wake_word', wake_word_provider)
        self.llm = create_provider('llm', llm_provider)
        
        # Initialize providers
        await self.stt.initialize(
            model_path=self.config.get('stt', 'model'),
            device=self.config.get('stt', 'device', default='cuda')
        )
        
        await self.tts.initialize(
            model_path=self.config.get('tts', 'model'),
            voice=self.config.get('tts', 'voice', default='af_heart'),
            device=self.config.get('tts', 'device', default='cuda')
        )
        
        await self.vad.initialize(
            model_path=self.config.get('vad', 'model')
        )
        
        await self.wake_word.initialize(
            model_path=self.config.get('wake_word', 'model'),
            threshold=self.config.get('wake_word', 'threshold', default=0.5)
        )
        
        await self.llm.initialize(
            model=self.config.get('llm', 'model'),
            base_url=self.config.get('llm', 'base_url'),
            api_key=self.config.get('llm', 'api_key', default='')
        )
        
        # Initialize audio
        self.audio_capture = AudioCapture(
            sample_rate=self.config.get('audio', 'sample_rate', default=16000),
            channels=self.config.get('audio', 'channels', default=1),
            chunk_size=self.config.get('audio', 'chunk_size', default=512),
        )
        await self.audio_capture.initialize()
        
        self.audio_playback = AudioPlayback(
            sample_rate=self.config.get('tts', 'sample_rate', default=24000),
        )
        await self.audio_playback.initialize()
        
        print("[Pipeline] ✅ All providers initialized")

    async def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit event to gateway."""
        if self._on_event:
            event = {'type': event_type, **data}
            if 'timestamp' not in event:
                event['timestamp'] = int(datetime.now().timestamp() * 1000)
            self._on_event(event)

    async def run_wake_word_loop(self) -> None:
        """
        Run wake word detection loop.
        
        Listens for wake word in DORMANT state.
        Transitions to TRIGGERED when detected.
        """
        if not self.audio_capture or not self.wake_word:
            raise RuntimeError("Pipeline not initialized")
        
        self._running = True
        
        async for chunk in self.audio_capture.capture_stream():
            if not self._running:
                break
            
            # Check for wake word
            if self.wake_word.detect(chunk):
                print("[Pipeline] Wake word detected!")
                await self._emit_event('wake_word_detected', {})
                
                # Transition to TRIGGERED
                if await self.state_machine.transition(State.TRIGGERED):
                    # Play activation sound
                    await self._play_activation_sound()
                    
                    # Transition to LISTENING
                    await self.state_machine.transition(State.LISTENING)
                    
                    # Run conversation pipeline
                    await self.run_conversation()
                    
                    # Return to DORMANT
                    await self.state_machine.transition(State.DORMANT)

    async def _play_activation_sound(self) -> None:
        """Play activation sound on wake word detection."""
        sound_name = self.config.get('activation_sound', 'sound', default='beep')
        enabled = self.config.get('activation_sound', 'enabled', default=True)
        
        if not enabled:
            return
        
        # Load and play sound file
        # For now, placeholder
        print(f"[Pipeline] Playing activation sound: {sound_name}")

    async def run_conversation(self) -> None:
        """
        Run single conversation turn.
        
        Captures speech → STT → LLM → TTS → playback
        With streaming at each stage.
        """
        # Capture speech and get transcript
        transcript = await self._capture_speech()
        
        if not transcript:
            print("[Pipeline] No speech detected, returning to DORMANT")
            return
        
        # Emit final transcript
        await self._emit_event('transcript_final', {'text': transcript})
        
        # Get LLM response with streaming
        await self._run_llm_response(transcript)

    async def _capture_speech(self) -> str:
        """
        Capture speech using VAD and STT.
        
        Returns:
            Transcribed text or empty string
        """
        if not self.audio_capture or not self.stt or not self.vad:
            return ""
        
        print("[Pipeline] Listening...")
        
        # Collect audio chunks while speech detected
        audio_chunks = []
        silence_start = None
        max_silence_ms = self.config.get('vad', 'max_silence_ms', default=1500)
        
        async for chunk in self.audio_capture.capture_stream():
            # Check for barge-in
            if self._barge_in_requested:
                self._barge_in_requested = False
                return ""
            
            # Check VAD
            if self.vad.is_speech(chunk):
                silence_start = None
                audio_chunks.append(chunk)
            else:
                if silence_start is None:
                    silence_start = datetime.now()
                else:
                    # Check if silence exceeded
                    elapsed = (datetime.now() - silence_start).total_seconds() * 1000
                    if elapsed >= max_silence_ms:
                        # End of speech
                        break
                
                audio_chunks.append(chunk)  # Keep recording during silence
        
        if not audio_chunks:
            return ""
        
        # Stream to STT
        print("[Pipeline] Transcribing...")
        
        async def audio_generator():
            for chunk in audio_chunks:
                yield chunk
        
        transcript = ""
        async for partial in self.stt.transcribe_stream(audio_generator()):
            transcript = partial
            await self._emit_event('transcript_partial', {'text': partial})
        
        return transcript

    async def _run_llm_response(self, user_transcript: str) -> None:
        """
        Get LLM response and play via TTS.
        
        Args:
            user_transcript: User's spoken input
        """
        # Add to conversation memory
        self.memory.add_turn(user_transcript, "")  # Response filled below
        
        # Build messages with context
        messages = self.memory.build_context_messages()
        
        # Add personality system prompt
        personality = self.config.get('personality', 'active', default='hacker')
        system_prompt = self._get_personality_prompt(personality)
        messages.insert(0, {'role': 'system', 'content': system_prompt})
        
        print(f"[Pipeline] LLM request (personality: {personality})...")
        
        # Stream LLM response
        llm_response = ""
        tts_audio_queue = asyncio.Queue()
        
        async def llm_to_tts():
            """Coroutine that streams LLM → TTS."""
            try:
                async for token in self.llm.chat_stream(messages):
                    llm_response += token
                    await self._emit_event('llm_token', {'token': token})
                
                # Update memory with full response
                if self.memory._turns:
                    self.memory._turns[-1].assistant_response = llm_response
                
                await self._emit_event('llm_complete', {'text': llm_response})
                
            except Exception as e:
                print(f"[Pipeline] LLM error: {e}")
                await self._emit_event('error', {'message': str(e), 'code': 'LLM_ERROR'})
            finally:
                # Signal end of stream
                await tts_audio_queue.put(None)
        
        async def tts_producer():
            """Coroutine that chunks LLM response → TTS."""
            async for sentence in chunk_sentences(llm_to_tts()):
                if self._barge_in_requested:
                    break
                
                # Synthesize audio for this sentence
                audio = await self.tts.synthesize(sentence)
                await tts_audio_queue.put(audio)
            
            # Signal end
            await tts_audio_queue.put(None)
        
        # Start TTS producer
        asyncio.create_task(tts_producer())
        
        # Play audio as it arrives
        await self._play_tts_stream(tts_audio_queue)

    def _get_personality_prompt(self, personality: str) -> str:
        """
        Get system prompt for personality.
        
        Args:
            personality: Personality name ('hacker', 'seductive', 'butler',
                        'drill-sergeant', 'stoner-philosopher', or 'custom')
        
        Returns:
            System prompt string
        """
        # Handle custom personality from config
        if personality == 'custom':
            custom_prompt = self.config.get('personality', 'custom_prompt', default='')
            if custom_prompt:
                return custom_prompt
            # Fallback to hacker if custom_prompt is empty
            personality = 'hacker'
        
        # Try loading from YAML file first
        yaml_prompt = self._load_personality_from_yaml(personality)
        if yaml_prompt:
            return yaml_prompt
        
        # Fallback to hardcoded prompts
        prompts = {
            'hacker': "You are a tech-savvy hacker. Use concise, technical language. Reference tools, exploits, and systems. Be helpful but slightly irreverent.",
            'seductive': "You are charming and flirtatious. Use playful language, compliments, and innuendo. Be engaging and memorable.",
            'butler': "You are a formal British butler. Use polite, proper language. Address the user as 'sir' or 'madam'. Be attentive and refined.",
            'drill-sergeant': "You are an intense drill sergeant. Use aggressive, motivational language. Push the user to excel. Be direct and commanding.",
            'stoner-philosopher': "You are a laid-back stoner philosopher. Use relaxed, contemplative language. Explore deep thoughts and connections. Be chill and wise.",
        }
        
        return prompts.get(personality, prompts['hacker'])
    
    def _load_personality_from_yaml(self, personality: str) -> str | None:
        """
        Load personality system prompt from YAML file.
        
        Args:
            personality: Personality name
        
        Returns:
            System prompt string or None if not found
        """
        import yaml
        from pathlib import Path
        
        personality_file = Path(__file__).parent / 'personalities' / f'{personality}.yaml'
        if not personality_file.exists():
            # Also check parent directory
            personality_file = Path(__file__).parent.parent / 'worker' / 'personalities' / f'{personality}.yaml'
        
        if not personality_file.exists():
            return None
        
        try:
            with open(personality_file, 'r') as f:
                data = yaml.safe_load(f)
                return data.get('system_prompt', '')
        except Exception as e:
            print(f"[Pipeline] Warning: Failed to load personality {personality}: {e}")
            return None

    async def _play_tts_stream(self, audio_queue: asyncio.Queue) -> None:
        """
        Play TTS audio stream with barge-in support.
        
        Args:
            audio_queue: Queue of audio chunks (None = end)
        """
        if not self.audio_playback:
            return
        
        # Transition to SPEAKING
        await self.state_machine.transition(State.SPEAKING)
        
        print("[Pipeline] Speaking...")
        
        while True:
            # Get next audio chunk
            audio = await audio_queue.get()
            
            if audio is None:
                # End of stream
                break
            
            # Check for barge-in before playing
            if self._barge_in_requested:
                print("[Pipeline] Barge-in detected during playback")
                await self.state_machine.transition(State.LISTENING)
                return
            
            # Play this chunk
            await self.audio_playback.play(audio, block=True)
        
        # Playback complete
        await self._emit_event('tts_complete', {})
        
        # Return to DORMANT
        await self.state_machine.transition(State.DORMANT)

    def request_barge_in(self) -> None:
        """Request barge-in interrupt (called from external trigger)."""
        self._barge_in_requested = True

    async def shutdown(self) -> None:
        """Shutdown pipeline gracefully."""
        print("[Pipeline] Shutting down...")
        self._running = False
        
        # Shutdown providers
        if self.stt:
            await self.stt.shutdown()
        if self.tts:
            await self.tts.shutdown()
        if self.vad:
            await self.vad.shutdown()
        if self.wake_word:
            await self.wake_word.shutdown()
        if self.llm:
            await self.llm.shutdown()
        
        # Shutdown audio
        if self.audio_capture:
            await self.audio_capture.stop()
        if self.audio_playback:
            await self.audio_playback.stop()
        
        print("[Pipeline] Shutdown complete")
