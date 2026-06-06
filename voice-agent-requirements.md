# Echo-Node — Software Requirements Specification

> **Version:** 1.1.0-draft
> **Date:** 2026-03-29
> **Status:** Draft — synthesized from 5 source documents + user answers
> **Project:** Echo-Node (Modular Open-Source Voice AI Interface)

---

## 1. Problem Statement

### 1.1 What We're Building

A **modular, open-source voice AI interface** that provides:

1. **Always-on voice assistant** — wake word activation, STT → LLM → TTS pipeline
2. **Animated 3D avatar** — lip-synced VRM character with idle animations (Web UI mode)
3. **Headless CLI mode** — terminal-only operation without any UI
4. **Pluggable components** — swap STT, TTS, LLM, wake word, and VAD providers via YAML config without code changes
5. **Agent integration** — works as a voice channel for Hermes Agent and as an OpenClaw skill

### 1.2 Core Architecture: Split Stack

The system is a **split-stack** architecture:

```
┌─────────────────────────────────────────────────┐
│         Svelte 5 Frontend (Web UI)               │
│   TalkingHead avatar · Frame themes · Controls   │
└────────────────────┬────────────────────────────┘
                     │ WebSocket (JSON events)
┌────────────────────▼────────────────────────────┐
│          Bun + Hono Gateway                      │
│   State relay · REST API · WebSocket hub         │
│   Client sessions · Integration adapters         │
└────────────────────┬────────────────────────────┘
                     │ WebSocket (binary audio + JSON)
┌────────────────────▼────────────────────────────┐
│         Python Audio Worker                      │
│   Wake word · VAD · STT · TTS · LLM client      │
│   State machine · Provider abstractions          │
│   Echo cancellation · Streaming pipeline         │
└─────────────────────────────────────────────────┘
```

**Why split?** ML inference (STT/TTS/VAD) requires Python (CUDA, PyTorch, ONNX). The gateway and UI use the user's preferred stack (Bun + Svelte 5).

### 1.3 Existing Components to Use (Don't Rebuild)

| Component | Library | License | What It Solves |
|-----------|---------|---------|---------------|
| Avatar + lip-sync | **TalkingHead** (met4citizen) | MIT | 3D VRM avatar with real-time lip-sync, idle animations, eye tracking, procedural gestures |
| STT (streaming) | **sherpa-onnx** | Apache 2.0 | Unified streaming/offline STT with ONNX models (Whisper, Parakeet, Zipformer) |
| TTS (edge) | **Kokoro-82M** | MIT | Lightweight 82M param TTS with phoneme timing |
| TTS (quality) | **Chatterbox-Turbo** | MIT | Sub-200ms latency, beats ElevenLabs in blind tests |
| TTS (emotion) | **Orpheus TTS** (150M/400M) | Apache 2.0 | Human-level emotion, streaming 25-50ms chunks |
| Wake word | **OpenWakeWord** | Apache 2.0 | Custom keyword detection |
| VAD | **Silero-VAD** / sherpa-onnx | MIT | Voice activity detection |
| Echo cancellation | **SpeexDSP** | BSD | Acoustic echo cancellation |

### 1.4 Design Philosophy

> **"Stitch, don't rebuild."** — Use existing libraries as black boxes. Build only the glue: provider abstractions, config system, state machine, integration adapters, and UI shell.

---

## 2. User Stories

### 2.1 Core Pipeline

> **US-01: Wake Word Activation**
> As a user, I want to say "Yo Gimp" (default wake word) or press a hotkey to activate the assistant, so that it's always listening but only processing when triggered. The wake word SHALL be configurable via `config.yaml`.

> **US-02: Voice Conversation**
> As a user, I want to speak naturally and receive spoken responses from an LLM, with the full cycle (end-of-speech → first audio playback) completing in under 2 seconds.

> **US-03: Provider Switching**
> As a user, I want to change my STT engine from whisper to parakeet by editing `config.yaml` and restarting, without modifying any code.

> **US-04: Multi-Tier TTS**
> As a user, I want to select between lightweight (Kokoro), real-time (Chatterbox), and quality (Orpheus) TTS modes, each optimized for different use cases.

