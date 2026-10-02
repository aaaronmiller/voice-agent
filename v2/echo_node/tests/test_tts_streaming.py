"""TTS generate_stream() wiring into InterruptibleSpeaker.

Runs as a script: ``python3 -m echo_node.tests.test_tts_streaming`` from
``v2/``. All fakes — no audio hardware, no TTS models, no GPU:

- ``FakeStreamingTTS``: generate_stream yields float32 chunks with
  controlled delays (and optional failure injection).
- ``FakeBlockingTTS``: only synthesize_to_wav (writes PCM16 via stdlib
  ``wave``); does NOT override generate_stream.
- ``FakePopen``: stands in for ``aplay`` (raw-float stdin streaming).
- ``FakeMic``/``FakeVad``: scripted mic audio + VAD scores for barge-in.

Covers: streaming path engagement, first-audio latency win, blocking
fallback (no override / early generator failure / avatar present /
missing sample_rate), barge-in mid-stream, mid-stream failure downgrade,
turn_rec timing order, the ABC default generate_stream, and the real
WyomingTTS.generate_stream against a fake TCP server.
"""

from __future__ import annotations

import contextlib
import io
import os
import socketserver
import sys
import tempfile as _tempfile  # noqa: E402
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from echo_node.adapters import _validate_entry
from echo_node.adapters import wyoming as W
from echo_node.adapters.wyoming import (
    WyomingTTS, make_wyoming_provider, read_event, write_event,
)
from echo_node.components import audio as audio_mod
from echo_node.components.audio import AudioConfig, InterruptibleSpeaker
from echo_node.components.barge_in import VadGatedBargeIn
from echo_node.components.tts import Qwen3TTS
from echo_node.slots import Capability, TTSProvider

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


# ── fakes ────────────────────────────────────────────────────────────

_SR = 24000


