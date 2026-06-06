# Echo-Node Provider Guide

**How to add new STT, TTS, VAD, Wake Word, and LLM providers to Echo-Node**

---

## Table of Contents

1. [Overview: Provider Architecture](#1-overview-provider-architecture)
2. [Adding a New STT Provider](#2-adding-a-new-stt-provider)
3. [Adding a New TTS Provider](#3-adding-a-new-tts-provider)
4. [Adding a New LLM Provider](#4-adding-a-new-llm-provider)
5. [Adding a New VAD Provider](#5-adding-a-new-vad-provider)
6. [Adding a New Wake Word Provider](#6-adding-a-new-wake-word-provider)
7. [Registering Providers in `__init__.py`](#7-registering-providers-in-__init__py)
8. [Updating `config.example.yaml`](#8-updating-configexamleyaml)
9. [Testing Provider Switching](#9-testing-provider-switching)
10. [VRAM Estimation Guidelines](#10-vram-estimation-guidelines)

---

## 1. Overview: Provider Architecture

Echo-Node uses a **pluggable provider architecture** based on abstract base classes (ABCs). Each pipeline component (STT, TTS, VAD, Wake Word, LLM) has a corresponding ABC that defines the interface all providers must implement.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    config.yaml                               │
│  stt.provider: sherpa-onnx | faster-whisper | your-provider │
│  tts.provider: kokoro | piper | your-provider               │
│  llm.provider: ollama | openai-compat | your-provider       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              worker/providers/__init__.py                    │
│                    PROVIDER_REGISTRY                         │
│  Factory: create_provider(category, name) → ProviderInstance │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              worker/providers/base.py                        │
│  Abstract Base Classes (ABCs):                               │
│  - STTProvider                                               │
│  - TTSProvider                                               │
│  - VADProvider                                               │
│  - WakeWordProvider                                          │
│  - LLMProvider                                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┼────────────┬────────────┬──────────┐
          ▼            ▼            ▼            ▼          ▼
   ┌──────────┐  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
   │ sherpa   │  │ kokoro   │ │ silero   │ │ open-  │ │ ollama   │
   │ stt      │  │ tts      │ │ vad      │ │ wakew  │ │ llm      │
   └──────────┘  └──────────┘ └──────────┘ └────────┘ └──────────┘
   YourProvider  YourProvider             YourProvider
```

### Key Principles

1. **No code changes for switching** — Change `config.yaml`, restart, done
2. **Provider ABCs are contracts** — Implement all abstract methods
3. **VRAM-aware** — Every provider reports its VRAM requirement
4. **Streaming-first** — Providers support streaming where applicable
5. **Graceful degradation** — Fallback to CPU if CUDA unavailable

### Base Classes Reference (`worker/providers/base.py`)

| Provider Type | Abstract Methods | Key Properties |
|---------------|------------------|----------------|
| `STTProvider` | `initialize()`, `transcribe_stream()`, `shutdown()` | `vram_requirement_mb` |
| `TTSProvider` | `initialize()`, `synthesize()`, `synthesize_stream()`, `shutdown()` | `vram_requirement_mb` |
| `VADProvider` | `initialize()`, `is_speech()`, `shutdown()` | `vram_requirement_mb` |
| `WakeWordProvider` | `initialize()`, `detect()`, `shutdown()` | `vram_requirement_mb` |
| `LLMProvider` | `initialize()`, `chat_stream()`, `shutdown()` | `vram_requirement_mb` |

---

## 2. Adding a New STT Provider

**Example:** Adding a hypothetical "VibeVoice" STT provider

### Step 1: Create the Provider File

Create `worker/providers/stt/vibevoice_stt.py`:

```python
"""
VibeVoice ASR Provider

High-accuracy automatic speech recognition.
Supports streaming transcription with partial results.
"""

import asyncio
from typing import AsyncIterator
import numpy as np

try:
    import vibevoice  # Hypothetical package
    VIBEVOICE_AVAILABLE = True
except ImportError:
    VIBEVOICE_AVAILABLE = False

from worker.providers.base import STTProvider


class VibeVoiceSTT(STTProvider):
    """
    VibeVoice streaming STT provider.

    Features:
    - Streaming partial transcripts
    - Multi-language support
    - Low latency (~300ms)
    """

    def __init__(self):
        self._model = None
        self._language = "en"
        self._vram_mb = 0
        self._sample_rate = 16000

    @property
    def vram_requirement_mb(self) -> int:
        """
        Estimated VRAM requirement.

        Returns:
            VRAM in MB (varies by model)
        """
        return self._vram_mb if self._vram_mb > 0 else 2048  # Default 2GB

    async def initialize(self, model_path: str = "", device: str = "cuda") -> None:
        """
        Initialize VibeVoice model.

        Args:
            model_path: Path to model directory or model name
            device: 'cuda', 'cpu', or 'openvino'
        """
        if not VIBEVOICE_AVAILABLE:
            raise ImportError(
                "vibevoice not installed. Install with:\n"
                "  pip install vibevoice-asr"
            )

        # Load model
        # self._model = vibevoice.load_model(
        #     model_path or "vibevoice-base",
        #     device=device
        # )

        # Estimate VRAM
        if device == "cuda":
            self._vram_mb = 2048  # ~2GB for base model
        else:
            self._vram_mb = 0

        print(f"[VibeVoiceSTT] Initialized with device: {device}")

    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]:
        """
        Stream audio chunks, yield partial transcripts.

        Args:
            audio_chunks: Async iterator of audio chunks (float32, 16kHz)

        Yields:
            Partial transcript strings
        """
        if not self._model:
            raise RuntimeError("STT not initialized. Call initialize() first.")

        # Create stream object (provider-specific)
        # stream = self._model.create_stream()

        async for chunk in audio_chunks:
            # Ensure correct format
            if chunk.dtype != np.float32:
                chunk = chunk.astype(np.float32)

            # Feed audio to stream
            # stream.accept_waveform(self._sample_rate, chunk)

            # Get partial transcript
            # partial = stream.get_partial_text()
            # if partial:
            #     yield partial

            # Placeholder for template
            yield "[partial transcript]"

        # Finalize and yield final transcript
        # final = stream.finalize()
        # if final:
        #     yield final

    async def shutdown(self) -> None:
        """Release resources."""
        self._model = None
        print("[VibeVoiceSTT] Shutdown complete")
```

### Step 2: Implement Required Methods

| Method | Purpose | Key Considerations |
|--------|---------|-------------------|
| `__init__()` | Initialize instance variables | Set `_vram_mb`, `_sample_rate`, provider-specific state |
| `vram_requirement_mb` | Report VRAM needs | Return accurate estimate based on model size |
| `initialize()` | Load model into memory | Handle CUDA/CPU/OpenVINO backends, validate installation |
| `transcribe_stream()` | Process audio, yield text | Accept `AsyncIterator[np.ndarray]`, yield strings |
| `shutdown()` | Release resources | Set model to `None`, close sessions |

### Step 3: Handle Dependencies

Add to `worker/requirements.txt`:

```txt
# STT Providers
sherpa-onnx>=1.9.0
faster-whisper>=1.0.0
vibevoice-asr>=0.5.0  # Your new provider
```

---

## 3. Adding a New TTS Provider

**Example:** Adding "Chatterbox" TTS provider

### Step 1: Create the Provider File

Create `worker/providers/tts/chatterbox_tts.py`:

```python
"""
Chatterbox-Turbo TTS Provider

High-quality, low-latency text-to-speech.
Beats ElevenLabs in blind tests, sub-200ms latency.
"""

import asyncio
from typing import AsyncIterator
import numpy as np

try:
    from chatterbox import ChatterboxTTS as ChatterboxModel
    CHATTERBOX_AVAILABLE = True
except ImportError:
    CHATTERBOX_AVAILABLE = False

from worker.providers.base import TTSProvider


class ChatterboxTTS(TTSProvider):
    """
    Chatterbox-Turbo TTS provider.

    Features:
    - Sub-200ms first-token latency
    - High naturalness (MOS 4.2+)
    - Multiple voices
    - Emotion control
    """

    def __init__(self):
        self._model = None
        self._voice = "default"
        self._vram_mb = 0
        self._sample_rate = 24000
        self._emotion = "neutral"

    @property
    def vram_requirement_mb(self) -> int:
        """
        Estimated VRAM requirement.

        Returns:
            VRAM in MB (~3GB for Chatterbox-Turbo)
        """
        return self._vram_mb if self._vram_mb > 0 else 3072

    async def initialize(
        self,
        model_path: str = "",
        voice: str = "default",
        device: str = "cuda",
        emotion: str = "neutral"
    ) -> None:
        """
        Initialize Chatterbox model.

        Args:
            model_path: Path to model or HuggingFace repo
            voice: Voice preset
            device: 'cuda' or 'cpu'
            emotion: Emotion preset (neutral, happy, sad, angry)
        """
        if not CHATTERBOX_AVAILABLE:
            raise ImportError(
                "chatterbox-turbo not installed. Install with:\n"
                "  pip install chatterbox-turbo"
            )

        self._voice = voice
        self._emotion = emotion

        # Load model
        # self._model = ChatterboxModel(
        #     model_path or "chatterbox-turbo",
        #     device=device
        # )

        # Estimate VRAM
        if device == "cuda":
            self._vram_mb = 3072  # ~3GB
        else:
            self._vram_mb = 0

        print(f"[ChatterboxTTS] Initialized: voice={voice}, device={device}, emotion={emotion}")

    async def synthesize(self, text: str) -> np.ndarray:
        """
        Synthesize full text to audio array.

        Args:
            text: Text to synthesize

        Returns:
            Audio array (float32, 24kHz mono, -1.0 to 1.0)
        """
        if not self._model and CHATTERBOX_AVAILABLE:
            raise RuntimeError("TTS not initialized. Call initialize() first.")

        # Synthesize
        # audio = self._model.synthesize(
        #     text,
        #     voice=self._voice,
        #     emotion=self._emotion
        # )
        # return audio.astype(np.float32)

        # Placeholder
        duration = max(0.5, len(text) * 0.08)
        samples = int(self._sample_rate * duration)
        return np.zeros(samples, dtype=np.float32)

    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        """
        Stream audio chunks as they're generated.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunks (float32, 24kHz)
        """
        # Chatterbox supports sentence-boundary streaming
        # sentences = self._split_sentences(text)
        #
        # for sentence in sentences:
        #     chunk = await self.synthesize(sentence)
        #     yield chunk

        # Placeholder: synthesize full and chunk it
        full_audio = await self.synthesize(text)
        chunk_size = int(self._sample_rate * 0.05)  # 50ms chunks

        for i in range(0, len(full_audio), chunk_size):
            chunk = full_audio[i:i + chunk_size]
            if len(chunk) > 0:
                yield chunk

    async def shutdown(self) -> None:
        """Release resources."""
        self._model = None
        print("[ChatterboxTTS] Shutdown complete")
```

### Step 2: Implement Required Methods

| Method | Purpose | Key Considerations |
|--------|---------|-------------------|
| `__init__()` | Initialize instance | Set voice, emotion, `_sample_rate` (usually 24kHz) |
| `vram_requirement_mb` | Report VRAM | Chatterbox-Turbo ~3GB, Kokoro ~512MB |
| `initialize()` | Load model | Accept `voice`, `emotion`, `device` params |
| `synthesize()` | Full text → audio | Return `np.ndarray` float32, -1.0 to 1.0 |
| `synthesize_stream()` | Stream audio chunks | Yield 50-100ms chunks for low-latency playback |
| `shutdown()` | Cleanup | Release model, close sessions |

---

## 4. Adding a New LLM Provider

**Example:** Adding "Anthropic Claude" direct API provider

### Step 1: Create the Provider File

Create `worker/providers/llm/anthropic_llm.py`:

```python
"""
Anthropic Claude LLM Provider

Direct integration with Anthropic Claude API.
Supports streaming, tool use, and multi-turn conversation.
"""

import asyncio
from typing import AsyncIterator
import aiohttp
import json

from worker.providers.base import LLMProvider


class AnthropicLLM(LLMProvider):
    """
    Anthropic Claude LLM provider.

    Features:
    - Streaming responses
    - Tool use (function calling)
    - 200K context window
    - Vision support (optional)
    """

    def __init__(self):
        self._api_key = ""
        self._model = "claude-sonnet-4-20250514"
        self._base_url = "https://api.anthropic.com/v1"
        self._session: aiohttp.ClientSession | None = None
        self._vram_mb = 0  # Cloud API

    @property
    def vram_requirement_mb(self) -> int:
        """
        VRAM requirement for cloud API.

        Returns:
            0 (inference happens on Anthropic's servers)
        """
        return 0

    async def initialize(
        self,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com/v1",
        api_key: str = ""
    ) -> None:
        """
        Initialize Anthropic client.

        Args:
            model: Model name (e.g., "claude-sonnet-4-20250514", "claude-opus-4-20250514")
            base_url: API base URL (default: Anthropic API)
            api_key: Anthropic API key (required)
        """
        self._model = model
        self._base_url = base_url
        self._api_key = api_key

        if not self._api_key:
            raise ValueError("Anthropic API key is required")

        # Create HTTP session with Anthropic headers
        self._session = aiohttp.ClientSession(
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        )

        print(f"[AnthropicLLM] Initialized with model: {self._model}")

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        """
        Stream response tokens from Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'
                     Note: Anthropic uses 'user'/'assistant', not 'user'/'ai'
            tools: Optional list of tool definitions

        Yields:
            Response tokens (strings)
        """
        if not self._session:
            raise RuntimeError("LLM not initialized. Call initialize() first.")

        # Convert messages to Anthropic format
        anthropic_messages = self._convert_messages(messages)

        # Build request
        payload = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": 1024,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools

        # Stream request
        async with self._session.post(
            f"{self._base_url}/messages",
            json=payload
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"Anthropic error: {resp.status} - {error_text}")

            # Read streaming response (SSE format)
            async for line in resp.content:
                line = line.decode('utf-8').strip()

                if not line:
                    continue

                # Parse SSE: "data: {...}"
                if line.startswith("data: "):
                    data_str = line[6:]

                    try:
                        event = json.loads(data_str)

                        # Extract content from delta
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield delta.get("text", "")

                        # Check for stream end
                        if event.get("type") == "message_stop":
                            break

                    except json.JSONDecodeError:
                        continue

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """
        Convert generic message format to Anthropic format.

        Anthropic requires:
        - 'role': 'user' or 'assistant' (not 'system' or 'ai')
        - 'content': string or list of content blocks
        """
        converted = []

        for msg in messages:
            role = msg["role"]

            # Map roles
            if role == "system":
                # Anthropic doesn't have system messages
                # Prepend to first user message
                continue
            elif role == "ai":
                role = "assistant"

            converted.append({
                "role": role,
                "content": msg["content"]
            })

        return converted

    async def shutdown(self) -> None:
        """Release resources."""
        if self._session:
            await self._session.close()
            self._session = None
        print("[AnthropicLLM] Shutdown complete")
```

### Step 2: Implement Required Methods

| Method | Purpose | Key Considerations |
|--------|---------|-------------------|
| `__init__()` | Initialize client | Set `_api_key`, `_model`, `_base_url` |
| `vram_requirement_mb` | Report VRAM | Cloud APIs return 0 |
| `initialize()` | Setup connection | Validate API key, create HTTP session |
| `chat_stream()` | Stream LLM response | Handle SSE parsing, yield tokens |
| `shutdown()` | Cleanup | Close HTTP session |

### LLM Provider Notes

1. **Message format**: Most LLMs use `{"role": "...", "content": "..."}`. Some (Anthropic) use different role names.
2. **Streaming**: Use `stream: true` in API requests for token-by-token streaming
3. **Tools**: Support optional `tools` parameter for function calling
4. **Error handling**: Always check HTTP status and parse error responses

---

## 5. Adding a New VAD Provider

**Example:** Adding "WebRTC" VAD provider

### Step 1: Create the Provider File

Create `worker/providers/vad/webrtc_vad.py`:

```python
"""
WebRTC VAD Provider

Voice Activity Detection using WebRTC VAD.
Ultra-lightweight, works on CPU, no GPU needed.
"""

import numpy as np

try:
    import webrtcvad
    WEBRTC_AVAILABLE = True
except ImportError:
    WEBRTC_AVAILABLE = False

from worker.providers.base import VADProvider


class WebRTCVAD(VADProvider):
    """
    WebRTC Voice Activity Detection.

    Features:
    - Ultra-lightweight (<1MB)
    - Real-time capable
    - CPU-only (no GPU needed)
    - Adjustable aggressiveness
    """

    def __init__(self):
        self._vad = None
        self._sample_rate = 16000
        self._frame_duration_ms = 30  # 10, 20, or 30ms
        self._aggressiveness = 2  # 0-3 (higher = more aggressive filtering)

    @property
    def vram_requirement_mb(self) -> int:
        """
        VRAM requirement.

        Returns:
            0 (WebRTC VAD runs on CPU)
        """
        return 0

    async def initialize(
        self,
        model_path: str = "",
        aggressiveness: int = 2
    ) -> None:
        """
        Initialize WebRTC VAD.

        Args:
            model_path: Unused (WebRTC VAD is built-in)
            aggressiveness: 0-3 (higher = more aggressive noise filtering)
        """
        if not WEBRTC_AVAILABLE:
            print("[WebRTCVAD] webrtcvad not installed, using the configured fallback")
            return

        self._aggressiveness = aggressiveness
        self._vad = webrtcvad.Vad(aggressiveness)

        print(f"[WebRTCVAD] Initialized with aggressiveness: {aggressiveness}")

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if audio chunk contains speech.

        Args:
            audio_chunk: Audio data (float32, 16kHz, 480 samples for 30ms)

        Returns:
            True if speech detected
        """
        if not self._vad:
            # Fallback: energy-based detection
            rms = np.sqrt(np.mean(audio_chunk ** 2))
            return rms > 0.02

        # Convert to bytes (WebRTC expects 16-bit PCM)
        audio_bytes = (audio_chunk * 32767).astype(np.int16).tobytes()

        # Run VAD
        try:
            return self._vad.is_speech(audio_bytes, self._sample_rate)
        except Exception:
            # Invalid frame size or other error
            return False

    async def shutdown(self) -> None:
        """Release resources."""
        self._vad = None
        print("[WebRTCVAD] Shutdown complete")
```

### VAD Provider Notes

| Method | Purpose | Key Considerations |
|--------|---------|-------------------|
| `is_speech()` | Detect speech in chunk | Input is 512 samples (32ms at 16kHz) |
| `vram_requirement_mb` | Report VRAM | Most VADs are CPU-only, return 0 |

---

## 6. Adding a New Wake Word Provider

**Example:** Adding "Porcupine" wake word provider

### Step 1: Create the Provider File

Create `worker/providers/wake_word/porcupine_wakeword.py`:

```python
"""
Porcupine Wake Word Provider

Custom wake word detection using Picovoice Porcupine.
Supports multiple wake words, low false positive rate.
"""

import numpy as np

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False

from worker.providers.base import WakeWordProvider


class PorcupineWakeWord(WakeWordProvider):
    """
    Porcupine wake word detection.

    Features:
    - Multiple wake word support
    - Low false positive rate
    - Real-time capable
    """

    def __init__(self):
        self._engine = None
        self._threshold = 0.5
        self._wake_words = ["hey google"]  # Default
        self._sample_rate = 16000

    @property
    def vram_requirement_mb(self) -> int:
        """
        VRAM requirement.

        Returns:
            0 (Porcupine runs on CPU)
        """
        return 0

    async def initialize(
        self,
        model_path: str = "",
        wake_words: list[str] | None = None,
        threshold: float = 0.5
    ) -> None:
        """
        Initialize Porcupine engine.

        Args:
            model_path: Unused (Porcupine uses built-in models)
            wake_words: List of wake words to detect
            threshold: Detection sensitivity (0.0-1.0)
        """
        if not PORCUPINE_AVAILABLE:
            print("[PorcupineWakeWord] pvporcupine not installed")
            return

        self._wake_words = wake_words or ["hey google"]
        self._threshold = threshold

        # Initialize Porcupine
        # self._engine = pvporcupine.create(
        #     keywords=self._wake_words,
        #     sensitivities=[self._threshold] * len(self._wake_words)
        # )

        print(f"[PorcupineWakeWord] Initialized with wake words: {self._wake_words}")

    def detect(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if wake word detected in chunk.

        Args:
            audio_chunk: Audio data (float32, 16kHz, 512 samples)

        Returns:
            True if wake word detected
        """
        if not self._engine:
            return False

        # Convert to 16-bit PCM
        audio_int16 = (audio_chunk * 32767).astype(np.int16)

        # Run detection
        # keyword_index = self._engine.process(audio_int16)
        # return keyword_index >= 0

        return False  # Placeholder

    async def shutdown(self) -> None:
        """Release resources."""
        self._engine = None
        print("[PorcupineWakeWord] Shutdown complete")
```

### Wake Word Provider Notes

| Method | Purpose | Key Considerations |
|--------|---------|-------------------|
| `detect()` | Check for wake word | Called every audio frame (~32ms) |
| `initialize()` | Load wake word model | Accept custom wake word list |

---

## 7. Registering Providers in `__init__.py`

After creating your provider file, register it in `worker/providers/__init__.py`:

```python
"""
Provider Registry for Echo-Node

All providers are registered here by category and name.
The factory function create_provider() instantiates providers by name.
"""

from worker.providers.base import STTProvider, TTSProvider, VADProvider, WakeWordProvider, LLMProvider

# Import provider implementations
from worker.providers.stt.sherpa_stt import SherpaSTT
from worker.providers.stt.faster_whisper_stt import FasterWhisperSTT
from worker.providers.stt.vibevoice_stt import VibeVoiceSTT  # NEW!

from worker.providers.tts.kokoro_tts import KokoroTTS
from worker.providers.tts.piper_tts import PiperTTS
from worker.providers.tts.chatterbox_tts import ChatterboxTTS  # NEW!

from worker.providers.vad.silero_vad import SileroVAD
from worker.providers.vad.webrtc_vad import WebRTCVAD  # NEW!

from worker.providers.wake_word.openwakeword import OpenWakeWordProvider
from worker.providers.wake_word.porcupine_wakeword import PorcupineWakeWord  # NEW!

from worker.providers.llm.ollama_llm import OllamaLLM
from worker.providers.llm.openai_compat_llm import OpenAICompatLLM
from worker.providers.llm.anthropic_llm import AnthropicLLM  # NEW!

# Provider registry - maps category + name to provider class
PROVIDER_REGISTRY: dict[str, dict[str, type]] = {
    "stt": {
        "sherpa-onnx": SherpaSTT,
        "faster-whisper": FasterWhisperSTT,
        "vibevoice-asr": VibeVoiceSTT,  # NEW!
    },
    "tts": {
        "kokoro": KokoroTTS,
        "piper": PiperTTS,
        "chatterbox": ChatterboxTTS,  # NEW!
    },
    "vad": {
        "silero": SileroVAD,
        "webrtc": WebRTCVAD,  # NEW!
    },
    "wake_word": {
        "openwakeword": OpenWakeWordProvider,
        "porcupine": PorcupineWakeWord,  # NEW!
    },
    "llm": {
        "ollama": OllamaLLM,
        "openai-compat": OpenAICompatLLM,
        "anthropic": AnthropicLLM,  # NEW!
    },
}


def create_provider(category: str, name: str) -> STTProvider | TTSProvider | VADProvider | WakeWordProvider | LLMProvider:
    """
    Factory: create a provider by category and name.

    Args:
        category: One of 'stt', 'tts', 'vad', 'wake_word', 'llm'
        name: Provider name (e.g., 'sherpa-onnx', 'kokoro')

    Returns:
        Provider instance implementing the appropriate ABC

    Raises:
        ValueError: If category or provider name is unknown
    """
    if category not in PROVIDER_REGISTRY:
        available = list(PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown provider category: {category}. Available: {available}")

    if name not in PROVIDER_REGISTRY[category]:
        available = list(PROVIDER_REGISTRY[category].keys())
        raise ValueError(f"Unknown {category} provider: {name}. Available: {available}")

    provider_class = PROVIDER_REGISTRY[category][name]
    return provider_class()


def get_available_providers(category: str | None = None) -> dict[str, dict[str, type]]:
    """
    Get available providers, optionally filtered by category.

    Args:
        category: Optional category filter ('stt', 'tts', etc.)

    Returns:
        Dict of provider categories and their registered providers
    """
    if category:
        return {category: PROVIDER_REGISTRY.get(category, {})}
    return PROVIDER_REGISTRY
```

### Registration Checklist

- [ ] Import your provider class at the top
- [ ] Add to `PROVIDER_REGISTRY` under correct category
- [ ] Use lowercase, hyphenated names (e.g., `"vibevoice-asr"`, `"chatterbox"`)
- [ ] Ensure name matches what users will put in `config.yaml`

---

## 8. Updating `config.example.yaml`

Add your new provider to the config example so users know it's available:

```yaml
# Echo-Node Configuration Example
# Copy this file to config.yaml and customize for your setup

echo_node:
  name: "Gimp"
  version: "1.0.0"

# ... (other sections)

wake_word:
  provider: openwakeword          # Wake word: openwakeword | porcupine
  model: "yo_gimp"
  threshold: 0.5
  cooldown_ms: 2000

vad:
  provider: silero                # VAD: silero | webrtc
  threshold: 0.5
  min_speech_ms: 250
  max_silence_ms: 1500

stt:
  provider: sherpa-onnx           # STT: sherpa-onnx | faster-whisper | vibevoice-asr
  model: "sherpa-onnx-streaming-zipformer-en-2023-06-26"
  device: cuda
  language: en

tts:
  provider: kokoro                # TTS: kokoro | piper | chatterbox
  model: "kokoro-v1.0"
  voice: "af_heart"
  device: cuda
  streaming: true
  sample_rate: 24000

llm:
  provider: ollama                # LLM: ollama | openai-compat | anthropic
  model: "llama3.2:7b-q4_K_M"
  base_url: "http://localhost:11434/v1"
  api_key: ""                     # Required for anthropic, openai-compat
  temperature: 0.7
  max_tokens: 256

# ... (rest of config)
```

### Config Update Checklist

- [ ] Add provider name to comment listing available options
- [ ] Include any provider-specific config options (e.g., `llm.api_key` for Anthropic)
- [ ] Set sensible defaults that work out-of-the-box

---

## 9. Testing Provider Switching

### Test 1: Basic Provider Loading

```bash
cd worker

# Test STT provider
python -c "
from worker.providers import create_provider
stt = create_provider('stt', 'vibevoice-asr')
print(f'✅ STT provider created: {type(stt).__name__}')
print(f'   VRAM requirement: {stt.vram_requirement_mb}MB')
"

# Test TTS provider
python -c "
from worker.providers import create_provider
tts = create_provider('tts', 'chatterbox')
print(f'✅ TTS provider created: {type(tts).__name__}')
print(f'   VRAM requirement: {tts.vram_requirement_mb}MB')
"

# Test LLM provider
python -c "
from worker.providers import create_provider
llm = create_provider('llm', 'anthropic')
print(f'✅ LLM provider created: {type(llm).__name__}')
print(f'   VRAM requirement: {llm.vram_requirement_mb}MB')
"
```

### Test 2: Config-Based Switching

1. **Edit `config.yaml`**:

```yaml
stt:
  provider: vibevoice-asr  # Changed from sherpa-onnx
  device: cuda

tts:
  provider: chatterbox  # Changed from kokoro
  voice: "default"
```

2. **Restart worker** and verify logs show new provider:

```bash
cd worker
python main.py

# Expected output:
# [VibeVoiceSTT] Initialized with device: cuda
# [ChatterboxTTS] Initialized: voice=default, device=cuda
```

### Test 3: Full Pipeline Test

```bash
# Terminal 1: Worker
cd worker
python main.py

# Terminal 2: Gateway
cd gateway
bun run src/index.ts

# Terminal 3: Test transcription
python -c "
import asyncio
import numpy as np
from worker.providers import create_provider

async def test_stt():
    stt = create_provider('stt', 'vibevoice-asr')
    await stt.initialize(device='cuda')

    # Generate test audio (silent for now)
    async def audio_generator():
        for i in range(10):
            yield np.zeros(512, dtype=np.float32)

    async for transcript in stt.transcribe_stream(audio_generator()):
        print(f'Transcript: {transcript}')

    await stt.shutdown()

asyncio.run(test_stt())
"
```

### Test 4: VRAM Calculator

```python
from worker.providers import create_provider

def calculate_total_vram(config: dict) -> int:
    """Calculate total VRAM for a provider configuration."""
    total = 0

    # STT
    stt = create_provider('stt', config['stt']['provider'])
    total += stt.vram_requirement_mb

    # TTS
    tts = create_provider('tts', config['tts']['provider'])
    total += tts.vram_requirement_mb

    # LLM (if local)
    if config['llm']['provider'] == 'ollama':
        llm = create_provider('llm', 'ollama')
        total += llm.vram_requirement_mb

    return total

# Example config
config = {
    'stt': {'provider': 'vibevoice-asr'},
    'tts': {'provider': 'chatterbox'},
    'llm': {'provider': 'ollama', 'model': 'llama3.2:7b'}
}

total_vram = calculate_total_vram(config)
print(f'Total VRAM required: {total_vram}MB ({total_vram / 1024:.1f}GB)')
```

---

## 10. VRAM Estimation Guidelines

Accurate VRAM estimation is critical for Echo-Node to warn users before loading models that won't fit.

### VRAM Estimation by Component

| Component | Model | VRAM (MB) | Notes |
|-----------|-------|-----------|-------|
| **STT** | sherpa-onnx (Zipformer) | 1500 | Streaming, English |
| **STT** | faster-whisper (base) | 1500 | CTranslate2 |
| **STT** | faster-whisper (large-v2) | 8000 | High accuracy |
| **STT** | vibevoice-asr | 2048 | Estimated |
| **TTS** | Kokoro-82M | 512 | Lightweight |
| **TTS** | Piper | 300 | Very light |
| **TTS** | Chatterbox-Turbo | 3072 | High quality |
| **TTS** | Orpheus-150M | 1500 | Emotion support |
| **VAD** | Silero-VAD | 50 | Tiny |
| **VAD** | WebRTC-VAD | 0 | CPU-only |
| **Wake Word** | OpenWakeWord | 100 | Small model |
| **Wake Word** | Porcupine | 0 | CPU-only |
| **LLM** | Ollama (7B q4) | 4096 | Quantized |
| **LLM** | Ollama (13B q4) | 8192 | Quantized |
| **LLM** | Ollama (70B q4) | 40960 | High-end GPU |
| **LLM** | Cloud APIs | 0 | No local VRAM |

### VRAM Calculation Formula

```python
def estimate_vram(provider_instance, model_variant: str = "") -> int:
    """
    Estimate VRAM for a provider.

    Args:
        provider_instance: Provider object
        model_variant: Optional model variant (e.g., "7b", "13b", "base", "large")

    Returns:
        VRAM in MB
    """
    # Use provider's built-in estimate
    base_vram = provider_instance.vram_requirement_mb

    # Adjust based on model variant if provided
    if model_variant:
        if "7b" in model_variant.lower():
            return 4096
        elif "13b" in model_variant.lower():
            return 8192
        elif "70b" in model_variant.lower():
            return 40960
        elif "tiny" in model_variant.lower():
            return base_vram // 3
        elif "base" in model_variant.lower():
            return base_vram
        elif "large" in model_variant.lower():
            return base_vram * 4

    return base_vram
```

### VRAM Budget Guidelines

| GPU Tier | Total VRAM | Recommended Config |
|----------|------------|-------------------|
| **Low-end** | 4GB | Kokoro TTS + sherpa-onnx STT + Cloud LLM |
| **Mid-range** | 6GB | Kokoro TTS + sherpa-onnx STT + Ollama 7B |
| **High-end** | 8-12GB | Chatterbox TTS + faster-whisper + Ollama 13B |
| **Enthusiast** | 16-24GB | Orpheus TTS + faster-whisper large + Ollama 70B |

### VRAM Warning System

Implement a pre-flight check in your worker startup:

```python
def check_vram_budget(config: dict, available_vram_mb: int) -> tuple[bool, str]:
    """
    Check if configured providers fit in available VRAM.

    Args:
        config: Configuration dict
        available_vram_mb: Available VRAM (from torch.cuda.get_device_properties)

    Returns:
        (fits, message): Tuple of success flag and explanatory message
    """
    from worker.providers import create_provider

    total_needed = 0
    breakdown = []

    # STT
    stt = create_provider('stt', config['stt']['provider'])
    stt_vram = stt.vram_requirement_mb
    total_needed += stt_vram
    breakdown.append(f"  STT ({config['stt']['provider']}): {stt_vram}MB")

    # TTS
    tts = create_provider('tts', config['tts']['provider'])
    tts_vram = tts.vram_requirement_mb
    total_needed += tts_vram
    breakdown.append(f"  TTS ({config['tts']['provider']}): {tts_vram}MB")

    # LLM (if local)
    if config['llm']['provider'] == 'ollama':
        llm = create_provider('llm', 'ollama')
        llm_vram = llm.vram_requirement_mb
        total_needed += llm_vram
        breakdown.append(f"  LLM ({config['llm']['model']}): {llm_vram}MB")

    # Check budget
    if total_needed > available_vram_mb:
        return False, (
            f"❌ VRAM overflow! Need {total_needed}MB, have {available_vram_mb}MB\n"
            + "\n".join(breakdown)
            + f"\n\nSuggestions:\n"
            + f"  - Switch TTS to 'kokoro' or 'piper' (saves ~2.5GB)\n"
            + f"  - Use cloud LLM (set llm.provider: 'openai-compat')\n"
            + f"  - Use smaller STT model\n"
        )

    return True, f"✅ VRAM OK: {total_needed}MB / {available_vram_mb}MB used"
```

---

## Quick Reference: Provider Templates

### Minimal STT Provider

```python
from typing import AsyncIterator
import numpy as np
from worker.providers.base import STTProvider

class MySTT(STTProvider):
    def __init__(self):
        self._model = None
        self._vram_mb = 1024

    @property
    def vram_requirement_mb(self) -> int:
        return self._vram_mb

    async def initialize(self, model_path: str, device: str = "cuda") -> None:
        # Load model
        pass

    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]:
        async for chunk in audio_chunks:
            yield "[transcript]"

    async def shutdown(self) -> None:
        self._model = None
```

### Minimal TTS Provider

```python
from typing import AsyncIterator
import numpy as np
from worker.providers.base import TTSProvider

class MyTTS(TTSProvider):
    def __init__(self):
        self._model = None
        self._vram_mb = 512
        self._sample_rate = 24000

    @property
    def vram_requirement_mb(self) -> int:
        return self._vram_mb

    async def initialize(self, model_path: str, voice: str, device: str = "cuda") -> None:
        # Load model
        pass

    async def synthesize(self, text: str) -> np.ndarray:
        # Return audio array
        return np.zeros(int(self._sample_rate * 0.5), dtype=np.float32)

    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        audio = await self.synthesize(text)
        chunk_size = int(self._sample_rate * 0.05)
        for i in range(0, len(audio), chunk_size):
            yield audio[i:i + chunk_size]

    async def shutdown(self) -> None:
        self._model = None
```

### Minimal LLM Provider

```python
from typing import AsyncIterator
import aiohttp
from worker.providers.base import LLMProvider

class MyLLM(LLMProvider):
    def __init__(self):
        self._base_url = ""
        self._model = ""
        self._api_key = ""
        self._session = None
        self._vram_mb = 0

    @property
    def vram_requirement_mb(self) -> int:
        return self._vram_mb

    async def initialize(self, model: str, base_url: str, api_key: str = "") -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._session = aiohttp.ClientSession()

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[str]:
        # Stream tokens
        yield "response token"

    async def shutdown(self) -> None:
        if self._session:
            await self._session.close()
```

---

## Troubleshooting

### Provider Not Found Error

```
ValueError: Unknown stt provider: my-stt. Available: ['sherpa-onnx', 'faster-whisper']
```

**Fix:** You forgot to register the provider in `worker/providers/__init__.py`. Add it to `PROVIDER_REGISTRY`.

### VRAM Overflow on Startup

```
❌ VRAM overflow! Need 9000MB, have 6000MB
```

**Fix:** Switch to lighter providers in `config.yaml`:
- TTS: `kokoro` (512MB) instead of `chatterbox` (3072MB)
- LLM: Use cloud API instead of local Ollama

### Import Error

```
ImportError: my-package not installed
```

**Fix:** Add dependency to `worker/requirements.txt` and run `pip install -r requirements.txt`.

### Streaming Not Working

If your provider doesn't stream, check:
1. `transcribe_stream()` / `chat_stream()` is an `async def` generator
2. You're using `yield` not `return`
3. Audio chunks are correct format (float32, 16kHz)

---

## See Also

- [`worker/providers/base.py`](../worker/providers/base.py) - Abstract base classes
- [`worker/providers/__init__.py`](../worker/providers/__init__.py) - Provider registry
- [`config.example.yaml`](../config.example.yaml) - Configuration reference
- [Existing providers](../worker/providers/) - Reference implementations
