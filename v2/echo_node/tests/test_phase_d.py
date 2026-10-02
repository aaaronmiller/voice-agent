"""Phase D conformance: Wyoming TCP adapters.

Runs as a script: ``python3 -m echo_node.tests.test_phase_d`` (or just
``python3 test_phase_d.py``) from ``v2/``. All host-side; the "servers"
are fake Wyoming TCP servers (threading socketserver) that implement
the upstream framing and event flow verified against rhasspy/wyoming
(OHF-Voice/wyoming, main, 2026-10-01). No real Wyoming server is
needed — or present — on this VM.

Checks:
  framing round-trip (header line + data blob + payload);
  STT transcribe → transcript;
  TTS synthesize → audio stream → WAV;
  wake-word detect → detection / not-detected;
  connection-refused validate() → honest missing, never raises;
  schema violations (bad transport, tcp+command, tcp+args, missing/bad
  port, tcp+unsupported slot) → ExternalProviderError;
  registry registration with external=True.
"""

from __future__ import annotations

import contextlib
import os
import socket
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from echo_node.adapters import (
    ExternalProviderError,
    _validate_entry,
    register_external_providers,
)
from echo_node.adapters import protocol as P
from echo_node.adapters import wyoming as W
from echo_node.adapters.wyoming import (
    WyomingAdapter,
    WyomingConnection,
    WyomingSTT,
    WyomingTTS,
    WyomingWakeWord,
    read_event,
    write_event,
)
from echo_node.slots import SlotType
from echo_node.slots.registry import ProviderRegistry


# ── harness ─────────────────────────────────────────────────────────

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