def _chunk(n: int, sr: int = _SR, freq: float = 220.0) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / sr
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class FakeStreamingTTS(TTSProvider):
    """Streaming TTS: yields float32 chunks with per-chunk delays."""

    def __init__(self, n_chunks: int = 4, chunk_n: int = 2400,
                 delay: float = 0.02, fail_at: int | None = None,
                 sample_rate: int | None = _SR):
        self.n_chunks = n_chunks
        self.chunk_n = chunk_n
        self.delay = delay
        self.fail_at = fail_at
        self._sr = sample_rate
        self.synth_calls = 0
        self.stream_calls = 0

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name="fake-stream", streaming=True)

    @classmethod
    def validate(cls, config=None):
        from echo_node.slots.validation import ok_result
        return ok_result("fake", {})

    def load(self): pass
    def unload(self): pass
    def warm(self): pass

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        self.synth_calls += 1
        pcm = (_chunk(self.chunk_n * self.n_chunks) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(_SR)
            wf.writeframes(pcm.tobytes())
        return path

    def generate_stream(self, text: str):
        self.stream_calls += 1
        for i in range(self.n_chunks):
            if self.fail_at is not None and i == self.fail_at:
                raise RuntimeError("boom (injected)")
            if self.delay:
                time.sleep(self.delay)
            yield _chunk(self.chunk_n)

    @property
    def sample_rate(self):
        return self._sr


class FakeBlockingTTS(TTSProvider):
    """Batch-only TTS: does NOT override generate_stream."""

    def __init__(self, synth_delay: float = 0.0):
        self.synth_delay = synth_delay
        self.synth_calls = 0

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name="fake-block", streaming=False)

    @classmethod
    def validate(cls, config=None):
        from echo_node.slots.validation import ok_result
        return ok_result("fake", {})

    def load(self): pass
    def unload(self): pass
    def warm(self): pass

    def synthesize_to_wav(self, text: str, path: Path) -> Path:
        self.synth_calls += 1
        if self.synth_delay:
            time.sleep(self.synth_delay)
        pcm = (_chunk(4800) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(_SR)
            wf.writeframes(pcm.tobytes())
        return path


class FakeVad:
    threshold = 0.5
    rms_floor = 100

    def __init__(self, score: float = 0.0):
        self._score = score

    def score(self, samples):
        return self._score


class FakeMic:
    """Scripted mic: silence until read #loud_from, then loud speech."""

    def __init__(self, chunk_n: int = 1280, loud_from: int | None = None):
        self.chunk_n = chunk_n
        self.loud_from = loud_from
        self.reads = 0

    def read(self):
        self.reads += 1
        if self.loud_from is not None and self.reads >= self.loud_from:
            return np.full(self.chunk_n, 8000, dtype=np.int16)
        return np.zeros(self.chunk_n, dtype=np.int16)


class FakePopen:
    """Stands in for aplay: records cmd + stdin bytes.

    Simulates a real aplay run: poll() reports "running" until stdin is
    closed (streaming path) or a short time budget elapses (wav path,
    where nothing is written to stdin) — otherwise _play_wav's
    ``while proc.poll() is None`` loop would spin forever.
    """

    instances: list = []

    def __init__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        self.stdin = _TrackingBytesIO(self)
        self._final_bytes: bytes | None = None
        self._stdin_closed = False
        self._born = time.monotonic()
        self._budget = 1.0
        self.terminated = False
        FakePopen.instances.append(self)

    def poll(self):
        if self.terminated or self._stdin_closed:
            return 0
        if time.monotonic() - self._born > self._budget:
            return 0
        return None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.terminated = True
        return 0

    @property
    def stdin_bytes(self):
        if self._final_bytes is not None:
            return self._final_bytes
        return self.stdin.getvalue()


class _TrackingBytesIO(io.BytesIO):
    """BytesIO that notifies its FakePopen when closed."""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner

    def close(self):
        # getvalue() raises on a closed buffer — stash first.
        self._owner._final_bytes = self.getvalue()
        self._owner._stdin_closed = True
        super().close()


def make_speaker(tts, *, mic_loud_from=None, vad_score=0.0,
                 avatar=None, far_end_cb=None, **cfg_over):
    """InterruptibleSpeaker with fakes, bypassing __init__."""
    sp = InterruptibleSpeaker.__new__(InterruptibleSpeaker)
    vad = FakeVad(score=vad_score)
    cfg = {
        "enabled": True,
        "min_speech_seconds": 0.0,
        "min_playback_age_seconds": 0.0,
        "bargein_end_grace_s": 0.0,
        "playback_threshold_boost": 1.0,
        "playback_rms_boost": 1.0,
        "playback_start_grace_s": 0.0,
    }
    cfg.update(cfg_over)
    sp.audio = AudioConfig(backend="alsa", sample_rate=16000, chunk_size=1280)
    sp.vad = vad
    sp.enabled = True
    sp.far_end_callback = far_end_cb
    sp.barge_in = VadGatedBargeIn(vad, cfg)
    sp.min_speech_seconds = float(cfg["min_speech_seconds"])
    sp.min_playback_age_seconds = float(cfg["min_playback_age_seconds"])
    sp.bargein_end_grace_s = float(cfg["bargein_end_grace_s"])
    sp.playback_threshold_boost = float(cfg["playback_threshold_boost"])
    sp.playback_rms_boost = float(cfg["playback_rms_boost"])
    sp.playback_start_grace_s = float(cfg["playback_start_grace_s"])
    sp._orig_threshold = vad.threshold
    sp._orig_rms_floor = vad.rms_floor
    sp.avatar = avatar
    sp.hotkey = None
    sp.debug_callback = None
    sp.tts = tts
    sp._mic_loud_from = mic_loud_from
    return sp


def make_rec():
    return SimpleNamespace(t_tts_start=0.0, t_tts_first_chunk=0.0,
                           t_tts_done=0.0, t_playback_start=0.0,
                           t_playback_done=0.0)


@contextlib.contextmanager
def fake_aplay():
    FakePopen.instances.clear()
    with mock.patch("shutil.which", return_value="/usr/bin/aplay"), \
         mock.patch("subprocess.Popen", FakePopen):
        yield FakePopen


# ── tests ────────────────────────────────────────────────────────────

def test_streaming_path_engaged():
    tts = FakeStreamingTTS(n_chunks=4, chunk_n=2400, delay=0.0)
    sp = make_speaker(tts)
    rec = make_rec()
    with fake_aplay():
        interrupted = sp.speak("Hello world.", mic=FakeMic(), turn_rec=rec)
    check("streaming: not interrupted", interrupted is False)
    check("streaming: synthesize_to_wav NOT called",
          tts.synth_calls == 0, f"calls={tts.synth_calls}")
    check("streaming: generate_stream called once", tts.stream_calls == 1)
    popen = FakePopen.instances[0]
    check("streaming: aplay raw-float mode",
          "-t" in popen.cmd and "FLOAT_LE" in popen.cmd
          and str(_SR) in popen.cmd, " ".join(popen.cmd))
    got = np.frombuffer(popen.stdin_bytes, dtype=np.float32)
    check("streaming: all 4 chunks written in order",
          got.shape == (4 * 2400,) and np.allclose(got[:2400], _chunk(2400)),
          f"shape={got.shape}")
    check("streaming: t_tts_first_chunk is first AUDIO chunk",
          0 < rec.t_tts_start < rec.t_tts_first_chunk <= rec.t_playback_start
          < rec.t_playback_done <= rec.t_tts_done,
          f"{rec.t_tts_start:.3f} {rec.t_tts_first_chunk:.3f} "
          f"{rec.t_playback_start:.3f} {rec.t_playback_done:.3f} {rec.t_tts_done:.3f}")


def test_first_audio_latency_beats_blocking():
    tts_stream = FakeStreamingTTS(n_chunks=6, chunk_n=2400, delay=0.05)
    sp = make_speaker(tts_stream)
    rec = make_rec()
    with fake_aplay():
        sp.speak("Hello world.", mic=FakeMic(), turn_rec=rec)
    stream_first = rec.t_tts_first_chunk - rec.t_tts_start

    tts_block = FakeBlockingTTS(synth_delay=0.4)
    sp2 = make_speaker(tts_block)
    rec2 = make_rec()
    with fake_aplay():
        sp2.speak("Hello world.", mic=FakeMic(), turn_rec=rec2)
    block_first = rec2.t_tts_first_chunk - rec2.t_tts_start
    check("latency: streaming first-audio beats blocking",
          stream_first < 0.25 and block_first > 0.35 and stream_first < block_first,
          f"stream={stream_first:.3f}s block={block_first:.3f}s")


def test_blocking_when_no_stream_override():
    tts = FakeBlockingTTS()
    sp = make_speaker(tts)
    check("no-override: streaming not engaged",
          sp._tts_supports_streaming() is False)
    with fake_aplay():
        sp.speak("Hello world.", mic=FakeMic())
    popen = FakePopen.instances[0]
    check("no-override: wav-file playback (no raw mode)",
          "-t" not in popen.cmd and popen.cmd[-1].endswith(".wav"),
          " ".join(popen.cmd))
    check("no-override: synthesize_to_wav called", tts.synth_calls == 1)


def test_fallback_on_early_stream_failure():
    tts = FakeStreamingTTS(n_chunks=4, fail_at=0)
    sp = make_speaker(tts)
    with fake_aplay():
        interrupted = sp.speak("Hello world.", mic=FakeMic())
    check("early-fail: falls back, no interruption", interrupted is False)
    check("early-fail: blocking synthesize called once", tts.synth_calls == 1)
    popen = FakePopen.instances[-1]
    check("early-fail: fallback plays a wav file",
          "-t" not in popen.cmd and popen.cmd[-1].endswith(".wav"),
          " ".join(popen.cmd))


def test_bargein_and_gate_blocks_rms_only():
    # Loud mic but VAD score 0.0: the AND gate (score AND rms) must NOT
    # trigger — this is the speaker-bleed protection.
    tts = FakeStreamingTTS(n_chunks=8, chunk_n=2400, delay=0.0)
    sp = make_speaker(tts)
    with fake_aplay():
        interrupted = sp.speak("Hello world.",
                               mic=FakeMic(loud_from=3), turn_rec=make_rec())
    popen = FakePopen.instances[0]
    n_written = len(popen.stdin_bytes) // (2400 * 4)
    check("and-gate: rms alone does not interrupt", interrupted is False)
    check("and-gate: all chunks played", n_written == 8,
          f"chunks written={n_written}")


def test_bargein_needs_vad_score():
    # Same setup but vad_score=0.95 so the AND gate (score AND rms) passes.
    tts = FakeStreamingTTS(n_chunks=8, chunk_n=2400, delay=0.0)
    sp = make_speaker(tts, vad_score=0.95)
    with fake_aplay():
        interrupted = sp.speak("Hello world.",
                               mic=FakeMic(loud_from=3), turn_rec=make_rec())
    popen = FakePopen.instances[0]
    n_written = len(popen.stdin_bytes) // (2400 * 4)
    check("barge-in+vad: interrupted", interrupted is True)
    check("barge-in+vad: stopped after 2 chunks", n_written == 2,
          f"chunks written={n_written}")


def test_midstream_failure_disables_streaming():
    # Two long sentences (each > max_chars so sentence_chunks keeps them
    # separate); the generator dies on chunk 1 of the first.
    s1 = "Alpha " * 60 + "."
    s2 = "Beta " * 60 + "."
    tts = FakeStreamingTTS(n_chunks=4, chunk_n=1200, delay=0.0, fail_at=1)
    sp = make_speaker(tts)
    with fake_aplay():
        interrupted = sp.speak(f"{s1} {s2}", mic=FakeMic(), turn_rec=make_rec)
    check("mid-fail: no exception, not interrupted", interrupted is False)
    check("mid-fail: second sentence used blocking fallback",
          tts.synth_calls == 1, f"synth_calls={tts.synth_calls}")
    # First sentence's partial chunk was played, never replayed: exactly
    # one streaming attempt (first sentence) happened.
    check("mid-fail: streaming attempted once", tts.stream_calls == 1)


class FakeAvatar:
    def preload(self, wav): return True
    def play(self): pass
    def stop(self): pass


def test_avatar_forces_blocking():
    tts = FakeStreamingTTS(n_chunks=4, delay=0.0)
    sp = make_speaker(tts, avatar=FakeAvatar())
    with fake_aplay():
        sp.speak("Hello world.", mic=FakeMic())
    check("avatar: streaming not used (lip-sync needs full wav)",
          tts.stream_calls == 0 and tts.synth_calls == 1)


def test_missing_sample_rate_falls_back():
    tts = FakeStreamingTTS(n_chunks=4, delay=0.0, sample_rate=None)
    sp = make_speaker(tts)
    with fake_aplay():
        sp.speak("Hello world.", mic=FakeMic())
    check("no-sr: falls back to blocking",
          tts.stream_calls == 0 and tts.synth_calls == 1)


def test_speak_stream_uses_streaming():
    tts = FakeStreamingTTS(n_chunks=2, chunk_n=1200, delay=0.0)
    sp = make_speaker(tts)
    with fake_aplay():
        interrupted, full = sp.speak_stream(
            ["Hello ", "world. And more."], mic=FakeMic())
    popen = FakePopen.instances[0]
    check("speak_stream: benefits from streaming path",
          "-t" in popen.cmd and "FLOAT_LE" in popen.cmd
          and tts.stream_calls >= 1 and tts.synth_calls == 0,
          f"stream_calls={tts.stream_calls} synth_calls={tts.synth_calls}")
    check("speak_stream: full text returned",
          full == "Hello world. And more." and interrupted is False, repr(full))


def test_far_end_tap_on_stream():
    tapped: list = []
    tts = FakeStreamingTTS(n_chunks=3, chunk_n=2400, delay=0.0)
    sp = make_speaker(tts, far_end_cb=tapped.append)
    with fake_aplay():
        sp.speak("Hello world.", mic=FakeMic())
    check("far-end: tap fired once", len(tapped) == 1, f"n={len(tapped)}")
    if tapped:
        pcm = tapped[0]
        # 3 chunks x 2400 samples @24kHz, resampled to the 16kHz mic rate.
        expect = int(3 * 2400 * 16000 / _SR)
        check("far-end: int16 at mic rate (16000)",
              pcm.dtype == np.int16 and pcm.shape == (expect,),
              f"{pcm.dtype} {pcm.shape}")


def test_abc_default_generate_stream():
    tts = FakeBlockingTTS()
    chunks = list(tts.generate_stream("hi"))
    check("abc-default: yields one float32 chunk",
          len(chunks) == 1 and chunks[0].dtype == np.float32
          and chunks[0].size == 4800 and np.abs(chunks[0]).max() <= 1.0,
          f"n={len(chunks)}")
    check("abc-default: sample_rate is None", tts.sample_rate is None)


def test_qwen3_advertised_batch():
    check("qwen3: streaming=False (upstream is offline-only)",
          Qwen3TTS.capabilities().streaming is False)


def test_wyoming_tts_generate_stream():
    import socket

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                ev = read_event(self.request, timeout=10)
            except W.WyomingProtocolError:
                return  # connect-only probe
            assert ev.type == "synthesize", ev.type
            write_event(self.request, "audio-start",
                        {"rate": 22050, "width": 2, "channels": 1})
            for _ in range(3):
                pcm = (np.arange(2205, dtype=np.int16) % 100).tobytes()
                write_event(self.request, "audio-chunk",
                            {"rate": 22050, "width": 2, "channels": 1},
                            payload=pcm)
            write_event(self.request, "audio-stop", {})

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    srv.allow_reuse_address = True
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        raw = {"slot": "tts", "name": "wy-stream", "transport": "tcp",
               "port": port}
        entry = _validate_entry(raw, 0)
        cls = make_wyoming_provider(entry)
        prov = cls({})
        check("wyoming: streaming advertised",
              cls.capabilities().streaming is True)
        check("wyoming: generate_stream overridden",
              type(prov).generate_stream is not TTSProvider.generate_stream)
        chunks = list(prov.generate_stream("hello"))
        check("wyoming: 3 float32 chunks yielded",
              len(chunks) == 3 and all(c.dtype == np.float32 for c in chunks)
              and all(c.shape == (2205,) for c in chunks),
              f"n={len(chunks)}")
        check("wyoming: sample_rate from audio-start",
              prov.sample_rate == 22050, f"sr={prov.sample_rate}")
    finally:
        srv.shutdown()
        srv.server_close()


def test_capability_summary_helper():
    from echo_node.adapters.ui_helpers import format_capability_summary
    check("cap-summary: kokoro",
          format_capability_summary(
              Capability(name="k", streaming=False, languages=["en"],
                         gpu_required=False, license="Apache-2.0",
                         notes="fast")) == "batch · en · CPU · Apache-2.0 — fast")
    check("cap-summary: streaming gpu",
          format_capability_summary(
              Capability(name="d", streaming=True, languages=["en", "zh"],
                         gpu_required=True, vram_gb=4.0, network=True))
          == "streaming · en/zh · GPU~4GB · network")
    check("cap-summary: none/empty",
          format_capability_summary(None) == ""
          and format_capability_summary(Capability(name="x")) == "batch · CPU")


def main() -> int:
    print("TTS streaming conformance")
    fns = sorted([(k, v) for k, v in globals().items()
                   if k.startswith("test_") and callable(v)])
    for name, fn in fns:
        print(f"— {name}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — one bad test must not hide the rest
            globals()["FAIL"] += 1
            print(f"  FAIL {name} raised {type(exc).__name__}: {exc}")
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
