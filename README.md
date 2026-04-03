# Echo-Node

**Modular Open-Source Voice AI Interface**

Wake word activation → STT → LLM → TTS pipeline with animated 3D avatar.

---

## Quick Start

### 1. Run Setup

```bash
./setup.sh
```

This will:
- Install Python dependencies (worker)
- Install Bun dependencies (gateway + frontend)
- Download default models (STT, TTS, VAD, wake word)
- Create config.yaml from example

### 2. Configure

Edit `config.yaml`:

```yaml
llm:
  provider: ollama
  model: llama3.2:7b-q4_K_M
  base_url: http://localhost:11434/v1

# Or use cloud LLM:
# llm:
#   provider: openai-compat
#   base_url: https://openrouter.ai/api/v1
#   api_key: sk-or-xxx
```

### 3. Start Ollama (if using local LLM)

```bash
ollama pull llama3.2:7b-q4_K_M
ollama serve
```

### 4. Run Echo-Node

```bash
# Terminal 1: Worker
cd worker
python main.py

# Terminal 2: Gateway
cd gateway
bun run src/index.ts

# Terminal 3: Frontend (optional - web UI mode)
cd frontend
bun run dev
```

Or use the dev script (all-in-one):

```bash
bun run dev
```

### 5. Use

**Headless (terminal) mode:**

```bash
# In config.yaml: ui.mode: headless
# Then say wake word: "Yo Gimp"
# Ask question, hear response
```

**Web UI mode:**

```bash
# In config.yaml: ui.mode: web
# Open http://localhost:5173
# Click mic or say wake word
```

---

## Architecture

```
┌─────────────────┐     WebSocket      ┌─────────────────┐
│   Frontend      │◄──────────────────►│    Gateway      │
│   (Svelte 5)    │   JSON events      │   (Bun + Hono)  │
│   Avatar + UI   │                    │   REST + WS     │
└─────────────────┘                    └────────┬────────┘
                                                │
                                       WebSocket
                                    binary + JSON
                                                │
                                       ┌────────▼────────┐
                                       │    Worker       │
                                       │   (Python)      │
                                       │  STT/TTS/LLM    │
                                       └─────────────────┘
```

---

## Configuration

See `config.example.yaml` for all options:

| Section | Description |
|---------|-------------|
| `pipeline_mode` | `local` (modular) or `cloud` (Gemini Live) |
| `stt.provider` | `sherpa-onnx`, `faster-whisper`, `vibevoice-asr` |
| `tts.provider` | `kokoro`, `chatterbox`, `orpheus`, `piper` |
| `llm.provider` | `ollama`, `openai-compat` |
| `wake_word.provider` | `openwakeword` |
| `personality.active` | `hacker`, `seductive`, `butler`, `drill-sergeant`, `stoner-philosopher` |
| `ui.mode` | `web` or `headless` |

---

## Features

- ✅ Wake word activation ("Yo Gimp" default)
- ✅ Keyboard/hotkey trigger
- ✅ Streaming STT → LLM → TTS pipeline
- ✅ ≤2 second latency target
- ✅ Config-only provider swapping
- ✅ 5 personality presets
- ✅ 15-turn conversation memory
- ✅ VRAM-aware model loading
- ✅ WSL2 audio auto-detection
- ✅ 3D VRM avatar with lip-sync (web mode)
- ✅ Cloud API mode (Gemini Live) - Phase 3
- ✅ Hermes Agent integration - Phase 3
- ✅ OpenClaw skill - Phase 3

---

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | WSL2, Linux, macOS | WSL2 on Windows 11 |
| GPU | Integrated (CPU mode) | NVIDIA RTX 4050 (6GB VRAM) |
| RAM | 8GB | 16GB |
| Python | 3.11+ | 3.12 |
| Node | Bun 1.0+ | Bun 1.5+ |

---

## Documentation

- `docs/setup-wsl2.md` - WSL2 audio configuration
- `docs/setup-fedora.md` - Fedora Linux setup
- `docs/setup-macos.md` - macOS setup
- `docs/provider-guide.md` - Adding custom providers
- `quickstart.md` - Detailed quickstart guide

---

## License

MIT - All dependencies must be MIT, Apache 2.0, or BSD licensed.

---

## Status

**Phase 2 Complete** - Foundational infrastructure ready.

- [x] Phase 1: Setup
- [x] Phase 2: Foundational (ABCs, state machine, audio, WebSocket, REST API)
- [ ] Phase 3: User Story 1 (Wake Word Voice Conversation - MVP)
- [ ] Phase 4: User Story 2 (Config-Only Provider Switching)
- [ ] Phase 5: User Story 3 (Personality + Memory)
- [ ] Phase 6: User Story 4 (3D Avatar + Web UI)
- [ ] Phase 7: User Story 5 (Cloud API Mode)
- [ ] Phase 8: User Story 6 (Agent Integration)
