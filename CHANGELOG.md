# Changelog

All notable changes to Echo-Node will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Cloud API Mode (US5)**: Gemini Live integration for cloud-based voice conversation
  - `pipeline_mode: cloud` in config.yaml
  - `gemini-live-adapter.ts` WebSocket proxy
  - Cloud mode gating in worker/main.py
  - `docs/gemini-live-setup.md`

- **Agent Integrations (US6)**: Hermes Agent and OpenClaw support
  - `hermes-adapter.ts` - WebSocket channel registration
  - `openclaw-adapter.ts` - Skill file management
  - `mcp-bridge.ts` - MCP tool invocation relay
  - Standalone mode (integrations disabled)
  - `docs/hermes-integration.md`
  - `docs/openclaw-skill.md`

- **Configuration**:
  - `pipeline_mode` validation in worker/config.py
  - Integration toggles in config.example.yaml

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
