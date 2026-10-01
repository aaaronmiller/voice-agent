"""CosyVoice 3 TTS backend for Echo-Node v2 (EXPERIMENTAL).

Wraps FunAudioLLM CosyVoice 3 (0.5B) in the same interface as
KokoroTTS / DotsTTS (v2/tts_dots.py) so it can be dropped into
InterruptibleSpeaker with minimal changes.

What it is
----------
CosyVoice 3 is an Apache-2.0, 0.5B-parameter streaming TTS model with
~150 ms time-to-first-audio, zero-shot voice cloning from a short
reference clip, and instruction control (emotion / speed / style) across
9 languages + dialects. At fp16 the 0.5B weights are ~1 GB, comfortably
inside a 6 GB VRAM budget (e.g. RTX 4050 laptop). It is the "quality
tier" complement to Kokoro (latency king, no cloning): keep Kokoro as
the default, reach for this when a cloned or directed voice is wanted.

Install requirements (NOT installed by v2/setup.sh — optional provider)
-----------------------------------------------------------------------
1. Clone and install CosyVoice 3 (it is not a plain `pip install`
   package; follow the repo README — requirements include torch,
   onnxruntime, etc.):
       https://github.com/FunAudioLLM/CosyVoice3
2. Download the 0.5B checkpoint (the repo id below is the expected one —
   VERIFY it against the CosyVoice3 README before downloading):
       huggingface-cli download FunAudioLLM/CosyVoice3-0.5B \
           --local-dir models/cosyvoice3-0.5b

VRAM expectations: ~1-2 GB fp16 on CUDA for the 0.5B model. CPU works
but is far too slow for interactive use — treat CUDA as required.

Config (opt-in; kokoro remains the default provider)
----------------------------------------------------
    tts:
      provider: cosyvoice3
      model_path: models/cosyvoice3-0.5b
      prompt_wav: voices/reference.wav   # 16 kHz mono WAV recommended;
                                         # required — this provider needs
                                         # a speaker reference (zero-shot
                                         # cloning is its reason to exist)
      prompt_text: "transcript of the reference clip"
      instruction: "speak cheerfully, a little fast"  # optional style
                                                  # control; needs prompt_wav
      language: en                     # informational for now; the
                                       # reference clip's language guides it
      fp16: true

STATUS: EXPERIMENTAL — written against the documented CosyVoice 3
interface but NOT yet verified on the author's hardware (no GPU on the
build machine). The single unverified API boundary is _new_runtime() /
_generate(); if the installed cosyvoice package API differs, adjust
those two methods — everything else (chunk conversion, wav writing,
error messages) is plain numpy/soundfile.

WIRING (for the orchestrator owner — do NOT wire from here)
-----------------------------------------------------------
In assistant_v2.py, InterruptibleSpeaker.__init__ provider selection,
next to the existing branches:
    from tts_cosyvoice import CosyVoice3TTS
    ...
    elif provider == "cosyvoice3":
        self.tts = CosyVoice3TTS(tts_config)
And in validate_config(): add "cosyvoice3" to the allowed
{"dots", "kokoro", "espeak-ng"} provider set (and to the streaming gate
alongside "dots" if generate_stream is used). kokoro stays the default —
this provider is opt-in only.
"""

# NOTE: from __future__ import annotations keeps the np.ndarray
# annotations below as unevaluated strings, which is what allows this
# module to stay import-safe (no numpy/torch/soundfile at import time).
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Generator

# numpy is intentionally NOT imported here — see module docstring.


def _missing_package_error(action: str) -> RuntimeError:
    return RuntimeError(
        f"CosyVoice 3 is not installed (needed to {action}). "
        "Install it from https://github.com/FunAudioLLM/CosyVoice3 "
        "(clone the repo and follow its README), then download the 0.5B model, e.g.:\n"
        "  huggingface-cli download FunAudioLLM/CosyVoice3-0.5B "
        "--local-dir models/cosyvoice3-0.5b\n"
        "Verify the repo id against the CosyVoice3 README before downloading."
    )


