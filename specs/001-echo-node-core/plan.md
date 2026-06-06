# Implementation Plan: Echo-Node Voice AI Interface

**Branch**: `001-echo-node-core` | **Date**: 2026-03-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-echo-node-core/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build a modular, open-source voice AI interface with wake word activation,
STT → LLM → TTS pipeline, animated 3D avatar, and agent integration.
3-layer split-stack: Python audio worker (ML inference, state machine),
Bun + Hono gateway (WebSocket relay, REST API), Svelte 5 frontend
(TalkingHead avatar, themes). Config-driven provider swapping, Gemini Live
cloud mode optional, VibeVoice-ASR support, remote client protocol for
ESP32/terminal/browser clients.

## Technical Context

**Language/Version**: Python 3.11+ (worker), Bun runtime + TypeScript (gateway), Svelte 5 (frontend)
**Primary Dependencies**: 
  - Worker: PyAudio/sounddevice, ONNX Runtime, PyTorch, sherpa-onnx, Kokoro-TTS, OpenWakeWord, Silero-VAD
  - Gateway: Hono, ws (WebSocket), yaml parser
  - Frontend: SvelteKit, TalkingHead (met4citizen), Three.js (VRM)
**Storage**: N/A (conversation history in-memory, 15-turn sliding window)
**Testing**: pytest (worker), Bun test (gateway), Vitest + Testing Library (frontend)
**Target Platform**: WSL2 (primary), native Linux (Fedora/Ubuntu), macOS, Windows via WSL2
**Project Type**: Split-stack voice AI system (CLI + Web UI modes)
**Performance Goals**: End-to-end latency ≤2s (STT ≤500ms, LLM ≤800ms, TTS ≤700ms)
**Constraints**: ≤6GB VRAM default config, MIT/Apache/BSD licenses only, localhost default (LAN optional)
**Scale/Scope**: Single-machine inference server, multiple LAN clients (ESP32, terminals, browsers)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Initial Check (Pre-Phase 0)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Stitch, Don't Rebuild | ✅ PASS | All components use existing libraries (sherpa-onnx, Kokoro, OpenWakeWord, Silero-VAD, TalkingHead) |
| II. Split-Stack Ownership | ✅ PASS | 3-layer architecture enforced: Python worker (audio/ML/state), Bun gateway (relay), Svelte frontend (visualizer) |
| III. Config-Driven Pipeline | ✅ PASS | All providers, thresholds, model paths via config.yaml with validation |
| IV. Provider Abstraction | ✅ PASS | ABCs defined for STT, TTS, VAD, WakeWord, LLM with initialize()/process()/shutdown()/vram_requirement_mb |
| V. Resource-Aware Loading | ✅ PASS | VRAM calculator before model load, CPU/OpenVINO fallback supported |
| VI. Dual-Mode Operation | ✅ PASS | Headless CLI + Web UI modes, same worker/gateway, mode selected via config |
| VII. Streaming-First Latency | ✅ PASS | STT partials, LLM token streaming, TTS sentence chunking, playback pipelining |

**GATE RESULT**: ✅ All principles satisfied. Proceeding to Phase 0.

### Post-Phase 1 Re-evaluation

| Principle | Status | Design Verification |
|-----------|--------|---------------------|
| I. Stitch, Don't Rebuild | ✅ PASS | research.md confirms all libraries are existing (VibeVoice-ASR from HuggingFace, TalkingHead bundled, Gemini Live API) |
| II. Split-Stack Ownership | ✅ PASS | data-model.md enforces layer boundaries: Worker owns state machine, Gateway relays, Frontend visualizes |
| III. Config-Driven Pipeline | ✅ PASS | Configuration entity in data-model.md includes full schema with validation rules |
| IV. Provider Abstraction | ✅ PASS | Provider entity defines 5 ABCs with required methods; registry documented |
| V. Resource-Aware Loading | ✅ PASS | VRAM calculator in research.md; VibeVoice-ASR quantization noted (18GB→6GB) |
| VI. Dual-Mode Operation | ✅ PASS | quickstart.md documents both `ui.mode: web` and `ui.mode: headless` |
| VII. Streaming-First Latency | ✅ PASS | research.md sentence chunker design; contracts/worker-protocol.md streaming events |

**GATE RESULT**: ✅ All principles satisfied post-design. Proceeding to Phase 2 (tasks.md).

## Project Structure

### Documentation (this feature)

```text
specs/001-echo-node-core/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
echo-node/
├── config.yaml                      # User configuration
├── config.example.yaml              # Documented defaults
├── README.md                        # Setup + usage
├── setup.sh                         # Install deps + download models
├── package.json                     # Bun deps (gateway + frontend)
├── bunfig.toml
│
├── gateway/                         # Layer 2: Bun + Hono
│   ├── src/
│   │   ├── index.ts                # Hono server
│   │   ├── websocket.ts            # WebSocket hub
│   │   ├── routes/                 # REST API routes
│   │   ├── integrations/           # Hermes, OpenClaw, MCP adapters
│   │   ├── sessions/               # Session manager
│   │   └── utils/                  # Config loader, logger, types
│   └── tsconfig.json
│
├── worker/                          # Layer 1: Python audio worker
│   ├── main.py                     # Entry point, WebSocket server
│   ├── state_machine.py            # 5-state machine
│   ├── pipeline.py                 # Pipeline orchestration
│   ├── config.py                   # Config loader
│   ├── providers/                  # ABCs + provider implementations
│   ├── audio/                      # Capture, playback, echo cancel
│   ├── streaming/                  # Sentence chunker, conversation memory
│   ├── personalities/              # Personality preset YAMLs
│   ├── sounds/                     # Activation sounds
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/                        # Layer 3: Svelte 5
│   ├── src/
│   │   ├── routes/
│   │   ├── lib/
│   │   │   ├── components/         # Avatar, waveform, transcript, settings
│   │   │   ├── stores/             # WebSocket, pipeline state
│   │   │   └── themes/             # Theme CSS files
│   │   └── static/
│   │       └── models/             # VRM avatar files
│   ├── svelte.config.js
│   ├── vite.config.ts
│   └── package.json
│
├── models/                          # Downloaded ML models (gitignored)
│   ├── stt/
│   ├── tts/
│   ├── vad/
│   └── wake_word/
│
└── docs/
    ├── setup-fedora.md
    ├── setup-wsl2.md
    ├── setup-macos.md
    └── provider-guide.md
```

**Structure Decision**: Split-stack monorepo with 3 layers (worker, gateway, frontend) sharing config and models directories. Single repository for co-location of all components.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | All constitution principles satisfied | N/A |
