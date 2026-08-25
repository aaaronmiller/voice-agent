# Unified provider abstraction

**Phase:** 7 — Providers | **Status:** Partial (backends.py exists) | **Owner:** Backend team

## Entry criteria

- [x] Architecture spec finalized (Phase 1)
- [x] Modular pipeline designed (Phase 4)
- [x] `echo_node/backends.py` exists with `AgentBackend` ABC

## Implementation

### Current state

The existing `echo_node/backends.py` has:
- ✅ `AgentBackend` abstract base class with `chat()` and `chat_stream()` methods
- ✅ 6 implementations: HermesBackend, PiBackend, ClaudeBackend, CodexBackend, OpenAIBackend, OpenRouterBackend
- ✅ `REGISTRY` dict for lookup
- ✅ `create_backend()` factory function

### What needs to change

The current system is **LLM-only** — it only abstracts the response generation. We need the same pattern for:

1. **STT providers** (whisper, parakeet, cloud STT)
2. **TTS providers** (kokoro, dots, espeak, cloud TTS)
3. **VAD providers** (silero, cloud VAD, webrtcvad)
4. **Wake word providers** (openwakeword, porcupine, snowboy)
5. **Live-voice providers** (gemini-live, openai-realtime) — these wrap all of the above

### New file structure

```
echo_node/
├── backends.py          # LLM backend system (existing, extend)
├── providers/
│   ├── __init__.py
│   ├── interfaces.py    # All provider ABCs
│   ├── registry.py      # Provider registry and discovery
│   ├── stt/
│   │   ├── base.py      # STTProvider ABC
│   │   ├── whisper.py   # faster-whisper
│   │   └── parakeet.py  # onnx-asr
│   ├── tts/
│   │   ├── base.py      # TTSProvider ABC
│   │   ├── kokoro.py    # Kokoro ONNX
│   │   ├── dots.py      # Dots.tts
│   │   └── espeak.py    # espeak-ng
│   ├── vad/
│   │   ├── base.py      # VADProvider ABC
│   │   └── silero.py    # Silero VAD
│   ├── wake/
│   │   ├── base.py      # WakeWordProvider ABC
│   │   └── openwakeword.py
│   └── live/            # Live-voice providers (new)
│       ├── base.py      # LiveVoiceProvider ABC
│       ├── gemini_live.py
│       └── openai_realtime.py
```

### Provider interfaces

```python
# echo_node/providers/interfaces.py

class Provider(ABC):
    """Base for all providers."""
    name: str = ""
    config_key: str = ""
    
    @abstractmethod
    async def load(self) -> None: ...
    @abstractmethod
    async def unload(self) -> None: ...
    @abstractmethod
    async def health_check(self) -> HealthStatus: ...

class STTProvider(Provider):
    @abstractmethod
    async def transcribe(self, audio: np.ndarray, sr: int) -> str: ...
    @abstractmethod
    async def transcribe_stream(self) -> AsyncIterator[str]: ...

class TTSProvider(Provider):
    @abstractmethod
    async def synthesize(self, text: str) -> tuple[np.ndarray, int]: ...
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[tuple[np.ndarray, int]]: ...

class VADProvider(Provider):
    @abstractmethod
    def is_speech(self, audio: np.ndarray) -> bool: ...
    @abstractmethod
    def speech_score(self, audio: np.ndarray) -> float: ...

class WakeWordProvider(Provider):
    @abstractmethod
    def detect(self, audio: np.ndarray) -> tuple[bool, str, float]: ...

class LiveVoiceProvider(Provider):
    """A live-voice provider handles everything (STT, LLM, TTS) internally."""
    @abstractmethod
    async def start_session(self) -> AsyncIterator[LiveEvent]: ...
    @abstractmethod
    async def send_audio(self, data: bytes): ...
    @abstractmethod
    async def interrupt(self): ...
```

### Registration and discovery

```python
# echo_node/providers/registry.py

from echo_node.providers.interfaces import *

class ProviderRegistry:
    """Central registry for all provider types."""
    
    def __init__(self):
        self._stt: dict[str, type[STTProvider]] = {}
        self._tts: dict[str, type[TTSProvider]] = {}
        self._vad: dict[str, type[VADProvider]] = {}
        self._wake: dict[str, type[WakeWordProvider]] = {}
        self._live: dict[str, type[LiveVoiceProvider]] = {}
        
    def register(self, provider_type: str, name: str, cls: type):
        """Register a provider class."""
        getattr(self, f'_{provider_type}')[name] = cls
        
    def create(self, provider_type: str, name: str, config: dict) -> Provider:
        """Instantiate a provider by type and name."""
        cls = getattr(self, f'_{provider_type}')[name]
        return cls(config)
        
    def list_available(self, provider_type: str) -> list[str]:
        """List registered providers of a type."""
        return list(getattr(self, f'_{provider_type}').keys())

# Global registry
registry = ProviderRegistry()
```

### Auto-discovery

Providers can register themselves:

```python
# echo_node/providers/stt/whisper.py
from echo_node.providers.registry import registry

class FasterWhisperSTT(STTProvider):
    name = "faster-whisper"
    ...

registry.register("stt", "faster-whisper", FasterWhisperSTT)
```

Or via a `setup.py` entry point / config scanning.

## Exit criteria

- [ ] All 5 provider interface ABCs defined
- [ ] Registry with auto-discovery working
- [ ] Existing STT/TTS/VAD/wake refactored to use new interfaces
- [ ] Gateway can discover and select providers by name
- [ ] Live-voice provider interface proven with Gemini Live implementation
- [ ] `python -c "from echo_node.providers.registry import registry; print(registry.list_available('stt'))"` works