> **US-16: Configurable LLM Endpoint**
> As a user, I want to point the voice assistant at any LLM backend — Hermes Agent, OpenRouter, OpenAI, Ollama, or any OpenAI-compatible API — by changing `llm.base_url` and `llm.api_key` in config.

> **US-17: Response Personality**
> As a user, I want to select a personality preset (hacker, seductive, butler, drill-sergeant, stoner-philosopher, etc.) that changes the assistant's tone and speaking style, with the ability to create custom personalities.

> **US-18: Conversation Memory**
> As a user, I want the assistant to remember the last 15 turns of our conversation within a session, so that I can have a natural back-and-forth dialogue. Cross-session memory is NOT required (the agent handles that).

> **US-19: Configurable Activation Sound**
> As a user, I want to choose what sound plays when the wake word is detected — a beep, a chime, a custom audio file, or silence.

### 2.2 Avatar & UI

> **US-05: Animated Avatar**
> As a user, I want to see a 3D avatar that lip-syncs to the assistant's speech, blinks, looks around, and performs idle gestures while waiting.

> **US-06: Frame Themes**
> As a user, I want to choose from visual themes (minimal, cyberpunk, retro-terminal, glassmorphism, none) that frame the avatar display.

> **US-07: Headless Mode**
> As a user, I want to run the assistant from the terminal with zero graphical UI, receiving text output and audio-only responses.

> **US-20: Avatar Rotation**
> As a user, I want a library of 10-15 default VRM avatars that can be rotated automatically or manually swapped. I should be able to add my own VRM models to the rotation pool.

### 2.3 Agent Integration

> **US-08: Hermes Voice Channel**
> As a Hermes Agent user, I want Echo-Node to register as a voice input/output channel, so that I can talk to Hermes instead of typing.

> **US-09: OpenClaw Skill**
> As an OpenClaw user, I want Echo-Node to appear as a skill that OpenClaw can invoke for voice interaction tasks.

> **US-10: MCP Tool Integration**
> As a user, I want the assistant to invoke MCP-connected tools when I ask it to (e.g., "search the web for X"), using LLM function calling.

### 2.4 Platform & Hardware

> **US-11: VRAM-Aware Loading**
> As a user with a 6GB GPU, I want the system to calculate total VRAM requirements before loading models and warn me if the combination won't fit.

> **US-12: CPU Fallback**
> As a user with an Intel Arc GPU, I want automatic CPU/OpenVINO fallback for inference when CUDA is unavailable.

> **US-13: WSL2 Audio**
> As a WSL2 user, I want the system to auto-detect and configure PipeWire/PulseAudio for microphone access.

### 2.5 Extensibility

> **US-14: Custom Wake Words**
> As a user, I want to train a custom wake word model using OpenWakeWord's training pipeline and load it via config.

> **US-15: Custom VRM Models**
> As a user, I want to use my own VRM avatar model by pointing the config to a local `.vrm` file.

---

## 3. Functional Requirements

### 3.1 Audio Pipeline (Python Worker)

| ID | Requirement | Phase |
|----|------------|-------|
| FR-01 | The system SHALL capture microphone audio at 16kHz mono via PyAudio/sounddevice | 1 |
| FR-02 | The system SHALL detect voice activity using Silero-VAD with configurable thresholds | 1 |
| FR-03 | The system SHALL detect the wake word "Yo Gimp" (default, configurable) using OpenWakeWord with ≤5% false positive rate | 1 |
| FR-04 | The system SHALL transcribe speech using sherpa-onnx streaming API with ≤500ms latency | 1 |
| FR-05 | The system SHALL support alternative STT providers (faster-whisper, Parakeet) via provider interface | 2 |
| FR-06 | The system SHALL synthesize speech using Kokoro-82M with streaming output (sentence-boundary chunking) | 1 |
| FR-07 | The system SHALL support alternative TTS providers (Chatterbox-Turbo, Orpheus, Piper) via provider interface | 2 |
| FR-08 | The system SHALL send transcribed text to a user-configurable LLM endpoint (OpenAI-compatible API) and stream the response. Supported targets: Ollama (local), OpenRouter, OpenAI, Hermes Agent, or any endpoint implementing the OpenAI chat completions schema. | 1 |
| FR-09 | The system SHALL mute the microphone during TTS playback (MVP echo cancellation) | 1 |
| FR-10 | The system SHALL support SpeexDSP acoustic echo cancellation (production mode) | 3 |

