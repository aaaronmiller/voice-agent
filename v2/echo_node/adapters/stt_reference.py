#!/usr/bin/env python3
"""Reference STT adapter: pure-Python faster-whisper shim.

Speaks the Echo-Node Phase B adapter protocol on stdin/stdout
(see echo_node/adapters/PROTOCOL.md). Launched by the host as::

    python3 stt_reference.py --model-dir /path/to/faster-whisper-model

The host resolves this file via ``command: ["builtin:stt_reference.py"]``.
This is the reference most likely to validate on a real machine: no
external binary beyond the ``faster-whisper`` pip package, and it never
downloads models — ``--model-dir`` must point at already-downloaded
CTranslate2 files.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocol as P

import numpy as np


class FasterWhisperSTT:
    def __init__(self, model_dir: str | None):
        self.model_dir = model_dir
        self._model: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.model_dir or not os.path.isdir(self.model_dir):
            raise P.AdapterError(
                -32002, "no local faster-whisper model configured: pass "
                        "--model-dir /path/to/model (downloads are refused)")
        from faster_whisper import WhisperModel
        self._model = WhisperModel(self.model_dir, device="auto")

    # ── protocol ──

    def rpc_initialize(self, params: dict) -> dict:
        found = importlib.util.find_spec("faster_whisper") is not None
        cap = {
            "name": "faster-whisper",
            "version": "unknown",
            "languages": ["en"],
            "streaming": False,
            "license": "MIT",
            "network": False,
            "notes": "external faster-whisper (pip) via subprocess adapter",
        }
        return {"protocol_version": P.PROTOCOL_VERSION, "slot": "stt",
                "name": "faster-whisper-ref", "capabilities": cap,
                "module_found": found}

    def rpc_validate(self, params: dict) -> dict:
        if importlib.util.find_spec("faster_whisper") is None:
            return {"ok": False,
                    "reason": "faster_whisper is not installed (pip install faster-whisper)",
                    "details": {}}
        if not self.model_dir or not os.path.isdir(self.model_dir):
            return {"ok": False,
                    "reason": "faster_whisper installed but no local model configured: "
                              "pass --model-dir /path/to/model (this adapter never downloads)",
                    "details": {}}
        # Micro-probe: load the local model and transcribe 0.5 s of
        # silence; assert a well-formed string comes back.
        try:
            self._load()
            silence = np.zeros(8000, dtype=np.int16)
            with tempfile.TemporaryDirectory(prefix="fw-probe-") as tmp:
                wav = os.path.join(tmp, "silence.wav")
                P.write_wav_pcm16(wav, silence, 16000)
                segments, _info = self._model.transcribe(wav, beam_size=1)
                text = " ".join(s.text for s in segments).strip()
        except Exception as exc:
            return {"ok": False,
                    "reason": f"faster-whisper probe failed: {type(exc).__name__}: {exc}",
                    "details": {"model_dir": self.model_dir}}
        if not isinstance(text, str):
            return {"ok": False, "reason": "faster-whisper returned non-text",
                    "details": {}}
        return {"ok": True,
                "reason": f"faster-whisper transcribed a silence fixture from {self.model_dir}",
                "details": {"model_dir": self.model_dir}}

    def rpc_ping(self, params: dict) -> dict:
        return {"ok": True}

    def rpc_transcribe(self, params: dict) -> dict:
        try:
            self._load()
        except P.AdapterError:
            raise
        except Exception as exc:
            raise P.AdapterError(-32003, f"model load failed: {exc}") from exc
        pcm = P.b64_to_pcm16(params["pcm_b64"])
        rate = int(params.get("sample_rate", 16000))
        with tempfile.TemporaryDirectory(prefix="fw-stt-") as tmp:
            wav = os.path.join(tmp, "in.wav")
            P.write_wav_pcm16(wav, pcm, rate)
            segments, _info = self._model.transcribe(wav, beam_size=5)
            text = " ".join(s.text for s in segments).strip()
        return {"text": text}

    def rpc_shutdown(self, params: dict) -> dict:
        self._model = None
        return {"ok": True}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="faster-whisper reference STT adapter")
    ap.add_argument("--model-dir", default=None,
                    help="directory with local faster-whisper (CTranslate2) model files")
    args = ap.parse_args(argv)
    return P.run_adapter(FasterWhisperSTT(args.model_dir))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
