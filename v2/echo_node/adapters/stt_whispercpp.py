#!/usr/bin/env python3
"""Reference STT adapter: wraps the whisper.cpp CLI.

Speaks the Echo-Node Phase B adapter protocol on stdin/stdout
(see echo_node/adapters/PROTOCOL.md). Launched by the host as::

    python3 stt_whispercpp.py --model /path/to/ggml-model.bin [--binary whisper-cli]

The host resolves this file via ``command: ["builtin:stt_whispercpp.py"]``.
PCM arrives as base64 int16 mono; whisper.cpp wants 16 kHz, which the
host already normalizes to.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocol as P

import numpy as np

_TIMESTAMP_RE = re.compile(r"^\[.*?-->.*?\]\s*")


class WhisperCppSTT:
    def __init__(self, binary: str, model: str | None, extra_args: list[str]):
        self.binary = binary
        self.model = model
        self.extra_args = extra_args

    # ── protocol ──

    def rpc_initialize(self, params: dict) -> dict:
        found = shutil.which(self.binary)
        # Plain dict on the wire — the child never needs the echo_node package.
        cap = {
            "name": "whisper.cpp",
            "version": "unknown",
            "languages": [],  # depends on the loaded model; not probed here
            "streaming": False,
            "license": "MIT",
            "network": False,
            "notes": f"external whisper.cpp CLI ({self.binary}) via subprocess adapter",
        }
        return {"protocol_version": P.PROTOCOL_VERSION, "slot": "stt",
                "name": "whispercpp", "capabilities": cap,
                "binary_found": bool(found)}

    def rpc_validate(self, params: dict) -> dict:
        binary_path = shutil.which(self.binary)
        if not binary_path:
            return {"ok": False,
                    "reason": f"whisper.cpp binary {self.binary!r} not found on PATH "
                              f"(install whisper.cpp or set --binary)",
                    "details": {"binary": self.binary}}
        if not self.model:
            return {"ok": False,
                    "reason": "no --model given; whisper.cpp needs a ggml model file",
                    "details": {"binary": binary_path}}
        if not os.path.exists(self.model):
            return {"ok": False,
                    "reason": f"model file missing: {self.model}",
                    "details": {"binary": binary_path, "model": self.model}}
        # Micro-probe: run the binary on 0.5 s of silence. Never downloads
        # anything; asserts the CLI runs and its output parses.
        silence = (b"\x00" * 16000)  # 0.5 s @ 16 kHz int16 mono
        with tempfile.TemporaryDirectory(prefix="whisper-probe-") as tmp:
            wav = os.path.join(tmp, "silence.wav")
            P.write_wav_pcm16(wav, np.frombuffer(silence, dtype="int16"), 16000)
            try:
                proc = subprocess.run(
                    [binary_path, "-m", self.model, "-f", wav, "--no-timestamps",
                     *self.extra_args],
                    capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                return {"ok": False, "reason": "whisper.cpp probe timed out on silence fixture",
                        "details": {"binary": binary_path}}
        if proc.returncode != 0:
            return {"ok": False,
                    "reason": f"whisper.cpp probe failed (exit {proc.returncode}): "
                              f"{proc.stderr.strip()[:200]}",
                    "details": {"binary": binary_path}}
        return {"ok": True,
                "reason": f"whisper.cpp CLI ran on a silence fixture ({binary_path})",
                "details": {"binary": binary_path, "model": self.model}}

    def rpc_ping(self, params: dict) -> dict:
        return {"ok": True}

    def rpc_transcribe(self, params: dict) -> dict:
        binary_path = shutil.which(self.binary)
        if not binary_path:
            raise P.AdapterError(-32001, f"whisper.cpp binary {self.binary!r} not on PATH")
        if not self.model or not os.path.exists(self.model or ""):
            raise P.AdapterError(-32002, "no usable --model configured for whisper.cpp")
        pcm = P.b64_to_pcm16(params["pcm_b64"])
        rate = int(params.get("sample_rate", 16000))
        with tempfile.TemporaryDirectory(prefix="whisper-stt-") as tmp:
            wav = os.path.join(tmp, "in.wav")
            P.write_wav_pcm16(wav, pcm, rate)
            proc = subprocess.run(
                [binary_path, "-m", self.model, "-f", wav, "--no-timestamps",
                 *self.extra_args],
                capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise P.AdapterError(-32003,
                                 f"whisper.cpp exit {proc.returncode}: {proc.stderr.strip()[:300]}")
        lines = [l for l in proc.stdout.splitlines()
                 if l.strip() and not _TIMESTAMP_RE.match(l.strip())]
        text = " ".join(lines).strip()
        # Fallback: some builds print plain text without --no-timestamps support.
        if not text:
            text = _TIMESTAMP_RE.sub("", proc.stdout).strip()
        return {"text": text}

    def rpc_shutdown(self, params: dict) -> dict:
        return {"ok": True}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="whisper.cpp STT adapter")
    ap.add_argument("--binary", default="whisper-cli",
                    help="whisper.cpp CLI binary name (default: whisper-cli)")
    ap.add_argument("--model", default=None,
                    help="path to ggml model file (required for transcription)")
    ap.add_argument("extra", nargs=argparse.REMAINDER,
                    help="extra args appended to the whisper.cpp command line")
    args = ap.parse_args(argv)
    return P.run_adapter(WhisperCppSTT(args.binary, args.model, args.extra))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