### 3.2 State Machine

| ID | Requirement | Phase |
|----|------------|-------|
| FR-11 | The Python worker SHALL own a 5-state machine: DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING | 1 |
| FR-12 | State transitions SHALL be emitted as WebSocket events to the gateway | 1 |
| FR-13 | The system SHALL support keyboard-triggered activation (bypass wake word) | 1 |
| FR-14 | The system SHALL return to DORMANT after TTS playback completes or after 30s timeout | 1 |
| FR-15 | The system SHALL allow interruption during SPEAKING state (barge-in) via new wake word or keyboard | 2 |

### 3.3 Gateway (Bun + Hono)

| ID | Requirement | Phase |
|----|------------|-------|
| FR-16 | The gateway SHALL relay state events from Python worker to connected frontend clients | 1 |
| FR-17 | The gateway SHALL serve the Svelte 5 frontend via static file serving | 2 |
| FR-18 | The gateway SHALL expose a REST API for configuration management (GET/PUT /api/config) | 2 |
| FR-19 | The gateway SHALL support multiple simultaneous frontend clients | 3 |
| FR-20 | The gateway SHALL provide a health endpoint (GET /api/health) reporting worker status | 1 |

### 3.4 Frontend (Svelte 5)

| ID | Requirement | Phase |
|----|------------|-------|
| FR-21 | The frontend SHALL display a TalkingHead VRM avatar that lip-syncs to TTS audio | 2 |
| FR-22 | The avatar SHALL perform idle animations (blinking, looking around, subtle gestures) when not speaking | 2 |
| FR-23 | The frontend SHALL display a visual waveform/indicator during LISTENING state | 2 |
| FR-24 | The frontend SHALL support 5 frame themes (none, minimal, cyberpunk, retro-terminal, glassmorphism) | 2 |
| FR-25 | The frontend SHALL display conversation history as a scrollable transcript | 2 |
| FR-26 | The frontend SHALL allow theme, avatar, and pipeline configuration via settings panel | 3 |

### 3.5 Configuration

| ID | Requirement | Phase |
|----|------------|-------|
| FR-27 | All pipeline components SHALL be configurable via a single `config.yaml` file | 1 |
| FR-28 | The config SHALL specify: wake_word, vad, stt, tts, llm, personality, integrations, ui sections | 1 |
| FR-29 | The system SHALL validate config on startup and report misconfiguration clearly | 1 |
| FR-30 | The system SHALL calculate and report total VRAM usage before loading models | 2 |

### 3.8 Personality & Memory

| ID | Requirement | Phase |
|----|------------|-------|
| FR-39 | The system SHALL support personality presets that modify the LLM system prompt (tone, vocabulary, behavioral rules) | 1 |
| FR-40 | The system SHALL ship with 5+ default personality presets: `hacker`, `seductive`, `butler`, `drill-sergeant`, `stoner-philosopher` | 1 |
| FR-41 | Users SHALL be able to create custom personality files (YAML with name, description, system_prompt) | 1 |
| FR-42 | The system SHALL maintain a sliding-window conversation history of up to 15 turns per session | 1 |
| FR-43 | Conversation history SHALL be discarded when the session ends (no cross-session persistence) | 1 |
| FR-44 | The activation sound SHALL be configurable: built-in options (beep, chime, silence) or a custom audio file path | 1 |

### 3.9 LLM Endpoint

