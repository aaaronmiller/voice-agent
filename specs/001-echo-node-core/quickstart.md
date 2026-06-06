# Quickstart: Echo-Node

**Version**: 1.0.0
**Last Updated**: 2026-03-29

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | WSL2 (Ubuntu 24.04), Fedora 43, macOS 14+ | WSL2 on Windows 11 |
| GPU | Integrated graphics (CPU mode) | NVIDIA RTX 4050 (6GB VRAM) |
| RAM | 8GB | 16GB |
| Storage | 10GB free | 20GB free (SSD) |
| Python | 3.11+ | 3.12 |
| Node | Bun 1.0+ | Bun 1.5+ |

### Audio Setup (WSL2)

```bash
# Check for PipeWire (Fedora 43 WSLg has this built-in)
pw-cli --version

# If not found, install PulseAudio (Ubuntu)
sudo apt update && sudo apt install pulseaudio

# Test microphone access
arecord -l  # List capture devices
```

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/your-org/echo-node.git
cd echo-node
```

### 2. Run Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

This will:
- Install Python dependencies (`worker/requirements.txt`)
- Install Bun dependencies (`package.json`)
- Download default models (sherpa-onnx, Kokoro, Silero-VAD, OpenWakeWord)
- Create `config.yaml` from `config.example.yaml`

### 3. Configure

Edit `config.yaml`:

```yaml
# Minimal config for local testing
echo_node:
  name: "Gimp"

stt:
  provider: sherpa-onnx

tts:
  provider: kokoro
  voice: af_heart

llm:
  provider: ollama
  model: llama3.2:7b-q4_K_M
  base_url: http://localhost:11434/v1
  api_key: ""  # Blank for Ollama

wake_word:
  provider: openwakeword
  model: yo_gimp  # Default: "Yo Gimp"

ui:
  mode: web  # or "headless" for terminal-only
```

### 4. Pull Ollama Model (if using local LLM)

```bash
ollama pull llama3.2:7b-q4_K_M
```

---

## Usage

### Start the System

```bash
# Start all components (worker + gateway + frontend)
bun run dev

# Or start individually:
# Terminal 1: Worker
cd worker && python main.py

# Terminal 2: Gateway
cd gateway && bun run src/index.ts

# Terminal 3: Frontend (if web mode)
cd frontend && bun run dev
```

### Web UI Mode

1. Open browser: `http://localhost:3000`
2. Allow microphone access when prompted
3. Say "Yo Gimp" or press spacebar to trigger
4. Speak your question
5. Wait for spoken response + avatar animation

### Headless CLI Mode

```yaml
# In config.yaml:
ui:
  mode: headless
```

```bash
# Start system
bun run dev

# Terminal output:
[INFO] Echo-Node starting...
[INFO] Loading STT provider: sherpa-onnx
[INFO] Loading TTS provider: kokoro
[INFO] VRAM check: 4096MB used, 2048MB available
[INFO] System ready. Say "Yo Gimp" to activate.

# After wake word:
[LISTENING] ...
[TRANSCRIPT] What's the weather like?
[PROCESSING] ...
[SPEAKING] The weather is currently...
```

---

## Configuration Examples

### Switch STT Provider

```yaml
stt:
  provider: faster-whisper
  model: base-en
  device: cuda
```

### Use Cloud LLM (OpenRouter)

```yaml
llm:
  provider: openai-compat
  model: meta-llama/llama-3-70b-instruct
  base_url: https://openrouter.ai/api/v1
  api_key: sk-or-xxx  # Your OpenRouter key
```

### Use Gemini Live Mode (Cloud Audio-to-Audio)

```yaml
pipeline_mode: cloud

llm:
  provider: gemini-live
  model: gemini-3.1-flash-live-preview
  api_key: YOUR_GEMINI_KEY  # Required
```

### Change Personality

```yaml
personality:
  active: hacker
```

### LAN Access (Remote Clients)

```yaml
gateway:
  port: 3000
  bind: 0.0.0.0  # Default: 127.0.0.1

ui:
  port: 3000
```

---

## Troubleshooting

### "No audio device found"

**WSL2**: Ensure PipeWire/PulseAudio is installed and running.

```bash
# Ubuntu WSL2
sudo apt install pulseaudio
pulseaudio --start

# Test capture
arecord -d 5 test.wav
aplay test.wav
```

### "VRAM exceeded"

Reduce model size or use CPU fallback:

```yaml
stt:
  provider: sherpa-onnx
  device: cpu  # Instead of cuda

tts:
  provider: kokoro  # Smallest TTS (82M params)
```

### "Provider not found"

Check provider name spelling. Available providers:

```bash
# Worker will log available providers at startup
[INFO] Available STT providers: sherpa-onnx, faster-whisper, vibevoice-asr
```

### Ollama Connection Refused

Ensure Ollama is running and accessible:

```bash
ollama serve  # Terminal 1
ollama list   # Verify model is downloaded
```

---

## Next Steps

1. **Customize Personality**: Create `worker/personalities/my-custom.yaml`
2. **Add Avatar**: Place `.vrm` file in `frontend/src/static/models/`
3. **Train Wake Word**: Use OpenWakeWord training pipeline for custom keyword
4. **Integrate Hermes**: Enable `integrations.hermes.enabled: true`
5. **Remote Access**: Configure `gateway.bind: 0.0.0.0` and connect from LAN device

---

## Command Reference

| Command | Description |
|---------|-------------|
| `bun run dev` | Start all components (worker + gateway + frontend) |
| `bun run worker` | Start Python worker only |
| `bun run gateway` | Start Bun gateway only |
| `bun run frontend` | Start Svelte frontend only |
| `./setup.sh` | Install dependencies + download models |
| `ollama pull <model>` | Download Ollama model |

---

## Support

- **Documentation**: `docs/` directory
- **Provider Guide**: `docs/provider-guide.md`
- **Platform Setup**: `docs/setup-fedora.md`, `docs/setup-wsl2.md`, `docs/setup-macos.md`
- **GitHub Issues**: https://github.com/your-org/echo-node/issues
