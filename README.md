# Echo-Node — 3-Tier Local Voice AI System

> **Status:** Functional architecture with skeleton providers. Not production-ready — significant implementation gaps in model loading and audio synthesis.

Echo-Node is a local-first voice AI pipeline with a 3-tier design: **worker** (audio + ML inference) → **gateway** (websocket hub + REST API) → **frontend** (Svelte5 UI). It supports wake word detection, streaming STT, streaming LLM, streaming TTS, barge-in interruption, personality system prompts, and optional cloud mode (Gemini Live).

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        ECHO-NODE PIPELINE                     │
│                                                                 │
│  Tier 1: WORKER (Python, port 9001)                           │
│  ┌─────────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌───────┐  │
│  │  Audio  │→│ VAD │→│ STT │→│ LLM │→│ TTS │→│ Audio │  │
│  │ Capture │  │     │  │     │  │     │  │     │  │ Out   │  │
│  └─────────┘  └─────┘  └─────┘  └─────┘  └─────┘  └───────┘  │
│     │          ▲         │                                │   │
│     │   Wake Word ◄──────┘                                │   │
│     │   (openwakeword)                                    │   │
│     └─────────────────────────────────────────────────────┘   │
│              ▲                                                │
│              │ WebSocket (aiohttp)                            │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Tier 2: GATEWAY (Bun/Hono, port 3000)                        │
│  ┌──────────────┐  ┌───────────┐  ┌─────────────────────────┐ │
│  │ WebSocket Hub│←→│ REST API  │  │ Integrations            │ │
│  │ (relay)      │  │ /health   │  │ - Hermes AI (optional)  │ │
│  │              │  │ /config   │  │ - OpenClaw skills (opt) │ │
│  │ Frontend ←───┘  │ /status   │  │ - MCP bridge (optional) │ │
│  │ Worker   ◄──────│ /personalities│ Gemini Live Adapter     │ │
│  │ ESP32 (opt)     │ /avatars  │  └─────────────────────────┘ │
│  └──────────────┘  └───────────┘                              │
│                                                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Tier 3: FRONTEND (Svelte5 + Vite)                           │
│  ┌──────────────────┐ ┌────────────────┐                      │
│  │ Waveform Display │ │ Transcript Log │                      │
│  │ Status Indicator  │ │ Settings Panel │                      │
│  │ Avatar Display   │ │ Pipeline State │                      │
│  └──────────────────┘ └────────────────┘                      │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

## Pipeline State Machine

The worker drives a 5-state machine that orchestrates the conversation cycle:

```
DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING → DORMANT
                                    ↑              ↓
                                    └── barge-in ──┘
```

| State | Description |
|-------|-------------|
| `DORMANT` | Idle, listening for wake word |
| `TRIGGERED` | Wake word detected, playing activation chime |
| `LISTENING` | VAD active, capturing speech to STT |
| `PROCESSING` | STT → LLM → TTS pipeline running |
| `SPEAKING` | TTS audio playback, barge-in enabled |

Barge-in allows the user to interrupt mid-speech, returning to `LISTENING`.

## Directory Structure

