#!/usr/bin/env bash
# Setup MuseTalk for Echo-Node local avatar video
# Downloads model weights (~8GB) and installs dependencies.
# Run once from v2/ directory:  bash avatar_video/setup.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

echo "=== Echo-Node MuseTalk Setup ==="
echo "Target: $SCRIPT_DIR/models"
echo ""

MODELS_DIR="$SCRIPT_DIR/models"
mkdir -p "$MODELS_DIR"

# ── 1. Install Python deps ──────────────────────────────────────────
echo "[1/4] Installing Python dependencies..."
"$VENV_PYTHON" -m pip install -q \
  "diffusers==0.32.2" \
  "accelerate==0.28.0" \
  "transformers==4.39.2" \
  "opencv-python==4.9.0.80" \
  "soundfile==0.12.1" \
  "librosa==0.11.0" \
  "einops==0.8.1" \
  "omegaconf" \
  "pyyaml" \
  "imageio" \
  "imageio[ffmpeg]" \
  "face-alignment" \
  "safetensors" \
  "timm" \
  "mediapipe" \
  "gdown" \
  "ffmpeg-python" \
  2>&1 | tail -3
echo "  Dependencies installed ✓"

# ── 2. Download model weights ──────────────────────────────────────
echo ""
echo "[2/4] Downloading model weights (~8 GB total)..."

"$VENV_PYTHON" - "$MODELS_DIR" << 'PYEOF'
from huggingface_hub import snapshot_download
import os, sys, urllib.request, subprocess, json, pathlib

target = pathlib.Path(sys.argv[1])

# ── MuseTalk V1.5 weights (UNet ~3.5GB, VAE, config) ────────────────────
print("  Downloading TMElyralab/MuseTalk V1.5 weights...")
snapshot_download(
    repo_id="TMElyralab/MuseTalk",
    local_dir=str(target / "MuseTalk"),
    ignore_patterns=["*.md", "*.txt", "*.gitattributes", "*.pkl"],
    allow_patterns=["musetalkV15/*", "musetalk/*.json"],
)
print("  MuseTalk V1.5 done.")

# ── Whisper tiny (audio encoder, ~150 MB) ──────────────────────────
whisper_dir = target / "whisper"
if not whisper_dir.exists():
    print("  Downloading openai/whisper-tiny...")
    snapshot_download(
        repo_id="openai/whisper-tiny",
        local_dir=str(whisper_dir),
        ignore_patterns=["*.md", "*.gitattributes", "flax_model*", "tf_model*", "rust_model*"],
    )
    print("  Whisper-tiny done.")
else:
    print("  Whisper-tiny already present ✓")

# ── SD-VAE (stabilityai/sd-vae-ft-mse, ~335 MB) ────────────────────
vae_dir = target / "sd-vae"
if not vae_dir.exists():
    print("  Downloading stabilityai/sd-vae-ft-mse...")
    snapshot_download(
        repo_id="stabilityai/sd-vae-ft-mse",
        local_dir=str(vae_dir),
        ignore_patterns=["*.md", "*.gitattributes"],
    )
    print("  SD-VAE done.")
else:
    print("  SD-VAE already present ✓")

# ── face-parse-bisent (BiSeNet face segmentation, ~100 MB) ─────────
bisent_dir = target / "face-parse-bisent"
bisent_dir.mkdir(exist_ok=True)

resnet_path = bisent_dir / "resnet18-5c106cde.pth"
if not resnet_path.exists():
    print("  Downloading ResNet18 backbone...")
    urllib.request.urlretrieve(
        "https://download.pytorch.org/models/resnet18-5c106cde.pth",
        str(resnet_path),
    )
else:
    print("  ResNet18 already present ✓")

bisenet_path = bisent_dir / "79999_iter.pth"
if not bisenet_path.exists():
    print("  Downloading BiSeNet face parser via gdown...")
    import gdown
    gdown.download(id="154JgKpzCPW82qINcVieuPH3fZ2e0P812", output=str(bisenet_path), quiet=False)
else:
    print("  BiSeNet already present ✓")

# ── Write a manifest for easy loading ──────────────────────────────
manifest = {
    "musetalk_dir": str(target / "MuseTalk"),
    "unet_path": str(target / "MuseTalk" / "musetalkV15" / "unet.pth"),
    "unet_config": str(target / "MuseTalk" / "musetalkV15" / "musetalk.json"),
    "vae_dir": str(vae_dir),
    "whisper_dir": str(whisper_dir),
    "bisent_dir": str(bisent_dir),
}
(target / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"  Manifest written ✓")
print("  All downloads complete!")
PYEOF

# ── 3. Verify ──────────────────────────────────────────────────────
echo ""
echo "[3/4] Verifying downloads..."
python3 -c "
import json, pathlib
m = json.loads(pathlib.Path('$MODELS_DIR/manifest.json').read_text())
for k, v in m.items():
    ok = pathlib.Path(v).exists()
    print(f'  {\"✓\" if ok else \"✗\"} {k}: {v}')
"

# ── 4. Test import ─────────────────────────────────────────────────
echo ""
echo "[4/4] Testing import..."
"$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$MODELS_DIR')
# Just check key deps
import torch
import cv2
import librosa
import face_alignment
import einops
import omegaconf
print('  All imports OK ✓')
print(f'  torch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')
# Show model sizes
import os
for d, label in [('MuseTalk/musetalkV15', 'UNet+VAE'),
                  ('whisper', 'Whisper'),
                  ('sd-vae', 'SD-VAE'),
                  ('face-parse-bisent', 'BiSeNet')]:
    p = os.path.join('$MODELS_DIR', d)
    if os.path.exists(p):
        size_mb = sum(os.path.getsize(os.path.join(dp,f)) for dp,_,fn in os.walk(p) for f in fn) / 1e6
        print(f'  {label}: {size_mb:.0f} MB')
" 2>&1 | tail -10

echo ""
echo "=== Setup complete! ==="
echo "Models in: $MODELS_DIR"
echo "Run test:  $VENV_PYTHON avatar_video/test_musetalk.py"
