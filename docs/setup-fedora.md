# Fedora Linux Setup for Echo-Node

**Purpose**: Native Fedora Linux audio and dependency setup.

---

## Quick Start

```bash
# Install system dependencies
sudo dnf install -y python3 python3-pip python3-devel \
    portaudio-devel pipewire pipewire-devel \
    bun nodejs

# Clone and setup
git clone <repo-url> echo-node
cd echo-node
./setup.sh
```

---

## Audio Configuration

### Fedora 43 (WSLg or Native)

Fedora 43 uses PipeWire by default. No additional configuration needed.

```bash
# Verify PipeWire is running
pw-cli --version

# Test microphone
arecord -d 5 test.wav
aplay test.wav
```

### Older Fedora (41/42)

```bash
# Install PipeWire
sudo dnf install pipewire pipewire-devel pipewire-utils

# Enable PipeWire
systemctl --user enable --now pipewire pipewire-pulse

# Test audio
arecord -l  # List capture devices
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

### Optional: NVIDIA CUDA Support

```bash
# Install NVIDIA drivers (if using proprietary drivers)
sudo dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda

# Install CUDA toolkit
sudo dnf install cuda-toolkit

# Install pynvml for VRAM monitoring
pip install pynvml
```

---

## Ollama Setup (Local LLM)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.2:7b-q4_K_M

# Start Ollama service
ollama serve
```

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

### "No audio device found"

```bash
# Check PipeWire status
systemctl --user status pipewire

# Restart PipeWire
systemctl --user restart pipewire pipewire-pulse

# List audio devices
arecord -l
aplay -l
```

### "Permission denied" for microphone

```bash
# Add user to audio group
sudo usermod -aG audio $USER

# Log out and back in
```

### Ollama Connection Refused

```bash
# Check Ollama is running
systemctl status ollama

# Start Ollama
ollama serve
```

---

## Performance Tips

### Reduce Audio Latency

Edit `/etc/pipewire/pipewire.conf.d/99-low-latency.conf`:

```text
default.clock.rate = 48000
default.clock.quantum = 256
default.clock.min-quantum = 128
default.clock.max-quantum = 512
```

### GPU Acceleration

Verify CUDA is available:

```bash
nvidia-smi
python3 -c "import torch; print(torch.cuda.is_available())"
```

---

## Next Steps

- [Setup WSL2](setup-wsl2.md) - WSL2 audio configuration
- [Setup macOS](setup-macos.md) - macOS audio setup
- [Quickstart](../quickstart.md) - Get started with Echo-Node