```
voice-agent/
├── worker/                      # Python ML worker
│   ├── main.py                  # Entry point — aiohttp WebSocket server on port 9001
│   ├── pipeline.py              # Voice pipeline orchestrator
│   ├── state_machine.py         # 5-state machine
│   ├── config.py                # YAML config loader with validation
│   ├── vram_calculator.py       # GPU VRAM estimator
│   ├── audio/
│   │   ├── capture.py           # Microphone capture (sounddevice/PyAudio, WSL2-aware)
│   │   ├── playback.py          # Audio playback
│   │   └── echo_cancel.py       # Echo cancellation (stub)
│   ├── providers/
│   │   ├── base.py              # ABC interfaces: STTProvider, TTSProvider, VADProvider, WakeWordProvider, LLMProvider
│   │   ├── stt/
│   │   │   ├── sherpa_stt.py    # REAL — Sherpa-ONNX streaming STT (Zipformer)
│   │   │   ├── faster_whisper_stt.py  # SKELETON — model loading + transcribe commented out
│   │   │   └── vibevoice_asr.py       # SKELETON — stub
│   │   ├── tts/
│   │   │   ├── kokoro_tts.py    # PLACEMENT — model loads if ONNX found, but synthesizes silence as fallback
│   │   │   └── piper_tts.py     # SKELETON — model loading commented out, returns silence
│   │   ├── vad/
│   │   │   └── silero_vad.py    # REAL — torch.hub.load with energy-based fallback
│   │   ├── wake_word/
│   │   │   └── openwakeword.py  # Implementation present (tflite)
│   │   └── llm/
│   │       ├── ollama_llm.py    # REAL — full streaming chat via Ollama API
│   │       └── openai_compat_llm.py  # REAL — OpenAI-compatible streaming
│   ├── streaming/
│   │   ├── conversation/
│   │   │   └── memory.py        # Conversation memory with turn limits
│   │   └── sentence_chunker.py  # Sentence-level chunking for TTS streaming
│   ├── personalities/           # YAML personality files
│   │   ├── hacker.yaml
│   │   ├── butler.yaml
│   │   ├── drill-sergeant.yaml
│   │   ├── seductive.yaml
│   │   └── stoner-philosopher.yaml
│   ├── download_models.py       # Model download helper
│   └── requirements.txt         # Python dependencies
│
├── gateway/                     # Bun/Hono server
│   ├── src/
│   │   ├── index.ts             # Entry point — Hono app on port 3000
│   │   ├── websocket.ts         # WebSocket hub (frontend ↔ worker relay, ESP32 protocol)
│   │   ├── routes/
│   │   │   ├── health.ts        # /api/health
│   │   │   ├── config.ts        # /api/config GET/PUT
│   │   │   ├── status.ts        # /api/status
│   │   │   ├── personalities.ts # /api/personalities
│   │   │   └── avatars.ts       # /api/avatars
│   │   ├── integrations/
│   │   │   ├── hermes-adapter.ts
│   │   │   ├── openclaw-adapter.ts
│   │   │   ├── mcp-bridge.ts
│   │   │   └── gemini-live-adapter.ts
│   │   ├── sessions/session-manager.ts
│   │   └── utils/
│   │       ├── config-loader.ts
│   │       ├── logger.ts
│   │       └── types.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── config.yaml
│
├── frontend/                    # Svelte5 + Vite
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +layout.svelte
│   │   │   ├── +layout.ts
│   │   │   └── +page.svelte
│   │   └── lib/
│   │       ├── components/
│   │       │   ├── waveform.svelte
│   │       │   ├── status-indicator.svelte
│   │       │   ├── transcript.svelte
│   │       │   ├── settings-panel.svelte
│   │       │   ├── frame.svelte
│   │       │   └── avatar-display.svelte
│   │       ├── stores/
│   │       │   ├── websocket.svelte.ts
│   │       │   └── pipeline-state.svelte.ts
│   │       └── utils/
│   │           ├── audio.ts
│   │           └── talking-head-loader.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── build/                   # Pre-built output (no model files shipped)
│
├── config.yaml                  # Main config (optimized for 4GB VRAM)
├── config.example.yaml          # Default config template
└── docs/                        # Setup guides for Fedora, macOS, WSL2
```

## Provider Status

| Provider | Component | Status | Details |
|----------|-----------|--------|---------|
| **Sherpa-ONNX STT** | `sherpa_stt.py` | **IMPLEMENTED** | Full streaming transcribe, requires downloadable Zipformer model ONNX files |
| **Faster-Whisper STT** | `faster_whisper_stt.py` | **SKELETON** | Model loading and transcribe calls are commented out; returns placeholder text |
| **VibeVoice ASR** | `vibevoice_asr.py` | **SKELETON** | Stub only |
| **Silero VAD** | `silero_vad.py` | **IMPLEMENTED** | torch.hub.load with energy-based fallback — functional |
| **openwakeword** | `openwakeword.py` | **IMPLEMENTED** | TFLite-based wake word detection present |
| **Kokoro TTS** | `kokoro_tts.py` | **PLACEMENT** | ONNX model loading works, but the text-to-audio synthesis inputs are wrong (raw byte encoding — not proper tokenization). Falls back to silence when real model is loaded |
| **Piper TTS** | `piper_tts.py` | **SKELETON** | Model loading commented out, returns pure silence arrays |
| **Ollama LLM** | `ollama_llm.py` | **IMPLEMENTED** | Full streaming chat via `/api/chat`, including model discovery and error handling |
| **OpenAI-Compatible LLM** | `openai_compat_llm.py` | **IMPLEMENTED** | Streaming OpenAI-format API client |

## What Works

