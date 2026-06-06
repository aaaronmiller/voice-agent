---
date: 2026-03-28 20:55:00 PST
ver: 1.0.0
author: Sliither
model: claude-opus-4-6
tags: [voice-ai, agent-zero, corrections, implementation-plan, parakeet, kokoro, talkinghead, echo-cancellation]
---
# Corrective Instructions for Voice AI Implementation

## Context for Agent Zero

You are building a dual-mode voice AI interface (web UI + standalone CLI) for an RTX 4050 (6GB VRAM) on Fedora 43, with secondary targets of WSL2 and macOS. The user has an existing PRD audit from Claude that identified critical issues. Your previous response contained several errors that need correction before writing any code.

---

## Critical Corrections

### 1. Use Real Import Paths (Not Hallucinated Ones)

Your pseudocode used fake imports. Here are the actual packages and their real APIs:

**Parakeet STT** (via NeMo):
```python
# Install: pip install nemo_toolkit['asr']
import nemo.collections.asr as nemo_asr
model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v3")
transcription = model.transcribe(["audio.wav"])
```

OR use the FastAPI wrapper (simpler):
```bash
# Clone: https://github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai
# Provides OpenAI-compatible /v1/audio/transcriptions endpoint
```

**Kokoro TTS**:
```python
# Install: pip install kokoro>=0.9.2
# Also: apt-get install espeak-ng
from kokoro import KPipeline
pipeline = KPipeline(lang_code='a')  # 'a' = American English
generator = pipeline("Hello world", voice='af_heart')
for i, (gs, ps, audio) in enumerate(generator):
    # audio is a numpy array at 24000 Hz sample rate
    sf.write(f'{i}.wav', audio, 24000)
```

**OpenWakeWord**:
```python
# Install: pip install openwakeword
from openwakeword.model import Model
oww_model = Model(wakeword_models=["path/to/model.onnx"])
# or leave empty for all pre-trained models
prediction = oww_model.predict(audio_frame)  # 16-bit 16kHz PCM
```

### 2. Implement Streaming TTS (Not Sequential Pipeline)

Your pipeline is: STT -> LLM (wait for complete response) -> TTS -> Play.
This creates 2-5 second latency. Instead, implement sentence-boundary chunking:

```
LLM token stream -> sentence detector -> TTS queue -> audio playback
                                              |
                                    (each sentence synthesized
                                     while next is still generating)
```

Implementation pattern:
```python
import re

async def stream_llm_to_tts(llm_stream, tts_pipeline, audio_queue):
    buffer = ""
    sentence_end = re.compile(r'[.!?]\s')
    
    async for token in llm_stream:
        buffer += token
        # Check for sentence boundary
        match = sentence_end.search(buffer)
        if match:
            sentence = buffer[:match.end()]
            buffer = buffer[match.end():]
            # Synthesize this sentence while LLM keeps generating
            audio = tts_pipeline(sentence, voice='af_heart')
            for _, _, chunk in audio:
                await audio_queue.put(chunk)
    
    # Handle remaining buffer
    if buffer.strip():
        audio = tts_pipeline(buffer, voice='af_heart')
        for _, _, chunk in audio:
            await audio_queue.put(chunk)
```

### 3. Add Echo Cancellation (MANDATORY)

Without AEC, the microphone captures TTS output and creates feedback. This is the hardest problem in the pipeline. Two approaches:

**Option A: Hardware separation** (simplest)
- Use headphones. Microphone doesn't pick up TTS output.
- Fine for development, not for hands-free speaker operation.

**Option B: Software AEC via SpeexDSP**
```python
# Install: pip install speexdsp-ns
# Or build from: https://github.com/nickleus27/speexdsp-python
from speexdsp import EchoCanceller
ec = EchoCanceller.create(frame_size=160, filter_length=1024)
# Feed TTS output as reference, mic input as capture
cleaned = ec.process(mic_frame, speaker_frame)
```

**Option C: Mute mic during TTS playback** (pragmatic MVP)
```python
# Simple but effective for MVP
is_speaking = False

async def play_tts(audio):
    global is_speaking
    is_speaking = True
    play_audio(audio)
    is_speaking = False

async def record_audio():
    if is_speaking:
        return None  # Skip recording during TTS
    return capture_mic()
```

For MVP, use Option C. Add Option B in Phase 2.

### 4. Use TalkingHead for Avatar (Don't Build Custom)

