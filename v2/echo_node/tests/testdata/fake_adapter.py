#!/usr/bin/env python3
"""Fake adapter for the Phase B conformance tests.

Speaks the adapter protocol on stdin/stdout. Modes (via --mode):

  echo        canned responses to every method (the happy path)
  crash-once  exits(1) on the first `ping`, then behaves like echo
  crash-always exits(1) on every `ping`
  hang        never answers `ping` (tests the host timeout)
  garbage     writes one non-JSON line at startup, then behaves like echo
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))) + "/adapters")

import protocol as P

import numpy as np


class FakeAdapter:
    def __init__(self, mode: str):
        self.mode = mode
        self._ping_count = 0
        if mode == "garbage":
            # One malformed line before any request: the host must log it
            # and keep going, never hang or poison the stream.
            sys.stdout.write("this is not json{{{\n")
            sys.stdout.flush()

    def rpc_initialize(self, params: dict) -> dict:
        cap = {
            "name": "fake", "version": "0.1", "languages": ["en"],
            "streaming": False, "license": "MIT", "network": False,
            "notes": "test fake adapter",
        }
        return {"protocol_version": P.PROTOCOL_VERSION, "slot": "stt",
                "name": "fake", "capabilities": cap}

    def rpc_validate(self, params: dict) -> dict:
        return {"ok": True, "reason": "fake self-check passed", "details": {}}

    def rpc_ping(self, params: dict) -> dict:
        self._ping_count += 1
        if self.mode == "hang":
            time.sleep(3600)  # never answers
        if self.mode == "crash-always":
            os._exit(1)
        if self.mode == "crash-once":
            marker = os.environ.get("FAKE_CRASH_MARKER")
            if not marker or not os.path.exists(marker):
                # First crash: touch the marker so the RESPAWNED child
                # behaves like echo (tests restart recovery, not a loop).
                if marker:
                    open(marker, "w").close()
                os._exit(1)
        return {"ok": True}

    def rpc_transcribe(self, params: dict) -> dict:
        return {"text": "hello world"}

    def rpc_synthesize(self, params: dict) -> dict:
        tone = (np.sin(np.arange(1600) * 0.1) * 10000).astype(np.int16)
        return {"pcm_b64": P.pcm16_to_b64(tone), "sample_rate": 16000}

    def rpc_is_speech(self, params: dict) -> dict:
        return {"speech": True, "score": 0.9}

    def rpc_detect(self, params: dict) -> dict:
        return {"detected": True, "phrase": "hey fake", "score": 0.8}

    def rpc_chat(self, params: dict) -> dict:
        return {"text": f"fake reply to: {params.get('text', '')}"}

    def rpc_shutdown(self, params: dict) -> dict:
        return {"ok": True}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="echo",
                    choices=["echo", "crash-once", "crash-always", "hang", "garbage"])
    args = ap.parse_args(argv)
    return P.run_adapter(FakeAdapter(args.mode))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