- **State machine** — well-designed, thread-safe 5-state machine with transition validation
- **Audio capture** — sounddevice with PyAudio fallback, WSL2 auto-detection, async streaming
- **Ollama LLM** — complete streaming chat implementation with model discovery
- **Silero VAD** — torch.hub integration with graceful energy-based fallback
- **Gateway** — clean Hono app with WebSocket relay, REST API, config validation
- **Frontend** — Svelte5 components with reactive stores for pipeline state and WebSocket
- **Configuration system** — YAML-based with nested key access and validation
- **Pipeline orchestrator** — wake word → VAD → STT → LLM → (sentence-chunked) TTS → playback
- **Barge-in support** — interrupt TTS playback to return to listening
- **Personality system** — YAML system prompts with fallback hardcoding
- **Conversation memory** — turn-limited with history management
- **Cloud mode** — Gemini Live relay architecture is wired in
- **ESP32 protocol** — binary audio frame parser/builder for embedded devices

## What Doesn't / What's Missing

- **Faster-Whisper STT** — the `WhisperModel.__init__` and `transcribe()` calls are commented out; returns `[faster-whisper segment]` as fake text
- **Kokoro TTS** — passes raw UTF-8 bytes as model input instead of proper phoneme/token encoding; the model path lookup and ONNX loading exist but synthesize produces silence
- **Piper TTS** — `PiperVoice.load()` is commented out; returns zeroed numpy arrays
- **VibeVoice ASR** — stub only
- **Echo cancellation** — `echo_cancel.py` has a "SpeexDSP integration pending" placeholder
- **Activation sounds** — startup chime and wake word beep are print statements only, no audio playback
- **Gateway → Worker WebSocket** — `connectToWorker()` logs "deferred (Bun limitation)" and sets `workerConnection = null`; the actual worker-to-gateway connection exists as an aiohttp server the worker exposes, but the gateway's client-side connection to reach it is never established (Bun's WebSocket API doesn't support client connections natively in the way written). The worker is designed as a **server** (accepting connections), while the gateway code tries to be a **client** to it — the two don't connect automatically
- **Frontend build** — the `build/` directory is a stub with no actual model files or full static output
- **No real test suite** — no pytest files exist

## Dependencies

### Worker (Python)
- `sounddevice` or `PyAudio` — audio capture
- `numpy` — audio processing
- `aiohttp` — async WebSocket server
- `pyyaml` — config parsing
- `torch` — Silero VAD (can fall back to energy detection)
- `sherpa-onnx` — streaming STT
- `openwakeword` — wake word detection
- `aiohttp` + `httpx`-style — LLM API calls
- `onnxruntime-gpu` (optional) — Kokoro TTS acceleration
- `pynvml` — NVIDIA VRAM monitoring

### Gateway (Bun)
- `bun` runtime
- `hono` — web framework
- `pino` — structured logging

### Frontend
- `svelte@5` — frontend framework
- `vite` — build tool
- `sveltekit` — routing

## Getting Started

```bash
# 1. Install Bun (for gateway)
curl -fsSL https://bun.sh/install | bash

# 2. Install gateway dependencies
cd voice-agent/gateway && bun install

# 3. Install Python worker dependencies
cd ../worker
pip install -r requirements.txt

# 4. Download model files (requires manual step — run the download helper)
python download_models.py

# 5. Start worker (port 9001)
python -m worker.main

# 6. Start gateway (port 3000)
cd gateway && bun run src/index.ts

# 7. (Optional) Start frontend for UI
cd ../frontend && npm install && npm run dev
```

## Configuration

All behavior is controlled via `config.yaml`. The shipped config is tuned for **4GB VRAM** (e.g., RTX 3050 laptop) using:
- Sherpa-ONNX Zipformer STT (~500MB)
- Kokoro TTS (~256MB)
- Silero VAD (~50MB)
- Ollama with Phi-4 q4 (~3GB)
- Wake word openwakeword (~100MB)

Two pipeline modes:
- `"local"` — all local providers (default)
- `"cloud"` — Gemini Live relay (worker acts as audio bridge only)

## Verdict

This is a **legitimate architectural skeleton with real scaffolding** — not legacy garbage. The structure is sound: provider ABCs, streaming pipeline, state machine, async I/O, WebSocket relay, and Svelte5 reactive UI are all properly organized.

However, it is **not production-functional** as shipped. The most critical gaps are:
1. **STT gap**: Faster-Whisper is commented out; Sherpa-ONNX requires external model ONNX files to be downloaded
2. **TTS gap**: Both Kokoro and Piper return silence or placeholder; actual text-to-speech inference is not wired
3. **Connection gap**: Gateway doesn't auto-connect to the worker WebSocket server
4. **Audio gap**: Activation sounds don't play; echo cancellation is a stub

The project sits at a **"Phase 2 / design-complete"** stage. The architecture is production-grade; the provider implementations are ~60-70% complete. A developer who can wire up the actual model inference calls and fix the gateway WebSocket connection would have a working voice AI system.