| ID | Requirement | Phase |
|----|------------|-------|
| FR-45 | The LLM provider SHALL accept `base_url`, `api_key`, and `model` parameters to target any OpenAI-compatible API | 1 |
| FR-46 | The system SHALL support Ollama, OpenRouter, OpenAI, and Hermes Agent as LLM targets without code changes | 1 |
| FR-47 | The `api_key` field SHALL be optional (Ollama doesn't need one, OpenRouter/OpenAI do) | 1 |

### 3.10 Avatar Library

| ID | Requirement | Phase |
|----|------------|-------|
| FR-48 | The system SHALL ship with 10-15 default VRM avatar models that can be rotated or manually selected | 2 |

### 3.6 Integration Adapters

| ID | Requirement | Phase |
|----|------------|-------|
| FR-31 | The system SHALL register as a Hermes Agent voice channel via WebSocket | 3 |
| FR-32 | The system SHALL create an OpenClaw skill file for voice interaction | 3 |
| FR-33 | The system SHALL support LLM function calling for MCP tool invocation | 3 |
| FR-34 | Integration adapters SHALL be toggled on/off via config.yaml | 3 |

### 3.7 Platform

| ID | Requirement | Phase |
|----|------------|-------|
| FR-35 | The system SHALL auto-detect CUDA, OpenVINO, or CPU-only runtime | 1 |
| FR-36 | The system SHALL configure PipeWire/PulseAudio for WSL2 audio access | 1 |
| FR-37 | The system SHALL support Fedora 43, Ubuntu 24.04, macOS 14+, WSL2 | 1 |
| FR-38 | The system SHALL provide a setup script that installs Python dependencies and downloads models | 1 |

---

## 4. Non-Functional Requirements

| ID | Requirement | Category |
|----|------------|----------|
| NFR-01 | End-to-end latency (end-of-speech → first audio byte) SHALL be ≤2 seconds on RTX 4050 | Performance |
| NFR-02 | All models combined SHALL fit within 6GB VRAM when using default config | Resource |
| NFR-03 | The system SHALL run on Linux (Fedora/Ubuntu), macOS, and Windows via WSL2 | Portability |
| NFR-04 | All dependencies SHALL be open-source (MIT, Apache 2.0, or BSD) | License |
| NFR-05 | The core pipeline (STT, TTS, VAD, wake word) SHALL operate fully offline. The LLM endpoint MAY be cloud-based (OpenRouter, OpenAI) if the user configures it. | Privacy |
| NFR-06 | Provider interfaces SHALL allow adding new STT/TTS/VAD/wake word providers without modifying core code | Modularity |
| NFR-07 | The frontend SHALL be responsive (mobile-friendly for remote access) | Accessibility |
| NFR-08 | The system SHALL produce structured JSON logs (Python: structlog, Bun: pino) | Observability |

---

## 5. Implementation Phases

### Phase 1: CLI MVP (Weeks 1-3)
**Goal:** Working voice conversation in the terminal — no UI, no avatar.

- Python audio worker: mic capture → VAD → wake word → STT → LLM → TTS → speaker
- 5-state machine with keyboard trigger
- Kokoro-82M TTS + sherpa-onnx STT + Silero-VAD + OpenWakeWord (default: "Yo Gimp")
- Mic mute during TTS (MVP echo cancellation)
- `config.yaml` with provider selection + personality + LLM endpoint config
- User-configurable LLM endpoint (Ollama, OpenRouter, OpenAI, Hermes, any OpenAI-compat)
- 5 personality presets (hacker, seductive, butler, drill-sergeant, stoner-philosopher)
- 15-turn sliding-window conversation memory (per session)
- Configurable activation sound (beep, chime, silent, custom file)
- Setup script (install deps + download models)
- WebSocket connection to Bun/Hono gateway (state events)
- Gateway health endpoint

**Acceptance:** Say "Yo Gimp" → speak → hear response in hacker personality → see transcript in terminal → follow-up question references previous answer.

### Phase 2: Web UI + Avatar (Weeks 4-6)
**Goal:** Full visual experience with TalkingHead avatar.

- Svelte 5 frontend with TalkingHead integration
- 10-15 bundled VRM avatars with rotation/selection
- Avatar lip-sync from TTS audio stream
- Frame theme system (5 themes via CSS)
- Waveform visualizer during listening
- Conversation transcript panel
- Provider switching UI + personality selector
- Avatar picker (browse library, upload custom)
- VRAM calculator display
- Alternative STT/TTS providers (Chatterbox, faster-whisper)
- Barge-in support

**Acceptance:** Open browser → see randomly selected avatar → speak → avatar responds with lip-sync → switch avatar from library.

### Phase 3: Integrations (Weeks 7-9)
**Goal:** Echo-Node as a component in larger agent systems.

- Hermes Agent channel adapter (WebSocket)
- OpenClaw skill adapter
- MCP tool calling through LLM
- SpeexDSP echo cancellation
- Multi-session support
- Settings panel in frontend

**Acceptance:** Hermes Agent receives voice input via Echo-Node channel.

### Phase 4: Polish (Weeks 10+)
**Goal:** Production readiness and extended hardware support.

- OpenVINO backend for Intel Arc
- Custom wake word training pipeline
- Model preloading / VRAM management
- Plugin system for custom providers
- Documentation + deployment guides

---

## 6. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | Svelte 5 Runes | User's preferred framework, $state/$derived reactivity |
| **Gateway** | Bun + Hono | User's preferred runtime, fast WebSocket server |
| **Audio Worker** | Python 3.11+ | Required for ML inference (CUDA, PyTorch, ONNX) |
| **STT** | sherpa-onnx | Streaming, all-in-one, broad model support |
| **TTS (default)** | Kokoro-82M | Lightweight, MIT, fits VRAM budget |
| **TTS (quality)** | Chatterbox-Turbo, Orpheus | Higher quality tiers for capable hardware |
| **Avatar** | TalkingHead | Proven VRM solution, MIT, built-in lip-sync |
| **Wake Word** | OpenWakeWord | Custom keyword detection, Apache 2.0 |
| **VAD** | Silero-VAD | Lightweight, accurate, MIT |
| **LLM** | OpenAI-compatible API (Ollama, OpenRouter, OpenAI, Hermes) | User-configurable endpoint, any OpenAI-compat target |
| **Config** | YAML | Human-readable, proven for config files |
| **IPC** | WebSocket | Binary audio + JSON events between all layers |

---

## 7. Constraints & Risks

### Constraints

- **6GB VRAM ceiling** — must fit STT + TTS + LLM simultaneously
- **No proprietary SDKs** — excludes NVIDIA Audio2Face, ElevenLabs, Deepgram
- **Python required** — ML inference ecosystem is Python; can't avoid it
- **WSL2 audio** — requires PipeWire/PulseAudio configuration (not automatic)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| TalkingHead API changes | Low | High | Pin version, vendor into project |
| sherpa-onnx model compatibility | Medium | Medium | Test with specific model versions, document known-good configs |
| LLM streaming + function calling | Medium | Medium | Start with Ollama's native function calling, fallback to prompt engineering |
| WSL2 mic access flaky | High | High | Document PipeWire setup, test on Fedora 43 WSLg |
| VRAM overflow with large models | High | High | VRAM calculator warns before loading, default to smallest models |

---

## 8. Success Criteria

The system is successful when:

1. ✅ A user can say "Yo Gimp", speak a question, and hear a spoken response within 2 seconds
2. ✅ The 3D avatar lip-syncs to the response in real-time
3. ✅ Changing `stt.provider: parakeet` in `config.yaml` switches the STT engine on restart
4. ✅ Switching `llm.base_url` to OpenRouter/OpenAI works without code changes
5. ✅ Selecting `personality: hacker` changes the assistant's tone and behavior
6. ✅ The assistant remembers context from 15 turns ago in the same session
7. ✅ The system runs without a GPU (CPU fallback, slower but functional)
8. ✅ Headless CLI mode produces audio-only conversation without any graphical dependencies
9. ✅ Hermes Agent can receive voice input through Echo-Node acting as a channel
10. ✅ All models fit within 6GB VRAM using default configuration

---

## 9. Out of Scope (Explicitly Deferred)

| Feature | Reason |
|---------|--------|
| Cloud STT/TTS providers (Deepgram, ElevenLabs) | Open-source only constraint |
| Mobile native app | Web-responsive covers mobile access |
| Multi-language STT | English-first; multilingual after Phase 4 |
| Custom avatar modeling tools | Use existing VRM models; don't build a modeling pipeline |
| Distributed multi-node inference | Single-machine target |
| Voice cloning | Ethical/legal complexity; use pre-trained voices |
