#!/usr/bin/env python3
"""Echo-Node assistant with MuseTalk local photorealistic avatar.

Replaces the raccoon-hacker sprite with a real-time talking head
generated from a source photo + audio via MuseTalk.

Architecture:
  VAD → Whisper STT → Hermes LLM → Kokoro TTS ─┐
                                                ├→ MuseTalk → avatar window
  Source photo → VAE encode ────────────────────┘

Usage:
  python musetalk_assistant.py --photo face.jpg
  python musetalk_assistant.py --photo face.jpg --demo  (no wake word)
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import sounddevice as sd
import torch

# ── Path set-up ───────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
os.chdir(str(REPO))

# Import avatar video module
from avatar_video.avatar_video import AvatarVideo

# ── MuseTalk Avatar Thread ─────────────────────────────────────────

class MuseTalkRenderer:
    """Runs MuseTalk in a background thread, generating frames for the
    avatar window. Handles multiple audio chunks across a session.

    This is the core integration: it pre-loads models once, then
    converts TTS audio → talking-head video frames in real-time.
    """

    def __init__(self, photo_path: str, manifest_path: str | None = None,
                 fps: int = 25, batch_size: int = 16, audio_padding: int = 2):
        self.photo_path = photo_path
        self.manifest_path = manifest_path or str(REPO / "avatar_video/models/manifest.json")
        self.fps = fps
        self.batch_size = batch_size
        self.audio_padding = audio_padding

        self.av = AvatarVideo(self.manifest_path)
        self._loaded = False
        self._current_frames: list[np.ndarray] = []
        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=256)
        self._running = True
        self._generate_thread: threading.Thread | None = None

    def load(self) -> None:
        """Load models onto GPU (~8s, ~1.9GB)."""
        self.av.load_models()
        self.av.set_face(self.photo_path)
        self._loaded = True
        print(f"[MuseTalk] Loaded, GPU: {torch.cuda.memory_allocated()/1024**3:.2f}GB")

    def generate(self, audio_path: str) -> None:
        """Start generating frames from audio in background thread."""
        if not self._loaded:
            return
        # Wait for previous generation to finish
        self._wait_for_generation()
        self._generate_thread = threading.Thread(
            target=self._generate_worker, args=(audio_path,), daemon=True
        )
        self._generate_thread.start()

    def _generate_worker(self, audio_path: str) -> None:
        """Worker thread: generate all frames, feed into queue."""
        try:
            for frame in self.av.generate_stream(
                audio_path, fps=self.fps, batch_size=self.batch_size,
                audio_padding_left=self.audio_padding,
                audio_padding_right=self.audio_padding,
            ):
                if not self._running:
                    break
                while self._running and self._frame_queue.full():
                    # Drain oldest if full (buffer management)
                    try:
                        self._frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                self._frame_queue.put(frame)
        except Exception as e:
            print(f"[MuseTalk] generate error: {e}", flush=True)

    def get_frame(self) -> np.ndarray | None:
        """Get next available frame (non-blocking)."""
        try:
            return self._frame_queue.get_nowait()
        except queue.Empty:
            return None

    def has_frames(self) -> bool:
        return self._frame_queue.qsize() > 0

    def _wait_for_generation(self) -> None:
        if self._generate_thread and self._generate_thread.is_alive():
            self._generate_thread.join(timeout=30)

    def unload(self) -> None:
        self._running = False
        self._wait_for_generation()
        self.av.unload()


# ── Simulated Avatar Window (for testing without full Qt) ──────────

class DummyAvatarWindow:
    """Stand-in avatar window for headless testing.
    When running inside the real Qt application, this is swapped out
    for the actual AvatarWindow process.
    """
    def __init__(self):
        self._frame = None

    def show_frame(self, frame: np.ndarray) -> None:
        self._frame = frame.copy()

    def send_command(self, payload: dict) -> None:
        """Simulate IPC to the real avatar window."""
        pass

    def show(self) -> None:
        pass

    def update_debug_data(self, **kw) -> None:
        pass


# ── Min assistant for MuseTalk integration test ────────────────────

def _save_wav(audio_data: np.ndarray, sr: int, path: str) -> str:
    import soundfile as sf
    sf.write(path, audio_data, sr)
    return path


def live_loop(renderer: MuseTalkRenderer, avatar: DummyAvatarWindow,
              input_device: str = "default", sample_rate: int = 16000):
    """Capture audio from mic, process through MuseTalk, show frames.

    Simplified test loop — no STT/LLM/TTS, just generates talking-head
    frames from a test sine wave audio while capturing real mic audio.
    For production, this is replaced by the assistant_v2 pipeline.
    """
    import soundfile as sf

    print("[MuseTalk] Listening... (Ctrl+C to stop)")

    # Generate a test audio chunk (sine wave sweep)
    t = np.linspace(0, 3, sample_rate * 3)
    test_audio = np.sin(2 * np.pi * 220 * t * (1 + 0.3 * t / 3)) * 0.4
    test_path = "/tmp/musetalk_test.wav"
    sf.write(test_path, test_audio.astype(np.float32), sample_rate)

    print(f"[MuseTalk] Generating talking-head video from {test_path}...")
    renderer.generate(test_path)

    # Display frames as they come in (25fps ≈ 40ms per frame)
    frame_interval = 1.0 / renderer.fps
    last_frame_time = 0.0

    while renderer.has_frames() or (
        renderer._generate_thread and renderer._generate_thread.is_alive()
    ):
        frame = renderer.get_frame()
        if frame is not None:
            now = time.monotonic()
            if now - last_frame_time >= frame_interval:
                avatar.show_frame(frame)
                avatar.update_debug_data(rms=100 + np.random.random() * 200,
                                          vad=0.3 + np.random.random() * 0.4)
                last_frame_time = now
        else:
            time.sleep(0.005)

    print("[MuseTalk] Done.")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Echo-Node MuseTalk Assistant")
    parser.add_argument("--photo", default=os.environ.get("PHOTO_PATH", "avatar_video/face.jpg"),
                        help="Path to source photo")
    parser.add_argument("--models", default=None,
                        help="Path to models directory")
    parser.add_argument("--demo", action="store_true",
                        help="Run demo loop instead of full assistant")
    parser.add_argument("--fps", type=int, default=25,
                        help="Output frame rate")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="UNet batch size")
    args = parser.parse_args()

    # Check photo exists
    photo_path = str(REPO / args.photo) if not os.path.isabs(args.photo) else args.photo
    if not os.path.exists(photo_path):
        print(f"[MuseTalk] ERROR: Photo not found: {photo_path}")
        print(f"  Place a face photo at: avatar_video/face.jpg")
        print(f"  Or set PHOTO_PATH env var or use --photo")
        sys.exit(1)

    print("╔══════════════════════════════════════════════╗")
    print("║   Echo-Node MuseTalk Local Avatar v0.1      ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"  Source photo: {photo_path}")
    print(f"  GPU: {torch.cuda.get_device_properties(0).name}")
    print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f}GB")

    renderer = MuseTalkRenderer(
        photo_path, fps=args.fps, batch_size=args.batch_size
    )

    print(f"\n[MuseTalk] Loading models (~8s, ~1.9GB VRAM)...")
    t0 = time.time()
    renderer.load()
    print(f"[MuseTalk] Loaded in {time.time()-t0:.1f}s")

    # For now: run a live demo loop with test audio
    # In production this will call the full assistant_v2 pipeline
    avatar = DummyAvatarWindow()

    try:
        if args.demo:
            live_loop(renderer, avatar)
        else:
            # TODO: Launch full assistant with MuseTalk renderer
            # This is where assistant_v2.py integration goes:
            #   - Wake word detection
            #   - STT → LLM → TTS
            #   - TTS audio → renderer.generate()
            #   - Avatar window shows renderer frames
            live_loop(renderer, avatar)

    except KeyboardInterrupt:
        print("\n[MuseTalk] Shutting down...")
    finally:
        renderer.unload()
        print("[MuseTalk] Done.")


if __name__ == "__main__":
    main()