TalkingHead (https://github.com/met4citizen/TalkingHead) provides everything needed:
- VRM avatar loading and rendering
- Real-time lip-sync from audio streams (built-in viseme generation)
- Idle animations (blinking, breathing, head tracking)
- AI-controllable gestures via function calling
- MIT licensed, browser-native

Integration approach for Agent Zero web UI:
```javascript
import { TalkingHead } from './talkinghead.mjs';

const head = new TalkingHead(container, {
    ttsEndpoint: 'http://localhost:8765/speak',  // Your Kokoro endpoint
    sttEndpoint: 'http://localhost:8765/transcribe',  // Your Parakeet endpoint
});

// Load VRM model
await head.showAvatar({ url: '/avatars/default.vrm' });

// Speak with lip-sync (audio + visemes handled automatically)
await head.speakAudio(audioBlob);

// Idle animations run automatically
```

Design the audio worker's WebSocket events to include viseme data from Kokoro's timing output so TalkingHead can sync lips precisely.

### 5. Web UI: Stream Kokoro Audio, NOT Web Speech API

Do NOT use `window.speechSynthesis` (Web Speech API). It sounds robotic and defeats the purpose of running Kokoro locally.

Instead, stream Kokoro-generated audio via WebSocket to the browser:
```javascript
// Frontend: receive and play Kokoro audio chunks
const ws = new WebSocket('ws://localhost:8765/audio-stream');
const audioContext = new AudioContext({ sampleRate: 24000 });

ws.onmessage = async (event) => {
    const audioData = await event.data.arrayBuffer();
    const buffer = audioContext.createBuffer(1, audioData.byteLength / 2, 24000);
    // Decode PCM16 and play
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.start();
};
```

### 6. WSL2 Audio: Explicit Implementation

WSL2 audio requires specific handling:

**For WSLg (Windows 11):** PipeWire is available automatically. Microphone input works but with ~50ms added latency. Use:
```bash
# Verify audio devices are visible
pactl list sources short
# If not, ensure WSLg is enabled in .wslconfig
```

**For older WSL2 (no WSLg):** Forward PulseAudio to Windows:
```bash
# In WSL2
export PULSE_SERVER=tcp:$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')
# On Windows, run PulseAudio server with network module
```

**Known issue:** WSL2 microphone input adds 50-200ms latency depending on the audio backend. For time-critical wake word detection, consider running OpenWakeWord on the Windows side and forwarding triggers to WSL2 via named pipe or localhost socket.

### 7. CLI Mode: Use systemd on Linux, launchd on Mac

**Fedora 43 (systemd):**
```ini
# /etc/systemd/user/voice-assistant.service
[Unit]
Description=Voice AI Assistant
After=pipewire.service

[Service]
ExecStart=/usr/bin/python3 /path/to/voice_worker.py --mode=standalone
Restart=always
Environment=CUDA_VISIBLE_DEVICES=0

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable voice-assistant
systemctl --user start voice-assistant
```

**macOS (launchd):**
```xml
<!-- ~/Library/LaunchAgents/com.user.voice-assistant.plist -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.voice-assistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/voice_worker.py</string>
        <string>--mode=standalone</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

### 8. VRAM Budget for RTX 4050 (6GB)

Stick to this allocation:
- Parakeet TDT 0.6B: ~1.5GB VRAM (or run on CPU at 30x real-time)
- Kokoro-82M: ~0.3GB VRAM (tiny model)
- OpenWakeWord: CPU only (ONNX, negligible)
- Silero VAD: CPU only (ONNX, negligible)
- Remaining ~4GB: Available for Ollama if running local LLM

Do NOT attempt to run Orpheus TTS (3B params) or Chatterbox (0.5B) alongside Parakeet on 6GB VRAM. Kokoro-82M is the correct choice for this hardware.

If you want higher quality TTS, run Parakeet on CPU (it achieves 30x real-time on CPU anyway) and use the full 6GB for Chatterbox-Turbo (350M params).

### 9. Hermes Agent Integration (If Applicable)

Do NOT use HTTP webhooks. Hermes Agent v0.3.0 has a gateway WebSocket. Register as a platform:
```python
# Connect to Hermes gateway
import websockets

async def hermes_channel():
    async with websockets.connect("ws://127.0.0.1:{HERMES_PORT}") as ws:
        # Register as voice channel
        await ws.send(json.dumps({
            "type": "register_channel",
            "channel": "voice",
            "capabilities": ["stt", "tts", "wake_word"]
        }))
        # Bidirectional message flow
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "response":
                await tts_speak(data["text"])
```

### 10. Implementation Order

**Phase 1 (MVP, 1-2 days):**
- Python audio worker: mic capture -> Silero VAD silence detection -> Parakeet STT -> return text
- Global hotkey trigger via `pynput` (Ctrl+Alt+V)
- Kokoro TTS audio playback via system audio
- Mic mute during TTS (echo prevention Option C)
- CLI mode only, no web UI yet
- Connect to Agent Zero via its REST API for LLM responses

**Phase 2 (Web Integration, 2-3 days):**
- WebSocket server in audio worker for browser connection
- Agent Zero frontend: add mic button that streams to audio worker
- Stream Kokoro audio back to browser via WebSocket
- Add streaming TTS (sentence-boundary chunking from LLM stream)

**Phase 3 (Wake Word + Polish, 1-2 days):**
- Add OpenWakeWord for hands-free activation
- Add wake word confirmation chime to reduce false positives
- Platform-specific daemon (systemd/launchd)
- WSL2 audio testing and fixes

**Phase 4 (Avatar, when ready):**
- Integrate TalkingHead into Agent Zero web UI
- WebSocket viseme events from audio worker
- VRM model selection UI

---

## What NOT To Do

- Do NOT use `window.speechSynthesis` for TTS output. Use Kokoro streamed audio.
- Do NOT build custom Three.js/VRM avatar code. Use TalkingHead library.
- Do NOT use FastAPI for the audio worker if the gateway already handles HTTP. Use a lightweight WebSocket server (`websockets` library).
- Do NOT hallucinate import paths. Test every import before writing implementation code.
- Do NOT ignore echo cancellation. At minimum, mute mic during TTS playback.
- Do NOT try to run >2GB TTS models alongside Parakeet on 6GB VRAM.