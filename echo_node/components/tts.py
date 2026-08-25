"""
Echo-Node TTS Components — Kokoro, Dots, eSpeak.
"""

from __future__ import annotations

import gc
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import soundfile as sf



ROOT = Path(__file__).resolve().parent.parent.parent  # echo_node -> project root

class KokoroTTS:
    def __init__(self, config: dict[str, Any]):
        self.model_path = (Path(__file__).resolve().parent.parent.parent / str(config.get("model_path", "models/kokoro/kokoro-v1.0.onnx"))).resolve()
        self.voices_path = (Path(__file__).resolve().parent.parent.parent / str(config.get("voices_path", "models/kokoro/voices-v1.0.bin"))).resolve()
        self.voice = str(config.get("voice", "af_heart"))
        self.speed = float(config.get("speed", 1.0))
        self._kokoro = None

    def load(self) -> None:
        if self._kokoro is not None:
            return
        if not self.model_path.exists() or not self.voices_path.exists():
            raise FileNotFoundError("Kokoro model files missing. Run ./setup.sh.")
        from kokoro_onnx import Kokoro
        started = time.perf_counter()
        self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        print(f"[timing] tts_load={time.perf_counter() - started:.2f}s", flush=True)

    def unload(self) -> None:
        if self._kokoro is None:
            return
        del self._kokoro
        self._kokoro = None
        import gc; gc.collect()

    def warm(self) -> None:
        fd, name = tempfile.mkstemp(prefix="echo-node-tts-warm-", suffix=".wav")
        os.close(fd)
        path = Path(name)
        try:
            self.synthesize_to_wav("Ready.", path)
        finally:
            path.unlink(missing_ok=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        self.load()
        assert self._kokoro is not None
        audio, sample_rate = self._kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        sf.write(str(path), audio, sample_rate)
        return path


class DotsTTS:
    """GPU-accelerated TTS via dots.tts (2B AR model, MeanFlow distillation)."""
    def __init__(self, config: dict[str, Any]):
        from tts_dots import DotsTTS as _DotsTTS
        self._impl = _DotsTTS(config)

    def load(self) -> None:
        self._impl.load()

    def unload(self) -> None:
        self._impl.unload()

    def warm(self) -> None:
        self._impl.warm()

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        started = time.perf_counter()
        result = self._impl.synthesize_to_wav(text, path)
        print(f"[timing] tts_gen={time.perf_counter() - started:.2f}s provider=dots", flush=True)
        return result

    def generate_stream(self, text: str):
        return self._impl.generate_stream(text)

    @property
    def sample_rate(self) -> int:
        return self._impl.sample_rate


class EspeakTTS:
    def __init__(self, config: dict[str, Any]):
        self.voice = str(config.get("espeak_voice", "en-us"))
        self.speed = str(config.get("espeak_speed", 165))
        self.pitch = str(config.get("espeak_pitch", 45))
        if shutil.which("espeak-ng") is None:
            raise RuntimeError("espeak-ng is not installed.")

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        subprocess.run(
            ["espeak-ng", "-v", self.voice, "-s", self.speed, "-p", self.pitch, "-w", str(path), text],
            check=True,
        )
        return path

    def unload(self) -> None:
        pass

    def warm(self) -> None:
        return


# ── Interruptible speaker ───────────────────────────────────────────