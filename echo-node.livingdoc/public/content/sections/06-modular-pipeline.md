# Modular component pipeline

**Phase:** 4 — Pipeline | **Status:** Pending | **Owner:** Backend team

## Entry criteria

- [x] Architecture spec finalized (Phase 1)
- [x] `echo_node/components/` and `echo_node/pipeline/` exist (currently empty)

## Implementation

Fill the empty `echo_node/components/` and `echo_node/pipeline/` directories with the modular pipeline architecture that was stubbed out.

### Component interfaces

Each component type gets an abstract base class:

```python
# echo_node/components/interfaces.py

class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...
    @abstractmethod
    async def load(self) -> None: ...
    @abstractmethod
    async def unload(self) -> None: ...

class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> tuple[np.ndarray, int]: ...
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[tuple[np.ndarray, int]]: ...
    @abstractmethod
    async def load(self) -> None: ...
    @abstractmethod
    async def unload(self) -> None: ...

class VADProvider(ABC):
    @abstractmethod
    def is_speech(self, audio: np.ndarray) -> bool: ...
    @abstractmethod
    def speech_score(self, audio: np.ndarray) -> float: ...

class WakeWordProvider(ABC):
    @abstractmethod
    def detect(self, audio: np.ndarray) -> tuple[bool, str, float]: ...
    @abstractmethod
    def load(self) -> None: ...
```

### Pipeline orchestration

```python
# echo_node/pipeline/orchestrator.py

class Pipeline:
    """Orchestrates the voice pipeline components.
    
    In legacy mode, this runs sequentially: Wake → VAD → STT → LLM → TTS → Play.
    In live-voice mode, this is bypassed entirely (handled by cloud API).
    """
    
    def __init__(self, config: dict):
        self.wake = self._load_wake(config)
        self.vad = self._load_vad(config)
        self.stt = self._load_stt(config)
        self.tts = self._load_tts(config)
        self.llm_router = LLMRouter(config)
        
    async def process_turn(self, audio_stream: AsyncIterator[np.ndarray]) -> AsyncIterator[bytes]:
        """Full turn pipeline. Yields audio chunks for playback."""
        ...
        
    async def transcribe_only(self, audio: np.ndarray) -> str:
        """STT-only path (used by live-voice providers for local VAD)."""
        ...
```

### What goes where

**`echo_node/components/`** — standalone provider implementations:
- `stt_faster_whisper.py` — faster-whisper wrapper
- `stt_parakeet.py` — parakeet/onnx-asr wrapper
- `tts_kokoro.py` — Kokoro ONNX wrapper
- `tts_dots.py` — Dots.tts wrapper
- `tts_espeak.py` — espeak-ng wrapper
- `vad_silero.py` — Silero VAD wrapper
- `wake_openwakeword.py` — OpenWakeWord wrapper

**`echo_node/pipeline/`** — orchestration and routing:
- `orchestrator.py` — main pipeline coordinator
- `stream.py` — audio stream utilities
- `router.py` — LLM routing logic
- `interrupt.py` — barge-in coordinator

### Migration from monolithic code

1. Extract component wrappers from `assistant_v2.py` into `components/`
2. Each component gets its own file with the interface from above
3. Pipeline orchestrator replaces the inline flow in `_handle_turn()`
4. The existing `assistant_v2.py` imports from the new modules
5. No functional change until the gateway is ready

## Exit criteria

- [x] All 6+ component files exist in `echo_node/components/` (7 files, 714 lines)
- [x] Pipeline orchestrator file exists in `echo_node/pipeline/` (4 files, 1064 lines)
- [x] `assistant_v2.py` imports from the new modules (1868→291 lines, no duplication)
- [x] `from echo_node.pipeline.orchestrator import Assistant` works
- [x] All existing syntax checks pass
- [x] Components can be individually imported for testing
