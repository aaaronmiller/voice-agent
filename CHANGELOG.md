# Changelog

All notable changes to Echo-Node will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed

- **T121**: Registered VibeVoiceASR in provider registry (was commented out)
- **T120**: Added EchoCanceller to `worker/audio/__init__.py` exports (was missing)
- **Frontend build**: Fixed `app.html` missing `%sveltekit.head%`, added `<slot />` to `+layout.svelte`, fixed TalkingHead named import, upgraded `@sveltejs/vite-plugin-svelte` to v4
- **Worker imports**: Fixed `EchoCanceler` → `EchoCanceller` class name typo preventing audio module load
- **Root package.json**: Added with `bun run dev`, `bun run worker`, `bun run gateway`, `bun run frontend` scripts (matches quickstart.md)

### Added

- **Phase 9: Polish & Cross-Cutting Concerns**
  - SpeexDSP acoustic echo cancellation (`worker/audio/echo_cancel.py`)
  - VibeVoice-ASR provider (7B model, 51 languages)
  - Remote terminal client support (thin-client mode) in session manager
  - LAN access logging for unauthorized connections
  - `docs/troubleshooting.md`
  - Root `package.json` with concurrently for multi-component dev

### Added

- **Phase 1: Setup & Phase 2: Foundational** (27 files, core architecture)
  - Project structure: worker/, gateway/, frontend/, models/, docs/
  - Python 3.11+ worker with Bun gateway and Svelte 5 frontend scaffolding
  - Provider ABCs: STT, TTS, VAD, WakeWord, LLM base classes
  - 5-state machine: DORMANT, TRIGGERED, LISTENING, PROCESSING, SPEAKING
  - Config loader with validation (Python + TypeScript)
  - Audio capture (PyAudio/sounddevice) and playback pipeline
  - WebSocket hub for frontend ↔ worker ↔ gateway relay
  - VRAM calculator for model load safety checks
  - REST API skeleton: /api/health, /api/config, /api/status
  - Structured logging with pino
  - Streaming modules: sentence chunker, conversation memory (15-turn window)
  - setup.sh, config.example.yaml, ESLint/Prettier, ruff/black

- **Phase 3: User Story 1 - Wake Word Voice Conversation (MVP)**
  - 5 provider implementations: sherpa-onnx STT, Kokoro TTS, Silero-VAD, OpenWakeWord, Ollama LLM
  - Pipeline orchestration: wake → VAD → STT → LLM → TTS → playback
  - Keyboard/hotkey trigger (bypass wake word)
  - Barge-in detection (wake word during SPEAKING → LISTENING)
  - Mic mute during TTS playback (MVP echo cancellation)
  - Activation sound (beep.wav) on wake
  - 5 personality presets: hacker, seductive, butler, drill-sergeant, stoner-philosopher
  - Personality injection into system prompts
  - 15-turn sliding window conversation memory
  - State change events, transcript partial/final, llm_token, llm_complete, tts_audio binary frames
  - Session manager (single active session)
  - Gateway relay: worker events → frontend
  - VRAM check warnings before model load
  - Startup ready signal (terminal message + optional chime)
  - Setup docs for WSL2, Fedora, macOS

- **Phase 4: User Story 2 - Config-Only Provider Switching**
  - 3 additional providers: faster-whisper STT, Piper TTS, OpenAI-compatible LLM (OpenRouter/OpenAI)
  - Provider factory pattern (create_provider function in __init__.py)
  - Dynamic provider loading from config.yaml
  - Config reload on PUT /api/config
  - Provider validation errors with available provider listing
  - TTS streaming with sentence-boundary chunking
  - vram_requirement_mb property on all providers
  - Updated config.example.yaml with all provider options
  - docs/provider-guide.md (how to add new STT/TTS provider)

- **Phase 5: User Story 3 - Personality Presets & Conversation Memory**
  - 5 personality YAML presets with distinct system prompts
  - Custom personality support (active: "custom" + custom_prompt)
  - Personality switching via PUT /api/config
  - GET /api/personalities endpoint
  - Conversation history persistence (15 turns, discard on restart)
  - Turn counter with oldest-turn eviction
  - LLM context building with conversation history
  - Personality selector in terminal output

