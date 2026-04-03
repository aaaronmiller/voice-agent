# Phase 0: Research & Technical Decisions

**Date**: 2026-03-29
**Branch**: 001-echo-node-core

---

## Research Task 1: VibeVoice-ASR Integration

**Decision**: Integrate VibeVoice-ASR (7B-9B params) as optional STT provider alongside sherpa-onnx (default) and faster-whisper.

**Rationale**: 
- Microsoft's VibeVoice-ASR handles 60-minute long-form audio in single pass
- 51 languages supported with code-switching
- MIT license (permissive, aligns with Constitution)
- Available on HuggingFace with Transformers support

**Alternatives Considered**:
- sherpa-onnx (default): Lighter weight, broader model support, Apache 2.0
- faster-whisper: Good fallback, CPU-friendly, MIT

**VRAM Note**: VibeVoice-ASR requires ~18GB VRAM at FP16 or ~6GB with 4-bit quantization. Will require VRAM-aware loading and user warning.

**Integration Approach**: 
- Subclass `STTProvider` ABC from `worker/providers/base.py`
- Implement `initialize()`, `transcribe_stream()`, `shutdown()`, `vram_requirement_mb`
- Register as `vibevoice-asr` in provider registry
- Add config validation for model path and quantization option

**Status**: ✅ Resolved (VibeVoice-TTS code removed from GitHub Sept 2025, only ASR available)

---

## Research Task 2: Gemini Flash Live API Mode

**Decision**: Implement as separate `pipeline_mode: cloud` configuration that bypasses modular STT/TTS/LLM chain.

**Rationale**:
- Gemini Live handles audio-to-audio directly via WebSocket
- Does not fit provider ABC model (coupled STT+LLM+TTS)
- Clean separation keeps local modular architecture intact
- Uses same wake word, config system, and frontend

**Alternatives Considered**:
- Option A (LLM provider type): Breaks provider abstraction, Gemini manages its own STT/TTS
- Option C (STT+TTS providers): Forces Gemini STT/TTS to work with any LLM, not supported

**Integration Approach**:
- Add `pipeline_mode: local | cloud` top-level config option
- When `cloud`: gateway opens direct WebSocket to `generativelanguage.googleapis.com`
- Python worker still handles wake word detection (gates when cloud stream opens)
- Frontend unchanged (receives same state events)

**API Details**:
- Endpoint: `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`
- Requires user-provided API key
- 16kHz PCM audio input/output
- Native VAD + barge-in handled server-side

**Status**: ✅ Resolved

---

## Research Task 3: Remote Client Protocol (ESP32/Terminal/Browser)

**Decision**: Single WebSocket protocol with raw 16kHz PCM for all clients. ESP32 gets simplified binary protocol handler as fallback if raw PCM is infeasible.

**Rationale**:
- Keeps gateway logic simple (single protocol handler)
- Browser and terminal clients can send raw PCM via Web Audio API
- ESP32 may need compression (Opus) or simplified protocol due to memory constraints
- Defers multi-session concurrency to post-v1 (single active conversation)

**Alternatives Considered**:
- Option B (Opus compression): Adds transcoding complexity in gateway
- Option C (Three separate handlers): Maximum flexibility, highest complexity

**Protocol Design**:
- Browser/Terminal: WebSocket with JSON events + binary PCM frames
- ESP32: Binary protocol with frame headers (message type, length, payload)
- Gateway routes all audio to Python worker via single internal WebSocket

**Multi-Client Handling (MVP)**:
- First client to trigger wins
- Others receive "busy" state, wait for current session to complete
- No queuing, no mixing (deferred to post-v1)

**Status**: ✅ Resolved

---

## Research Task 4: TalkingHead Avatar Integration

**Decision**: Use TalkingHead by met4citizen (MIT license) as bundled dependency.

**Rationale**:
- Proven VRM avatar solution with real-time lip-sync
- Built-in idle animations (blinking, eye tracking, gestures)
- MIT license aligns with Constitution
- Svelte/Three.js compatible

**Alternatives Considered**:
- Custom Three.js + VRM loader: More control, higher complexity
- Other avatar libraries: Less mature, restrictive licenses

**Integration Approach**:
- Bundle TalkingHead into `frontend/src/lib/components/avatar-display.svelte`
- Drive lip-sync from TTS audio amplitude (no ML required)
- Idle animations run on timer when state = DORMANT
- Avatar selection via config (`ui.avatar.model`) or settings panel

**VRM Model Pool**:
- Bundle 10-15 default avatars (casual, punk, corporate, anime, robot, witch, pirate, cyborg, elf, scientist, ninja, steampunk)
- User can add custom `.vrm` files to `frontend/src/static/models/`

**Status**: ✅ Resolved

---

## Research Task 5: WSL2 Audio Configuration

**Decision**: Auto-detect PipeWire/PulseAudio at startup, configure PyAudio accordingly.

**Rationale**:
- WSL2 does not expose mic directly (requires PipeWire/PulseAudio bridge)
- Fedora 43 WSLg has PipeWire built-in
- Ubuntu 24.04 may require manual PulseAudio setup

**Detection Logic**:
```python
# Check for PipeWire first
if shutil.which("pw-cli"):
    use_pipewire()
elif shutil.which("pactl"):
    use_pulseaudio()
else:
    warn_user("No audio server detected. Install PipeWire or PulseAudio for WSL2.")
```

