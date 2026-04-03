#!/usr/bin/env python3
"""
Echo-Node Model Downloader

Downloads all required models for the voice pipeline.
Handles ~4GB VRAM budget with quality/performance balance.
"""

import os
import sys
import urllib.request
import tarfile
import zipfile
from pathlib import Path
import shutil

MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

# Model configurations with VRAM estimates
# Total budget: ~4GB VRAM
MODELS = {
    # STT: ~1GB - Fast streaming Zipformer
    "stt": {
        "name": "sherpa-onnx-streaming-zipformer-en-2023-06-26",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2",
        "size_mb": 120,
        "vram_mb": 500,
    },
    # TTS: ~350MB - Kokoro is tiny and fast
    "tts_kokoro": {
        "name": "kokoro-v1.0",
        "url": "https://github.com/remsky/kokoro-onnx/releases/download/v1.0/kokoro-v1.0-onnx.zip",
        "size_mb": 350,
        "vram_mb": 256,
    },
    # VAD: ~50MB - Silero is lightweight
    "vad": {
        "name": "silero-vad",
        "url": "https://github.com/snakers4/silero-vad/archive/refs/heads/master.zip",
        "size_mb": 50,
        "vram_mb": 50,
    },
    # Wake Word: ~100MB - OpenWakeWord
    "wake_word": {
        "name": "openwakeword-1.0",
        "url": "https://github.com/dscripka/openWakeWord/releases/download/v1.0/openwakeword-1.0.tflite",
        "size_mb": 100,
        "vram_mb": 50,
    },
}


def download_file(url: str, dest: Path, expected_size_mb: int = 0) -> bool:
    """Download file with progress."""
    print(f"  Downloading: {url}")
    print(f"  Destination: {dest}")

    try:
        # Create temp file
        temp_file = dest.with_suffix(".tmp")

        def reporthook(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, block_num * block_size * 100 // total_size)
                print(f"\r  Progress: {percent}%", end="", flush=True)

        urllib.request.urlretrieve(url, temp_file, reporthook)
        print()

        # Move to final location
        shutil.move(str(temp_file), str(dest))
        print(f"  Downloaded: {dest.name}")
        return True

    except Exception as e:
        print(f"\n  ERROR: {e}")
        if dest.exists():
            dest.unlink()
        return False


def extract_tarBZ2(archive: Path, dest_dir: Path) -> bool:
    """Extract tar.bz2 archive."""
    try:
        print(f"  Extracting {archive.name}...")
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(dest_dir)
        return True
    except Exception as e:
        print(f"  ERROR extracting: {e}")
        return False


def extract_zip(archive: Path, dest_dir: Path) -> bool:
    """Extract zip archive."""
    try:
        print(f"  Extracting {archive.name}...")
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest_dir)
        return True
    except Exception as e:
        print(f"  ERROR extracting: {e}")
        return False


def download_stt() -> bool:
    """Download Sherpa-ONNX STT model."""
    model_dir = MODELS_DIR / "stt" / "sherpa-onnx-streaming-zipformer-en-2023-06-26"
    if model_dir.exists():
        print("[STT] Already downloaded, skipping")
        return True

    model_dir.parent.mkdir(parents=True, exist_ok=True)
    archive = MODELS_DIR / "stt.tar.bz2"

    if not download_file(MODELS["stt"]["url"], archive):
        return False

    return extract_tarBZ2(archive, MODELS_DIR / "stt")


def download_tts() -> bool:
    """Download Kokoro TTS model."""
    model_dir = MODELS_DIR / "tts" / "kokoro-v1.0"
    if model_dir.exists():
        print("[TTS] Already downloaded, skipping")
        return True

    model_dir.mkdir(parents=True, exist_ok=True)
    archive = MODELS_DIR / "kokoro.zip"

    if not download_file(MODELS["tts_kokoro"]["url"], archive):
        return False

    if not extract_zip(archive, MODELS_DIR / "tts"):
        return False

    # Move files to correct location
    extracted = MODELS_DIR / "tts" / "kokoro-v1.0-onnx"
    if extracted.exists():
        for f in extracted.iterdir():
            shutil.move(str(f), str(model_dir / f.name))
        extracted.rmdir()

    archive.unlink()
    return True


def download_vad() -> bool:
    """Download Silero VAD model."""
    # Silero VAD is loaded via PyTorch Hub, not manual download
    print("[VAD] Will be downloaded automatically on first use (PyTorch Hub)")
    return True


def download_wake_word() -> bool:
    """Download OpenWakeWord model."""
    model_dir = MODELS_DIR / "wake_word"
    model_dir.mkdir(parents=True, exist_ok=True)

    dest = model_dir / "openwakeword-1.0.tflite"
    if dest.exists():
        print("[Wake Word] Already downloaded, skipping")
        return True

    return download_file(MODELS["wake_word"]["url"], dest)


def main():
    print("=" * 60)
    echo = """
███████╗ █████╗ ██████╗ ██╗   ██╗██╗         ███████╗██╗ ██████╗ 
██╔════╝██╔══██╗██╔══██╗██║   ██║██║         ██╔════╝██║██╔════╝ 
█████╗  ███████║██████╔╝██║   ██║██║         █████╗  ██║██║  ███╗
██╔══╝  ██╔══██║██╔══██╗╚██╗ ██╔╝██║         ██╔══╝  ██║██║   ██║
██║     ██║  ██║██║  ██║ ╚████╔╝ ███████╗    ██║     ██║╚██████╔╝
╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝    ╚═╝     ╚═╝ ╚════╝ 
"""
    print(echo)
    print("=" * 60)
    print(f"\nModels directory: {MODELS_DIR}")
    print(f"Total VRAM budget: ~4GB\n")

    os.chdir(MODELS_DIR)

    print("\n[1/4] Downloading STT model (Sherpa-ONNX, ~120MB)...")
    if not download_stt():
        print("FAILED")
        return 1

    print("\n[2/4] Downloading TTS model (Kokoro, ~350MB)...")
    if not download_tts():
        print("FAILED")
        return 1

    print("\n[3/4] VAD setup...")
    if not download_vad():
        print("FAILED")
        return 1

    print("\n[4/4] Downloading Wake Word model (~100MB)...")
    if not download_wake_word():
        print("FAILED")
        return 1

    print("\n" + "=" * 60)
    print("All models downloaded successfully!")
    print("=" * 60)

    # Print VRAM summary
    total_vram = sum(m["vram_mb"] for m in MODELS.values())
    print(f"\nVRAM Usage Summary:")
    for name, m in MODELS.items():
        print(f"  {name}: ~{m['vram_mb']}MB")
    print(f"  TOTAL: ~{total_vram}MB")
    print(f"  Remaining for LLM: ~{4096 - total_vram}MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