- **Phase 6: User Story 4 - 3D Avatar & Web Interface**
  - 18 Svelte 5 frontend components:
    - Main page layout, avatar display (TalkingHead wrapper), waveform visualizer
    - Transcript display, status indicator, settings panel, theme frame wrapper
    - WebSocket state store, pipeline state store, talking-head loader
  - 4 themes: minimal, cyberpunk, retro-terminal, glassmorphism
  - 12 VRM avatar models bundled as static assets
  - Avatar lip-sync driven by TTS audio amplitude
  - Idle animations (blinking, eye tracking)
  - Theme switching via config
  - Avatar selection (browse library + custom upload)
  - GET /api/avatars endpoint
  - Responsive design (mobile-friendly)
  - Vite static asset serving for VRM models

- **Phase 7: Cloud API Voice Mode (US5)**: Gemini Live integration for cloud-based voice conversation
  - `pipeline_mode: cloud` in config.yaml
  - `gemini-live-adapter.ts` WebSocket proxy
  - Cloud mode gating in worker/main.py
  - `docs/gemini-live-setup.md`

- **Phase 8: Agent Integrations (US6)**: Hermes Agent and OpenClaw support
  - `hermes-adapter.ts` - WebSocket channel registration
  - `openclaw-adapter.ts` - Skill file management
  - `mcp-bridge.ts` - MCP tool invocation relay
  - Standalone mode (integrations disabled)
  - `docs/hermes-integration.md`
  - `docs/openclaw-skill.md`

---

## [1.0.0] - 2026-03-29

### Added

- **Phase 1: Setup**
  - Project structure (worker/, gateway/, frontend/)
  - Python worker with requirements.txt
  - Bun gateway with package.json
  - Svelte 5 frontend
  - config.example.yaml with defaults
  - .gitignore
  - setup.sh script
  - ESLint/Prettier for TypeScript
  - ruff/black for Python

- **Phase 2: Foundational**
  - Provider ABCs (STT, TTS, VAD, WakeWord, LLM)
  - State machine (5 states: DORMANT, TRIGGERED, LISTENING, PROCESSING, SPEAKING)
  - Config loader (Python + TypeScript)
  - Audio capture and playback
  - WebSocket hub (frontend ↔ worker relay)
  - VRAM calculator
  - REST API routes (health, config, status)
  - Structured logging (pino)
  - Streaming modules (sentence chunker, conversation memory)

- **Phase 3: User Story 1 - MVP**
  - sherpa-onnx STT provider
  - Kokoro TTS provider
  - Silero-VAD provider
  - OpenWakeWord provider ("Yo Gimp" default)
  - Ollama LLM client with streaming
  - Pipeline orchestration
  - Keyboard/hotkey trigger
  - Barge-in detection
  - Mic mute during TTS (echo cancellation)
  - Activation sound playback
  - 5 personality presets
  - 15-turn conversation memory
  - State change events
  - Transcript events (partial/final)
  - LLM token streaming
  - TTS audio frames

- **Phase 4: User Story 2 - Provider Switching**
  - faster-whisper STT provider
  - Piper TTS provider
  - OpenAI-compatible LLM (OpenRouter/OpenAI)
  - Provider factory pattern
  - Dynamic provider loading
  - Config reload via REST API
  - Provider validation errors
  - TTS streaming (sentence chunking)
  - VRAM requirements per provider

- **Phase 5: User Story 3 - Personalities**
  - 5 personality YAML presets
  - Custom personality support
  - Personality switching via API
  - GET /api/personalities endpoint
  - Conversation history persistence
  - Turn counter with eviction

- **Phase 6: User Story 4 - 3D Avatar**
  - Svelte 5 frontend components
  - TalkingHead wrapper
  - Audio waveform visualizer
  - Transcript display
  - Status indicator
  - Settings panel
  - Theme frame wrapper
  - WebSocket state store
  - Pipeline state store
  - 4 themes (minimal, cyberpunk, retro-terminal, glassmorphism)
  - Avatar library (12 VRM models)
  - Lip-sync from TTS amplitude
  - Idle animations (blinking, eye tracking)
  - Theme switching
  - Avatar selection
  - GET /api/avatars endpoint
  - Responsive design

---

## [0.1.0] - 2026-01-15

### Added

- Initial project structure
- Basic configuration loader
- Placeholder for provider ABCs
