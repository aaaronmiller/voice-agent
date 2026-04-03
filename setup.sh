#!/bin/bash
# Echo-Node Setup Script
# Installs dependencies and downloads default models

set -e

echo "🎯 Echo-Node Setup"
echo "=================="

# Detect OS
OS="$(uname -s)"
echo "Detected OS: $OS"

# Check for WSL2
if grep -q "WSL" /proc/version 2>/dev/null; then
    echo "🐧 WSL2 detected - checking audio configuration..."
    if command -v pw-cli &> /dev/null; then
        echo "✅ PipeWire detected"
    elif command -v pactl &> /dev/null; then
        echo "✅ PulseAudio detected"
    else
        echo "⚠️  No audio server detected. Install PipeWire or PulseAudio for WSL2 audio."
        echo "   Ubuntu: sudo apt install pulseaudio"
        echo "   Fedora: sudo dnf install pipewire"
    fi
fi

# Create models directory
echo ""
echo "📁 Creating models directory..."
mkdir -p models/{stt,tts,vad,wake_word}

# Install Python dependencies
echo ""
echo "🐍 Installing Python dependencies..."
cd worker
if [ -d ".venv" ]; then
    echo "  - Existing virtualenv found, reusing..."
    source .venv/bin/activate
else
    python3 -m venv .venv
    source .venv/bin/activate
fi
pip install --upgrade pip
pip install -r requirements.txt
cd ..

# Install Bun dependencies (gateway)
echo ""
echo "📦 Installing Bun gateway dependencies..."
cd gateway
bun install
cd ..

# Install Bun dependencies (frontend)
echo ""
echo "🎨 Installing Svelte frontend dependencies..."
cd frontend
bun install
cd ..

# Download default models
echo ""
echo "📥 Downloading default models..."

# Silero VAD
echo "  - Silero VAD..."
curl -L "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx" -o models/vad/silero_vad.onnx

# OpenWakeWord (yo_gimp model - placeholder, user should train custom)
echo "  - OpenWakeWord (placeholder)..."
# User should train custom wake word with OpenWakeWord training pipeline
# For now, create placeholder
touch models/wake_word/yo_gimp.onnx.placeholder
echo "⚠️  OpenWakeWord placeholder created. Train custom wake word at: https://github.com/dscripka/openWakeWord"

# Sherpa-ONNX STT model
echo "  - Sherpa-ONNX STT model (this may take a while)..."
SHERPA_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2"
curl -L "$SHERPA_URL" -o /tmp/sherpa-model.tar.bz2
tar -xjf /tmp/sherpa-model.tar.bz2 -C models/stt/
rm /tmp/sherpa-model.tar.bz2

# Kokoro TTS model
echo "  - Kokoro TTS model..."
# Kokoro model download (placeholder - actual download depends on availability)
# User may need to download manually from HuggingFace
echo "⚠️  Kokoro TTS model: Download manually from HuggingFace if not auto-downloaded"
echo "   https://huggingface.co/kokoro-82m/kokoro-v1.0"

# Cleanup
rm -rf /tmp/sherpa-model.tar.bz2

# Create config.yaml from example
echo ""
echo "⚙️  Creating config.yaml..."
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo "✅ config.yaml created from config.example.yaml"
else
    echo "ℹ️  config.yaml already exists - skipping"
fi

# Create activation sound files
echo ""
echo "🔔 Creating activation sounds..."
# Generate simple beep using Python
python3 << 'EOF'
import numpy as np
import wave
import struct

sample_rate = 24000
duration = 0.1  # 100ms
frequency = 880  # A5

t = np.linspace(0, duration, int(sample_rate * duration))
audio = 0.5 * np.sin(2 * np.pi * frequency * t)
audio = audio.astype(np.float32)

with wave.open('worker/sounds/beep.wav', 'w') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    for sample in audio:
        wav.writeframes(struct.pack('<h', int(sample * 32767)))

print("✅ beep.wav created")
EOF

# Create chime sound (placeholder)
cp worker/sounds/beep.wav worker/sounds/chime.wav 2>/dev/null || echo "⚠️  Chime sound: copy beep.wav manually"

# Final instructions
echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml to customize your setup"
echo "2. Download Ollama model: ollama pull llama3.2:7b-q4_K_M"
echo "3. (Optional) Train custom wake word with OpenWakeWord"
echo "4. Run: bun run dev"
echo ""
echo "For WSL2 audio setup, see docs/setup-wsl2.md"
