# macOS Setup for Echo-Node

**Purpose**: macOS audio and dependency setup.

---

## Quick Start

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.11 bun portaudio

# Clone and setup
git clone <repo-url> echo-node
cd echo-node
./setup.sh
```

---

## Audio Configuration

macOS has built-in audio support via Core Audio. No additional configuration needed.

```bash
# Test microphone
rec -d 5 test.wav
play test.wav

# Or use sox
brew install sox
rec -d 5 test.wav
```

---

## Python Dependencies

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
cd worker
pip install -r requirements.txt
```

### Note: No NVIDIA GPU on macOS

macOS does not support CUDA. Echo-Node will use CPU fallback or Metal acceleration where available.

In `config.yaml`:

```yaml
stt:
  device: cpu  # or 'openvino' if using Intel Mac

tts:
  device: cpu

llm:
  provider: ollama  # Ollama supports Metal on macOS
```

---

## Ollama Setup (Local LLM)

```bash
# Install Ollama
brew install ollama

# Pull model (optimized for Apple Silicon)
ollama pull llama3.2:7b-q4_K_M

# Start Ollama
ollama serve
```

Ollama on macOS uses Metal acceleration automatically on Apple Silicon.

---

## Run Echo-Node

```bash
# Terminal 1: Worker
cd worker
source .venv/bin/activate
python main.py

# Terminal 2: Gateway
cd gateway
bun run src/index.ts

# Terminal 3: Frontend (optional)
cd frontend
bun run dev
```

Open http://localhost:5173 for web UI.

---

## Troubleshooting

### "PortAudio not found"

```bash
# Install via Homebrew
brew install portaudio

# If still not found, specify path
export CFLAGS="-I$(brew --prefix portaudio)/include"
export LDFLAGS="-L$(brew --prefix portaudio)/lib"
pip install pyaudio
```

### "Microphone access denied"

macOS requires microphone permission:

1. Go to **System Settings** → **Privacy & Security** → **Microphone**
2. Enable microphone access for Terminal (or your IDE)
3. Restart Terminal

### "No audio output"

```bash
# Check audio output device
brew install switchaudio-osx
switchaudio-osx -c

# List output devices
switchaudio-osx -t output -l
```

---

## Performance Tips

### Apple Silicon Optimization

Use quantized models for better performance:

```yaml
llm:
  model: llama3.2:7b-q4_K_M  # 4-bit quantized
  # Not: llama3.2:7b (full precision, slower)
```

### Reduce Memory Pressure

macOS shares RAM between CPU and GPU. Use smaller models:

```yaml
stt:
  provider: sherpa-onnx  # Lighter than VibeVoice

tts:
  provider: kokoro  # 82M params, fits easily
```

---

## Next Steps

- [Setup WSL2](setup-wsl2.md) - WSL2 audio configuration
- [Setup Fedora](setup-fedora.md) - Native Fedora Linux
- [Quickstart](../quickstart.md) - Get started with Echo-Node
