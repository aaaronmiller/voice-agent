#!/usr/bin/env python3
"""Reference TTS adapter: wraps the Piper binary.

Speaks the Echo-Node Phase B adapter protocol on stdin/stdout
(see echo_node/adapters/PROTOCOL.md). Launched by the host as::

    python3 tts_piper.py --model /path/to/voice.onnx [--binary piper]

The host resolves this file via ``command: ["builtin:tts_piper.py"]``.
Piper reads text on stdin and writes a WAV file; this adapter returns
the PCM as base64 with the WAV's sample rate.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocol as P

import numpy as np


class PiperTTS:
    def __init__(self, binary: str, model: str | None, config: str | None,
                 extra_args: list[str]):
        self.binary = binary
        self.model = model
        self.config = config
        self.extra_args = extra_args

    def _base_cmd(self, out_wav: str) -> list[str]:
        cmd = [self.binary, "--model", self.model or "", "--output_file", out_wav]
        if self.config:
            cmd += ["--config", self.config]
        return cmd + self.extra_args

    # ── protocol ──

    def rpc_initialize(self, params: dict) -> dict:
        found = shutil.which(self.binary)
        cap = {
            "name": "piper",
            "version": "unknown",
            "languages": [],  # depends on the voice model; not probed here
            "streaming": False,
            "license": "MIT",
            "network": False,
            "notes": f"external Piper TTS binary ({self.binary}) via subprocess adapter",
        }
        return {"protocol_version": P.PROTOCOL_VERSION, "slot": "tts",
                "name": "piper", "capabilities": cap,
                "binary_found": bool(found)}

    def rpc_validate(self, params: dict) -> dict:
        binary_path = shutil.which(self.binary)
        if not binary_path:
            return {"ok": False,
                    "reason": f"piper binary {self.binary!r} not found on PATH "
                              f"(install piper-tts or set --binary)",
                    "details": {"binary": self.binary}}
        if not self.model:
            return {"ok": False,
                    "reason": "no --model given; piper needs a voice .onnx file",
                    "details": {"binary": binary_path}}
        if not os.path.exists(self.model):
            return {"ok": False,
                    "reason": f"voice model missing: {self.model}",
                    "details": {"binary": binary_path, "model": self.model}}
        # Micro-probe: synthesize a short sentence; assert a non-empty WAV.
        # Never downloads anything.
        with tempfile.TemporaryDirectory(prefix="piper-probe-") as tmp:
            out = os.path.join(tmp, "probe.wav")
            try:
                proc = subprocess.run(
                    self._base_cmd(out), input="test\n",
                    capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                return {"ok": False, "reason": "piper probe timed out",
                        "details": {"binary": binary_path}}
            if proc.returncode != 0 or not os.path.exists(out):
                return {"ok": False,
                        "reason": f"piper probe failed (exit {proc.returncode}): "
                                  f"{proc.stderr.strip()[:200]}",
                        "details": {"binary": binary_path}}
            try:
                samples, rate = P.read_wav_pcm16(out, target_rate=22050)
            except Exception as exc:
                return {"ok": False, "reason": f"piper probe produced no WAV: {exc}",
                        "details": {"binary": binary_path}}
            rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        return {"ok": True,
                "reason": f"piper synthesized a probe sentence ({rate} Hz, RMS {rms:.0f})",
                "details": {"binary": binary_path, "model": self.model,
                            "sample_rate": rate, "rms": rms}}

    def rpc_ping(self, params: dict) -> dict:
        return {"ok": True}

    def rpc_synthesize(self, params: dict) -> dict:
        binary_path = shutil.which(self.binary)
        if not binary_path:
            raise P.AdapterError(-32001, f"piper binary {self.binary!r} not on PATH")
        if not self.model or not os.path.exists(self.model or ""):
            raise P.AdapterError(-32002, "no usable --model configured for piper")
        text = str(params.get("text", "")).strip()
        if not text:
            raise P.AdapterError(-32602, "synthesize requires non-empty 'text'")
        with tempfile.TemporaryDirectory(prefix="piper-tts-") as tmp:
            out = os.path.join(tmp, "out.wav")
            proc = subprocess.run(
                self._base_cmd(out), input=text + "\n",
                capture_output=True, text=True, timeout=300)
            if proc.returncode != 0 or not os.path.exists(out):
                raise P.AdapterError(
                    -32003, f"piper exit {proc.returncode}: {proc.stderr.strip()[:300]}")
            samples, rate = P.read_wav_pcm16(out, target_rate=22050)
        return {"pcm_b64": P.pcm16_to_b64(samples), "sample_rate": rate}

    def rpc_shutdown(self, params: dict) -> dict:
        return {"ok": True}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Piper TTS adapter")
    ap.add_argument("--binary", default="piper",
                    help="piper binary name (default: piper)")
    ap.add_argument("--model", default=None,
                    help="path to piper voice .onnx file (required for synthesis)")
    ap.add_argument("--config", default=None,
                    help="optional piper voice .onnx.json config")
    ap.add_argument("extra", nargs=argparse.REMAINDER,
                    help="extra args appended to the piper command line")
    args = ap.parse_args(argv)
    return P.run_adapter(PiperTTS(args.binary, args.model, args.config, args.extra))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
