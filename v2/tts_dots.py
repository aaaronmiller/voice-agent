"""dots.tts TTS backend for Echo-Node v2.

Wraps DotsTtsRuntime in the same interface as KokoroTTS / EspeakTTS
so it can be dropped into InterruptibleSpeaker with minimal changes.

Also exposes a streaming generator for ultra-low-latency playback.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Generator, Iterator

import numpy as np
import soundfile as sf
import torch


class DotsTTS:
    """GPU-accelerated TTS via dots.tts (2B AR model, MeanFlow distillation).

    Interface matches KokoroTTS/EspeakTTS: load(), warm(), synthesize_to_wav().
    """

    def __init__(self, config: dict[str, Any]):
        self.model_path = Path(str(config.get("model_path", "models/dots-tts-mf")))
        self.voice = str(config.get("voice", "basic_ref_en"))
        self.num_steps = int(config.get("num_steps", 4))
        self.guidance_scale = float(config.get("guidance_scale", 1.2))
        self._runtime = None

    def load(self) -> None:
        if self._runtime is not None:
            return
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"dots.tts model not found at {self.model_path}. "
                "Run: huggingface-cli download rednote-hilab/dots.tts-mf "
                f"--local-dir {self.model_path}"
            )

        started = time.perf_counter()
        print(f"[dots.tts] loading model from {self.model_path}", flush=True)

        # Load model manually to manage memory (convert all to bf16 before GPU)
        from dots_tts.models.dots_tts.model import DotsTtsModel

        model = DotsTtsModel.from_pretrained(str(self.model_path))
        target_dtype = torch.bfloat16
        model.core.to(dtype=target_dtype)
        # Keep vocoder/xvector in fp32 (weight_norm requires matching input/weight dtype)
        # Only core (LLM backbone) benefits from bf16 memory savings

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device).eval()
        model.set_optimize(False)

        # Now wrap in runtime
        from dots_tts.runtime import DotsTtsRuntime
        from pathlib import Path

        # Patch: build a minimal runtime that reuses our already-loaded model
        self._runtime = DotsTtsRuntime.__new__(DotsTtsRuntime)
        self._runtime.model = model
        self._runtime.pretrained_path = Path(str(self.model_path))
        self._runtime.precision = "bfloat16"
        self._runtime.device = device
        self._runtime.optimize = False
        self._runtime.max_generate_length = 500
        self._runtime.sample_rate = int(model.config.vocoder.sample_rate)

        print(f"[timing] dots_load={time.perf_counter() - started:.2f}s", flush=True)

    def warm(self) -> None:
        """Warm the model with a short generation to prime CUDA kernels."""
        if self._runtime is None:
            self.load()
        started = time.perf_counter()
        try:
            # Short generation to warm CUDA and trigger any lazy compilation
            result = self._runtime.generate(
                text="Ready.",
                num_steps=2,  # fewer steps for warmup
                guidance_scale=self.guidance_scale,
            )
            _ = result["audio"]
            print(f"[timing] dots_warm={time.perf_counter() - started:.2f}s", flush=True)
        except Exception as exc:
            print(f"[dots.tts] warm failed: {exc}", flush=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        """Generate speech for *text* and save to *path*.

        Returns *path* for chaining.
        """
        self.load()
        assert self._runtime is not None

        started = time.perf_counter()
        result = self._runtime.generate(
            text=text,
            num_steps=self.num_steps,
            guidance_scale=self.guidance_scale,
        )
        audio = result["audio"].float().cpu().squeeze().numpy()
        sample_rate = int(result["sample_rate"])
        sf.write(str(path), audio, sample_rate)
        print(f"[timing] dots_gen={time.perf_counter() - started:.2f}s text_len={len(text)}", flush=True)
        return path

    def generate_stream(
        self, text: str
    ) -> Generator[np.ndarray, None, None]:
        """Yield audio chunks as they are produced by dots.tts.

        Each chunk is a numpy float32 array at model sample rate (48 kHz).
        """
        self.load()
        assert self._runtime is not None

        for chunk in self._runtime.generate_stream(
            text=text,
            num_steps=self.num_steps,
            guidance_scale=self.guidance_scale,
        ):
            yield chunk.detach().float().cpu().squeeze().numpy()

    @property
    def sample_rate(self) -> int:
        """Return the model's native sample rate (48 kHz)."""
        self.load()
        assert self._runtime is not None
        return self._runtime.sample_rate

    def unload(self) -> None:
        self.close()

    def close(self) -> None:
        """Release GPU memory."""
        self._runtime = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