class _ThreadedTCP(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _BaseHandler(socketserver.BaseRequestHandler):
    def _read(self):
        return read_event(self.request, timeout=10)

    def _first_event(self):
        """First event, or None if the client just probed the port.

        validate() is a bare TCP connect probe — it disconnects without
        sending anything. A real Wyoming server tolerates that; so do we.
        """
        try:
            return self._read()
        except W.WyomingProtocolError:
            return None

    def _write(self, type_, data=None, payload=None):
        write_event(self.request, type_, data, payload)

    def _drain_audio(self):
        """Read events until audio-stop; return the event types seen."""
        seen = []
        while True:
            ev = self._read()
            seen.append(ev.type)
            if ev.type == "audio-stop":
                return seen


class FakeSTTHandler(_BaseHandler):
    seen_transcribe: dict | None = None

    def handle(self):
        ev = self._first_event()
        if ev is None:
            return  # connect-only probe (validate); nothing to do
        assert ev.type == "transcribe", ev.type
        FakeSTTHandler.seen_transcribe = dict(ev.data)
        self._drain_audio()
        self._write("transcript", {"text": "hello world"})


class FakeStreamingSTTHandler(_BaseHandler):
    def handle(self):
        ev = self._first_event()
        if ev is None:
            return  # connect-only probe (validate); nothing to do
        assert ev.type == "transcribe", ev.type
        self._drain_audio()
        # Streaming variant per upstream asr.py: chunks replace each
        # other, final transcript wins.
        self._write("transcript-chunk", {"text": "hello"})
        self._write("transcript-chunk", {"text": "hello world"})
        self._write("transcript", {"text": "hello world"})


class FakeTTSHandler(_BaseHandler):
    seen_synthesize: dict | None = None

    def handle(self):
        ev = self._first_event()
        if ev is None:
            return  # connect-only probe (validate); nothing to do
        assert ev.type == "synthesize", ev.type
        FakeTTSHandler.seen_synthesize = dict(ev.data)
        self._write("audio-start", {"rate": 22050, "width": 2, "channels": 1})
        pcm = (np.arange(2205, dtype=np.int16) % 100).tobytes()
        self._write("audio-chunk", {"rate": 22050, "width": 2, "channels": 1},
                    payload=pcm)
        self._write("audio-stop", {})


class FakeWakeHandler(_BaseHandler):
    def handle(self):
        ev = self._first_event()
        if ev is None:
            return  # connect-only probe (validate); nothing to do
        assert ev.type == "detect", ev.type
        self._drain_audio()
        self._write("detection", {"name": "hey_jarvis"})


class FakeWakeSilentHandler(_BaseHandler):
    def handle(self):
        ev = self._first_event()
        if ev is None:
            return  # connect-only probe (validate); nothing to do
        assert ev.type == "detect", ev.type
        self._drain_audio()
        self._write("not-detected", {})


@contextlib.contextmanager
def fake_server(handler_cls):
    srv = _ThreadedTCP(("127.0.0.1", 0), handler_cls)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _tcp_entry(slot: str, name: str, port: int, **kw) -> dict:
    raw = {"slot": slot, "name": name, "transport": "tcp", "port": port,
           **kw}
    return _validate_entry(raw, 0)


def _wav_file(tmp: Path, samples: np.ndarray, rate: int = 16000) -> Path:
    p = tmp / "in.wav"
    P.write_wav_pcm16(p, samples, rate)
    return p


# ── 1. framing ──────────────────────────────────────────────────────

def test_framing() -> None:
    a, b = socket.socketpair()
    try:
        # Event with data + payload (like audio-chunk).
        write_event(a, "audio-chunk",
                    {"rate": 16000, "width": 2, "channels": 1},
                    payload=b"\x01\x02\x03\x04")
        ev = read_event(b, timeout=5)
        check("framing: type/data/payload round-trip",
              ev.type == "audio-chunk"
              and ev.data == {"rate": 16000, "width": 2, "channels": 1}
              and ev.payload == b"\x01\x02\x03\x04", repr(ev))

        # Event with empty data and no payload (like audio-stop {}).
        write_event(a, "audio-stop", {})
        ev = read_event(b, timeout=5)
        check("framing: empty-data event round-trip",
              ev.type == "audio-stop" and ev.data == {} and ev.payload is None,
              repr(ev))

        # Event with data, no payload.
        write_event(a, "transcript", {"text": "hi"})
        ev = read_event(b, timeout=5)
        check("framing: data-only event round-trip",
              ev.type == "transcript" and ev.data == {"text": "hi"},
              repr(ev))
    finally:
        a.close()
        b.close()


# ── 2. STT round-trip ───────────────────────────────────────────────

def test_stt(tmp: Path) -> None:
    with fake_server(FakeSTTHandler) as port:
        entry = _tcp_entry("stt", "wy-stt", port)
        cls = W.make_wyoming_provider(entry)
        check("stt: factory builds a WyomingSTT subclass",
              issubclass(cls, WyomingSTT), cls.__name__)
        check("stt: entry keeps transport/host/port",
              entry["transport"] == "tcp" and entry["host"] == "127.0.0.1"
              and entry["port"] == port, repr({k: entry[k] for k in ("transport", "host", "port")}))

        prov = cls({})
        wav = _wav_file(tmp, np.zeros(3200, dtype=np.int16))  # 0.2 s
        text = prov.transcribe(wav)
        check("stt: transcribe round-trip returns server text",
              text == "hello world", repr(text))
        seen = FakeSTTHandler.seen_transcribe
        check("stt: transcribe sent without name/language when unset",
              seen is not None and "name" not in seen and "language" not in seen,
              repr(seen))

        # Optional hints are passed through to the transcribe event.
        FakeSTTHandler.seen_transcribe = None
        entry2 = _tcp_entry("stt", "wy-stt2", port, model="tiny-int8",
                            language="en")
        prov2 = W.make_wyoming_provider(entry2)({})
        check("stt: model/language hints pass through",
              prov2.transcribe(wav) == "hello world"
              and FakeSTTHandler.seen_transcribe == {"name": "tiny-int8",
                                                     "language": "en"},
              repr(FakeSTTHandler.seen_transcribe))

        # Streaming variant: transcript-chunks then final transcript.
        with fake_server(FakeStreamingSTTHandler) as port2:
            entry3 = _tcp_entry("stt", "wy-stt3", port2)
            prov3 = W.make_wyoming_provider(entry3)({})
            check("stt: streaming transcript-chunks tolerated",
                  prov3.transcribe(wav) == "hello world")


# ── 3. TTS round-trip ───────────────────────────────────────────────

def test_tts(tmp: Path) -> None:
    with fake_server(FakeTTSHandler) as port:
        entry = _tcp_entry("tts", "wy-tts", port, voice_name="en_US-amy-medium")
        cls = W.make_wyoming_provider(entry)
        check("tts: factory builds a WyomingTTS subclass",
              issubclass(cls, WyomingTTS), cls.__name__)
        prov = cls({})
        out = tmp / "out.wav"
        prov.synthesize_to_wav("say this", out)
        samples, rate = P.read_wav_pcm16(out, target_rate=22050)
        check("tts: wav written at server sample rate with server audio",
              rate == 22050 and len(samples) == 2205
              and int(samples[0]) == 0 and int(samples[1]) == 1,
              f"rate={rate} len={len(samples)}")
        seen = FakeTTSHandler.seen_synthesize
        check("tts: synthesize carried text + voice name",
              seen is not None and seen.get("text") == "say this"
              and seen.get("voice") == {"name": "en_US-amy-medium"},
              repr(seen))


# ── 4. wake-word round-trip ─────────────────────────────────────────

def test_wake() -> None:
    chunk = (np.random.RandomState(0).rand(1600).astype(np.float32) * 2 - 1)
    with fake_server(FakeWakeHandler) as port:
        entry = _tcp_entry("wake_word", "wy-wake", port,
                           phrase_names=["hey_jarvis"])
        cls = W.make_wyoming_provider(entry)
        check("wake: factory builds a WyomingWakeWord subclass",
              issubclass(cls, WyomingWakeWord), cls.__name__)
        prov = cls({})
        detected, name, score = prov.detect(chunk)
        check("wake: detection event → (True, name, 1.0)",
              detected is True and name == "hey_jarvis" and score == 1.0,
              repr((detected, name, score)))
    with fake_server(FakeWakeSilentHandler) as port:
        entry = _tcp_entry("wake_word", "wy-wake2", port)
        prov = W.make_wyoming_provider(entry)({})
        detected, name, score = prov.detect(chunk)
        check("wake: not-detected event → (False, '', 0.0)",
              detected is False and name == "" and score == 0.0,
              repr((detected, name, score)))


# ── 5. validate() ───────────────────────────────────────────────────

def test_validate() -> None:
    with fake_server(FakeSTTHandler) as port:
        entry = _tcp_entry("stt", "wy-stt", port)
        cls = W.make_wyoming_provider(entry)
        result = cls.validate()
        check("validate: reachable server → ok", result.ok, result.reason)
        caps = cls.capabilities()
        check("validate: capabilities network+streaming",
              caps.network is True and caps.streaming is True
              and "127.0.0.1" in caps.notes, repr(caps))

    port = _free_port()  # nothing listening
    entry = _tcp_entry("stt", "wy-dead", port)
    cls = W.make_wyoming_provider(entry)
    try:
        result = cls.validate()
        crashed = False
    except Exception as exc:  # noqa: BLE001 — the point is it must not raise
        crashed, result = True, exc
    check("validate: refused connection → missing, never raises",
          not crashed and not result.ok, repr(result if not crashed else result))


# ── 6. schema violations ────────────────────────────────────────────

def test_schema() -> None:
    cases = [
        ("transport bogus",
         {"slot": "stt", "name": "x", "transport": "bogus", "port": 10300}),
        ("tcp + command",
         {"slot": "stt", "name": "x", "transport": "tcp", "port": 10300,
          "command": ["something"]}),
        ("tcp + args",
         {"slot": "stt", "name": "x", "transport": "tcp", "port": 10300,
          "args": ["--foo"]}),
        ("tcp missing port",
         {"slot": "stt", "name": "x", "transport": "tcp"}),
        ("tcp port 0",
         {"slot": "stt", "name": "x", "transport": "tcp", "port": 0}),
        ("tcp port too big",
         {"slot": "stt", "name": "x", "transport": "tcp", "port": 70000}),
        ("tcp port not a number",
         {"slot": "stt", "name": "x", "transport": "tcp", "port": "abc"}),
        ("tcp + vad slot (unsupported)",
         {"slot": "vad", "name": "x", "transport": "tcp", "port": 10300}),
        ("tcp + agent_backend slot (unsupported)",
         {"slot": "agent_backend", "name": "x", "transport": "tcp", "port": 1}),
        ("tcp bad phrase_names",
         {"slot": "wake_word", "name": "x", "transport": "tcp", "port": 10400,
          "phrase_names": "hey_jarvis"}),
    ]
    for label, raw in cases:
        try:
            _validate_entry(raw, 0)
            raised = False
            msg = ""
        except ExternalProviderError as exc:
            raised, msg = True, str(exc)
        check(f"schema: {label} → ExternalProviderError", raised, msg)

    # tcp entry without explicit host defaults to 127.0.0.1
    entry = _validate_entry(
        {"slot": "tts", "name": "x", "transport": "tcp", "port": 10200}, 0)
    check("schema: host defaults to 127.0.0.1", entry["host"] == "127.0.0.1",
          repr(entry["host"]))
    # subprocess default transport is unchanged
    entry = _validate_entry(
        {"slot": "stt", "name": "x", "command": ["builtin:stt_whispercpp.py"]}, 0)
    check("schema: default transport stays subprocess",
          entry["transport"] == "subprocess" and entry["argv"][1].endswith(
              "stt_whispercpp.py"), repr(entry))


# ── 7. registry ─────────────────────────────────────────────────────

def test_registry() -> None:
    with fake_server(FakeSTTHandler) as port:
        reg = ProviderRegistry()
        got = register_external_providers(
            {"external_providers": [
                {"slot": "stt", "name": "wyoming-whisper", "transport": "tcp",
                 "port": port, "label": "whisper (wyoming)"}]},
            reg)
        check("registry: tcp entry registers", got == ["stt/wyoming-whisper"],
              repr(got))
        info = reg.info(SlotType.STT, "wyoming-whisper")
        check("registry: external=True", info.external is True)
        check("registry: label kept", info.provider_cls.label == "whisper (wyoming)",
              info.provider_cls.label)
        working = reg.working(SlotType.STT)
        check("registry: reachable wyoming provider in working()",
              any(i.name == "wyoming-whisper" for i in working),
              repr([i.name for i in working]))
        # Name collision with a built-in is still fatal for tcp entries.
        try:
            register_external_providers(
                {"external_providers": [
                    {"slot": "stt", "name": "wyoming-whisper", "transport": "tcp",
                     "port": port}]},
                reg)
            collided = False
        except ExternalProviderError:
            collided = True
        check("registry: name collision still fatal", collided)


def main() -> int:
    print("phase D — wyoming TCP adapters")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_framing()
        test_stt(tmp)
        test_tts(tmp)
        test_wake()
        test_validate()
        test_schema()
        test_registry()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
