#!/usr/bin/env python3
"""MuseTalk avatar video generator for Echo-Node.

Local photorealistic avatar using MuseTalk V1.5.
Hardware: RTX 4050, ~2GB VRAM, ~74fps UNet inference, ~15fps total with VAE decode.

Usage:
    python avatar_video/avatar_video.py <face.jpg> <audio.wav> [output.mp4]
    
As library:
    from avatar_video import AvatarVideo
    av = AvatarVideo()
    av.load_models()              # ~8s, 1.86GB GPU
    av.set_face("photo.jpg")       # detect face + precompute
    av.set_face_from_array(frame)  # or from numpy array
    frames = av.generate("audio.wav", fps=25)
    # frames is list of BGR numpy arrays (HxWx3)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch

# ── Model paths ──────────────────────────────────────────────────
AVATAR_DIR = Path(__file__).resolve().parent
MODELS_DIR = AVATAR_DIR / "models"
MANIFEST_PATH = MODELS_DIR / "manifest.json"
os.chdir(str(AVATAR_DIR))

import sys
sys.path.insert(0, str(MODELS_DIR))

from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.preprocessing import _detect_face_bbox, read_imgs, coord_placeholder
from musetalk.utils.blending import get_image_prepare_material, get_image_blending
from musetalk.utils.utils import datagen
from musetalk.models.unet import UNet, PositionalEncoding
from musetalk.models.vae import VAE as MuseTalkVAE


class AvatarVideo:
    """Lip-sync video avatar from a single photo + audio.

    Usage:
        av = AvatarVideo()
        av.load_models()            # one-time GPU load
        av.set_face("photo.jpg")    # pre-process
        frames = av.generate("audio.wav")
        # or stream frames one at a time
        for frame in av.generate_stream("audio_chunk.wav"):
            yield frame
    """

    def __init__(self, manifest_path: str | Path = MANIFEST_PATH):
        self.manifest = json.loads(Path(manifest_path).read_text()) if Path(manifest_path).exists() else {}
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        # Models (set by load_models)
        self.model = None
        self.pe = None
        self.vae = None
        self.whisper = None
        self.ap = None
        self.fp = None

        # Pre-computed avatar data
        self._latent = None
        self._bbox = None
        self._frame = None
        self._avatar_loaded = False
        self._models_loaded = False

        # Timing
        self._load_time = 0.0

    # ── Model loading ────────────────────────────────────────────

    def load_models(self) -> float:
        """Load all MuseTalk models onto GPU. Takes ~8s, uses ~1.9GB VRAM."""
        if self._models_loaded:
            return self._load_time

        t0 = time.time()
        m = self.manifest

        # ── UNet ──
        with open(m["unet_config"]) as f:
            unet_cfg = json.load(f)
        from diffusers import UNet2DConditionModel
        self.model = UNet2DConditionModel(**unet_cfg).to(self.device, dtype=torch.float16)
        sd = torch.load(m["unet_path"], map_location="cpu", weights_only=False)
        self.model.load_state_dict(sd, strict=False)
        del sd

        self.pe = PositionalEncoding(d_model=384).half().to(self.device)

        # ── VAE ──
        self.vae = MuseTalkVAE(model_path=m["vae_dir"])
        self.vae.vae = self.vae.vae.half().to(self.device)

        # ── Whisper on GPU ──
        from transformers import WhisperModel
        weight_dtype = self.model.dtype
        self.whisper = WhisperModel.from_pretrained(m["whisper_dir"]).to(
            self.device, dtype=weight_dtype
        ).eval()

        self.ap = AudioProcessor(feature_extractor_path=m["whisper_dir"])
        self.fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)

        torch.cuda.synchronize()
        self._models_loaded = True
        self._load_time = time.time() - t0
        print(f"[AvatarVideo] Models loaded in {self._load_time:.1f}s, "
              f"GPU: {torch.cuda.memory_allocated()/1024**3:.2f}GB")
        return self._load_time

    # ── Face pre-processing ──────────────────────────────────────

    def set_face(self, image_path: str | Path) -> None:
        """Detect face in image and pre-compute latents."""
        if not self._models_loaded:
            raise RuntimeError("Call load_models() first")

        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        self.set_face_from_array(img)

    def set_face_from_array(self, img: np.ndarray) -> None:
        """Set face from numpy array (BGR)."""
        if not self._models_loaded:
            raise RuntimeError("Call load_models() first")

        bbox = _detect_face_bbox(img)
        if not bbox:
            h, w = img.shape[:2]
            bbox = (int(w * 0.1), int(h * 0.1), int(w * 0.9), int(h * 0.9))
            print(f"[AvatarVideo] No face detected, using center crop: {bbox}")

        self._bbox = bbox
        self._frame = img.copy()

        x1, y1, x2, y2 = bbox
        crop = cv2.resize(img[y1:y2, x1:x2], (256, 256),
                          interpolation=cv2.INTER_LANCZOS4)

        with torch.no_grad():
            self._latent = self.vae.get_latents_for_unet(crop).to(self.device).half()

        self._avatar_loaded = True
        print(f"[AvatarVideo] Face ready: bbox={bbox}")

    # ── Audio → video generation ─────────────────────────────────

    def generate(self, audio_path: str | Path, fps: int = 25,
                 audio_padding_left: int = 2, audio_padding_right: int = 2,
                 batch_size: int = 16) -> list[np.ndarray]:
        """Generate lip-synced video frames from audio file.

        Returns list of BGR numpy arrays (HxWx3).
        """
        frames = list(self.generate_stream(audio_path, fps, audio_padding_left,
                                            audio_padding_right, batch_size))
        return frames

    def generate_stream(self, audio_path: str | Path, fps: int = 25,
                        audio_padding_left: int = 2, audio_padding_right: int = 2,
                        batch_size: int = 16):
        """Generator yielding video frames one at a time."""
        if not self._avatar_loaded:
            raise RuntimeError("Call set_face() first")

        weight_dtype = self.model.dtype
        timesteps = torch.tensor([0], device=self.device)

        # Audio features
        feat_list, librosa_length = self.ap.get_audio_feature(
            str(audio_path), weight_dtype=weight_dtype
        )
        whisper_chunks = self.ap.get_whisper_chunk(
            feat_list, self.device, weight_dtype, self.whisper,
            librosa_length, fps=fps,
            audio_padding_length_left=audio_padding_left,
            audio_padding_length_right=audio_padding_right,
        )

        n_chunks = len(whisper_chunks)
        if n_chunks == 0:
            return

        latent_list = [self._latent] * n_chunks
        gen = datagen(whisper_chunks, latent_list, batch_size=batch_size,
                      delay_frame=0, device=self.device)

        scaling = self.vae.scaling_factor
        x1, y1, x2, y2 = self._bbox
        bg = self._frame

        for wb, lb in gen:
            with torch.no_grad():
                af = self.pe(wb.to(self.device))
                lb = lb.to(self.device, dtype=weight_dtype)
                pred = self.model(lb, timesteps, encoder_hidden_states=af).sample

                # Decode
                latents_decode = (1 / scaling) * pred
                image = self.vae.vae.decode(latents_decode).sample
                image = (image / 2 + 0.5).clamp(0, 1)
                image = image.detach().cpu().permute(0, 2, 3, 1).float().numpy()
                image = (image * 255).round().astype("uint8")

            for res_frame in image:
                res_r = cv2.resize(res_frame, (x2 - x1, y2 - y1),
                                   interpolation=cv2.INTER_LANCZOS4)
                combined = bg.copy()
                combined[y1:y2, x1:x2] = res_r
                yield combined

    # ── Cleanup ──────────────────────────────────────────────────

    def unload(self) -> None:
        """Free GPU memory."""
        self.model = self.pe = self.vae = self.whisper = self.ap = self.fp = None
        self._latent = self._bbox = self._frame = None
        self._models_loaded = self._avatar_loaded = False
        torch.cuda.empty_cache()
        print("[AvatarVideo] GPU memory freed")


# ── Quick test ───────────────────────────────────────────────────

def main():
    import sys

    if len(sys.argv) < 3:
        print("Usage: python avatar_video.py <face.jpg> <audio.wav> [output.mp4]")
        return

    image_path = sys.argv[1]
    audio_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "output.mp4"

    av = AvatarVideo()
    av.load_models()
    av.set_face(image_path)

    t0 = time.time()
    frames = av.generate(audio_path, fps=25)
    elapsed = time.time() - t0

    # Save video
    if frames:
        import imageio
        h, w = frames[0].shape[:2]
        # Ensure dimensions are divisible by 2 for codec
        if h % 2 != 0 or w % 2 != 0:
            frames = [cv2.resize(f, (w - w % 2, h - h % 2)) for f in frames]
        writer = imageio.get_writer(output_path, fps=25, codec='libx264', quality=8)
        for f in frames:
            writer.append_data(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        writer.close()
        size_mb = os.path.getsize(output_path) / 1e6
        print(f"[AvatarVideo] {len(frames)} frames in {elapsed:.1f}s -> {output_path} ({size_mb:.1f}MB)")

    av.unload()


if __name__ == "__main__":
    main()