**Integration Approach**:
- Add `audio/wsl2_config.py` module
- Run detection at worker startup
- Set `PYAUDIO_DEFAULT_DEVICE` environment variable
- Document manual setup in `docs/setup-wsl2.md`

**Status**: ✅ Resolved

---

## Research Task 6: Provider ABC Design

**Decision**: All providers implement ABC with `initialize()`, core process method, `shutdown()`, `vram_requirement_mb`.

**Rationale**:
- Aligns with Constitution Principle IV (Provider Abstraction)
- Enables hot-swapping via config without code changes
- VRAM reporting enables resource-aware loading (Principle V)

**ABC Definitions**:
```python
class STTProvider(ABC):
    async def initialize(self, model_path: str, device: str) -> None
    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]
    async def shutdown(self) -> None
    @property def vram_requirement_mb(self) -> int

class TTSProvider(ABC):
    async def initialize(self, model_path: str, voice: str, device: str) -> None
    async def synthesize(self, text: str) -> np.ndarray
    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]
    async def shutdown(self) -> None
    @property def vram_requirement_mb(self) -> int

class VADProvider(ABC):
    async def initialize(self, model_path: str) -> None
    def is_speech(self, audio_chunk: np.ndarray) -> bool
    async def shutdown(self) -> None

class WakeWordProvider(ABC):
    async def initialize(self, model_path: str, threshold: float) -> None
    def detect(self, audio_chunk: np.ndarray) -> bool
    async def shutdown(self) -> None

class LLMProvider(ABC):
    async def initialize(self, model: str, base_url: str, api_key: str) -> None
    async def chat_stream(self, messages: list[dict], tools: list[dict] | None) -> AsyncIterator[str]
    async def shutdown(self) -> None
```

**Provider Registry**:
```python
PROVIDER_REGISTRY = {
    "stt": {"sherpa-onnx": SherpaSTT, "faster-whisper": FasterWhisperSTT, "vibevoice-asr": VibeVoiceASR},
    "tts": {"kokoro": KokoroTTS, "chatterbox": ChatterboxTTS, "orpheus": OrpheusTTS, "piper": PiperTTS},
    "vad": {"silero": SileroVAD},
    "wake_word": {"openwakeword": OpenWakeWordProvider},
    "llm": {"ollama": OllamaLLM, "openai-compat": OpenAICompatLLM},
}
```

**Status**: ✅ Resolved

---

## Research Task 7: Streaming Pipeline Design

**Decision**: Sentence-boundary chunking with parallel synthesis/playback.

**Rationale**:
- Aligns with Constitution Principle VII (Streaming-First Latency)
- Avoids waiting for full LLM response before TTS begins
- Meets ≤2s end-to-end latency target

**Pipeline Flow**:
```
VAD silence → STT partials → LLM tokens → Sentence chunker → TTS synthesize → Playback
                                                              ↓
                                              (next sentence synthesizes while current plays)
```

**Sentence Chunker**:
```python
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

async def chunk_sentences(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    buffer = ""
    async for token in token_stream:
        buffer += token
        parts = SENTENCE_END.split(buffer)
        while len(parts) > 1:
            yield parts.pop(0).strip()
        buffer = " ".join(parts)
    if buffer.strip():
        yield buffer.strip()
```

**Barge-in Handling**:
- Check `_barge_in_requested` between sentence playback
- If true: break synthesis loop, return to LISTENING state

**Status**: ✅ Resolved

---

## Research Task 8: VRAM Calculator

**Decision**: Pre-load VRAM check with fallback suggestions.

**Rationale**:
- Aligns with Constitution Principle V (Resource-Aware Loading)
- Prevents mid-load crashes
- User-friendly error messages

**Implementation**:
```python
import pynvml

def get_available_vram() -> int:
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    return info.free // (1024 * 1024)  # MB

def check_vram(providers: list[Provider]) -> tuple[bool, int, int]:
    total_needed = sum(p.vram_requirement_mb for p in providers)
    available = get_available_vram()
    return total_needed <= available, total_needed, available
```

**Fallback Suggestions**:
- If VRAM insufficient: suggest smaller models (Kokoro over Orpheus, sherpa-onnx over VibeVoice-ASR)
- Offer CPU fallback with latency warning
- Quantization options (4-bit for VibeVoice-ASR: ~6GB vs ~18GB)

**Status**: ✅ Resolved

---

## Summary of Resolved Unknowns

| Unknown | Decision |
|---------|----------|
| VibeVoice integration | ASR only (TTS removed), optional provider with VRAM warning |
| Gemini Live mode | Separate `pipeline_mode: cloud` config, bypasses local STT/TTS/LLM |
| Remote client protocol | Single WebSocket PCM, ESP32 fallback if needed, single active conversation MVP |
| TalkingHead integration | Bundled dependency, lip-sync from audio amplitude |
| WSL2 audio | Auto-detect PipeWire/PulseAudio, set PyAudio device |
| Provider ABC design | 5 ABCs with initialize/process/shutdown/vram |
| Streaming pipeline | Sentence chunking, parallel synthesis/playback |
| VRAM calculator | Pre-load check with fallback suggestions |

**All NEEDS CLARIFICATION items resolved. Phase 0 complete.**