class CosyVoice3TTS:
    """Streaming-capable TTS via CosyVoice 3 (0.5B, zero-shot cloning).

    Interface matches DotsTTS (v2/tts_dots.py): __init__(config),
    load(), warm(), synthesize_to_wav(), generate_stream(), sample_rate,
    unload()/close(). Importing this module never touches torch/numpy/
    soundfile/cosyvoice — all heavy imports are lazy inside methods.
    """

    def __init__(self, config: dict[str, Any]):
        self.model_path = Path(str(config.get("model_path", "models/cosyvoice3-0.5b")))
        prompt_wav = config.get("prompt_wav")
        self.prompt_wav = Path(str(prompt_wav)) if prompt_wav is not None else None
        self.prompt_text = str(config.get("prompt_text", ""))
        self.instruction = str(config.get("instruction", ""))
        # Informational for now: kept in config for a future verified
        # binding; the reference clip's language currently guides output.
        self.language = str(config.get("language", "en"))
        self.fp16 = bool(config.get("fp16", True))
        self._runtime = None
        self._sample_rate = 22050

    def load(self) -> None:
        if self._runtime is not None:
            return
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"CosyVoice 3 model not found at {self.model_path}. "
                "Download it, e.g.: huggingface-cli download FunAudioLLM/CosyVoice3-0.5B "
                f"--local-dir {self.model_path} "
                "(verify the repo id against https://github.com/FunAudioLLM/CosyVoice3)"
            )
        if self.prompt_wav is not None and not self.prompt_wav.exists():
            raise FileNotFoundError(
                f"prompt_wav for zero-shot cloning not found: {self.prompt_wav}"
            )

        started = time.perf_counter()
        print(f"[cosyvoice3] loading model from {self.model_path}", flush=True)
        self._runtime = self._new_runtime()
        self._sample_rate = int(getattr(self._runtime, "sample_rate", 22050))
        print(f"[timing] cosyvoice3_load={time.perf_counter() - started:.2f}s", flush=True)

    def _new_runtime(self):
        """Create the CosyVoice3 inference object.

        UNVERIFIED API BOUNDARY — written against the documented
        CosyVoice 3 CLI interface (mirrors the CosyVoice 2 CLI shape);
        adjust here if the installed package differs.
        """
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice3
        except ImportError as exc:
            raise _missing_package_error("load the model") from exc
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "torch is not installed; CosyVoice 3 needs torch. "
                "Install it per the CosyVoice3 README (match its expected CUDA build)."
            ) from exc
        use_fp16 = self.fp16 and torch.cuda.is_available()
        if self.fp16 and not torch.cuda.is_available():
            print("[cosyvoice3] no CUDA device; falling back to fp32 on CPU (slow)", flush=True)
        return CosyVoice3(
            str(self.model_path),
            load_jit=False,
            load_trt=False,
            fp16=use_fp16,
        )

    def _generate(self, text: str, stream: bool):
        """Yield raw audio chunks (torch tensors) for *text*.

        UNVERIFIED API BOUNDARY — see _new_runtime().
        Mode selection:
          instruction + prompt_wav -> instruct2 (clone + style control)
          prompt_wav               -> zero-shot clone
          neither                  -> clear error (this provider needs a
                                      speaker reference; that is its
                                      reason to exist)
        """
        rt = self._runtime
        assert rt is not None
        if self.instruction and self.prompt_wav is not None:
            gen = rt.inference_instruct2(
                text, self.instruction, str(self.prompt_wav), stream=stream
            )
        elif self.prompt_wav is not None:
            gen = rt.inference_zero_shot(
                text, self.prompt_text, str(self.prompt_wav), stream=stream
            )
        else:
            raise RuntimeError(
                "CosyVoice3TTS needs a speaker reference: set tts.prompt_wav "
                "(+ optional tts.prompt_text / tts.instruction) in the config. "
                "Zero-shot cloning is the point of this provider — for a fixed "
                "voice with no reference clip, use kokoro or dots instead."
            )
        # CosyVoice inference calls yield (or, when stream=False, may
        # return) dicts like {"tts_speech": Tensor}; normalize to chunks.
        if isinstance(gen, dict):
            gen = (gen,)
        for out in gen:
            yield out["tts_speech"]

    def warm(self) -> None:
        """Warm the model with a short generation to prime kernels."""
        if self._runtime is None:
            self.load()
        assert self._runtime is not None
        started = time.perf_counter()
        try:
            # Warmup needs a speaker reference too; without one there is
            # nothing meaningful to warm — load() already validated the dir.
            if self.prompt_wav is None:
                print("[cosyvoice3] warm skipped (no prompt_wav configured)", flush=True)
                return
            for _ in self._generate("Ready.", stream=False):
                pass
            print(f"[timing] cosyvoice3_warm={time.perf_counter() - started:.2f}s", flush=True)
        except Exception as exc:
            print(f"[cosyvoice3] warm failed: {exc}", flush=True)

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        """Generate speech for *text* and save to *path*.

        Returns *path* for chaining.
        """
        self.load()
        assert self._runtime is not None
        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError(
                "synthesize_to_wav needs numpy and soundfile: "
                "pip install numpy soundfile"
            ) from exc

        started = time.perf_counter()
        chunks = [
            c.detach().float().cpu().numpy().reshape(-1)
            for c in self._generate(text, stream=False)
        ]
        if not chunks:
            raise RuntimeError(f"CosyVoice 3 produced no audio for text: {text[:60]!r}")
        audio = np.concatenate(chunks, axis=0).astype("float32")
        sf.write(str(path), audio, self._sample_rate)
        print(
            f"[timing] cosyvoice3_gen={time.perf_counter() - started:.2f}s "
            f"text_len={len(text)}",
            flush=True,
        )
        return path

    def generate_stream(self, text: str) -> Generator[np.ndarray, None, None]:
        """Yield audio chunks as they are produced by CosyVoice 3.

        Each chunk is a numpy float32 array at the model sample rate.
        """
        self.load()
        assert self._runtime is not None
        try:
            import torch  # noqa: F401  (chunk conversion below)
        except ImportError as exc:
            raise RuntimeError("generate_stream needs torch: pip install torch") from exc

        for chunk in self._generate(text, stream=True):
            yield chunk.detach().float().cpu().reshape(-1).numpy()

    @property
    def sample_rate(self) -> int:
        """Return the model's native sample rate (read from the runtime)."""
        self.load()
        assert self._runtime is not None
        return self._sample_rate

    def unload(self) -> None:
        self.close()

    def close(self) -> None:
        """Release the model / GPU memory."""
        self._runtime = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
