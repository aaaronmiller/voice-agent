"""Tests for v2/tools/stt_ab.py (Phase C, item e).

Uses stub STT providers — no GPU, no audio, no model downloads.
"""

from __future__ import annotations

import importlib.util
import json
import time
import wave
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"

from echo_node.slots import Capability, SlotType, STTProvider
from echo_node.slots.registry import ProviderRegistry
from echo_node.slots.validation import ok_result


def load_stt_ab():
    spec = importlib.util.spec_from_file_location("stt_ab", TOOLS_DIR / "stt_ab.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


stt_ab = load_stt_ab()


# ── Stub providers ───────────────────────────────────────────────────

class FastStubSTT(STTProvider):
    def __init__(self, config):
        self.config = config
        self.loaded = False

    @classmethod
    def capabilities(cls):
        return Capability(name="fast-stub")

    @classmethod
    def validate(cls, config=None):
        return ok_result("stub always available", {})

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False

    def transcribe(self, wav_path):
        return "hello world"


class SlowStubSTT(STTProvider):
    def __init__(self, config):
        self.config = config

    def transcribe(self, wav_path):
        time.sleep(0.05)  # make it measurably slower than FastStubSTT
        return "hello world"

    def load(self):
        pass

    def unload(self):
        pass


class BrokenTranscribeSTT(STTProvider):
    def load(self):
        pass

    def unload(self):
        pass

    def transcribe(self, wav_path):
        raise RuntimeError("boom")


class BrokenLoadSTT(STTProvider):
    def __init__(self, config):
        raise ValueError("cannot construct")

    def load(self):
        pass

    def unload(self):
        pass

    def transcribe(self, wav_path):
        return "never"


def make_registry():
    reg = ProviderRegistry()
    reg.register(SlotType.STT, "fast-stub", FastStubSTT)
    reg.register(SlotType.STT, "slow-stub", SlowStubSTT)
    reg.register(SlotType.STT, "broken-transcribe", BrokenTranscribeSTT)
    reg.register(SlotType.STT, "broken-load", BrokenLoadSTT)
    return reg


@pytest.fixture()
def stubbed_ab(monkeypatch):
    """stt_ab with its registry lookup pointed at stub providers."""
    monkeypatch.setattr(stt_ab, "get_registry", make_registry)
    return stt_ab


def write_wav(path: Path, rate=16000, channels=1, sampwidth=2, seconds=1):
    frames = rate * seconds
    data = b"\x00" * frames * channels * sampwidth
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(data)


# ── arg parsing ──────────────────────────────────────────────────────

def test_parse_args_list_flag():
    args = stt_ab.parse_args(["--list"])
    assert args.list is True


def test_parse_args_requires_a_b_and_files():
    with pytest.raises(SystemExit):
        stt_ab.parse_args(["sample.wav"])
    with pytest.raises(SystemExit):
        stt_ab.parse_args(["--a", "x", "--b", "y"])


def test_parse_args_full():
    args = stt_ab.parse_args(
        ["--a", "fast-stub", "--b", "slow-stub", "--c", "x", "f1.wav",
         "--out", "r.json", "--csv", "r.csv"])
    assert args.a == "fast-stub" and args.b == "slow-stub" and args.c == "x"
    assert args.files == ["f1.wav"]
    assert args.out == "r.json" and args.csv == "r.csv"


# ── WAV validation ───────────────────────────────────────────────────

def test_check_wav_accepts_16k_mono_pcm16(tmp_path):
    p = tmp_path / "ok.wav"
    write_wav(p)
    stt_ab.check_wav(p)  # must not raise


@pytest.mark.parametrize("kwargs,expected", [
    ({"rate": 44100}, "sample rate=44100 Hz, need 16000 Hz"),
    ({"channels": 2}, "channels=2, need 1 (mono)"),
    ({"sampwidth": 1}, "sample width=1 bytes, need 2 (16-bit PCM)"),
])
def test_check_wav_rejects_bad_formats(tmp_path, kwargs, expected):
    p = tmp_path / "bad.wav"
    write_wav(p, **kwargs)
    with pytest.raises(ValueError) as excinfo:
        stt_ab.check_wav(p)
    assert expected in str(excinfo.value)


def test_check_wav_rejects_non_wav(tmp_path):
    p = tmp_path / "not.wav"
    p.write_text("this is not audio", encoding="utf-8")
    with pytest.raises(ValueError, match="not a readable WAV"):
        stt_ab.check_wav(p)


def test_check_wav_rejects_missing(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        stt_ab.check_wav(tmp_path / "nope.wav")


# ── run_ab report structure / error recording ────────────────────────

def test_run_ab_report_structure_and_winner(stubbed_ab, tmp_path):
    f1 = tmp_path / "a.wav"
    f2 = tmp_path / "b.wav"
    write_wav(f1)
    write_wav(f2)
    report = stubbed_ab.run_ab(["fast-stub", "slow-stub"], [f1, f2], stt_config={})

    assert report["harness"] == "stt_ab"
    assert set(report["providers"]) == {"fast-stub", "slow-stub"}
    for name, info in report["providers"].items():
        assert info["error"] is None
        assert info["class"].endswith("StubSTT")
    assert report["files"] == [str(f1), str(f2)]
    assert len(report["results"]) == 2
    for entry in report["results"]:
        assert set(entry["transcripts"]) == {"fast-stub", "slow-stub"}
        for t in entry["transcripts"].values():
            assert t["transcript"] == "hello world"
            assert t["error"] is None
            assert t["latency_s"] is not None and t["latency_s"] >= 0
        assert entry["winner"] == "fast-stub"  # slow stub sleeps 50ms
    assert "generated_at" in report


def test_run_ab_records_errors_without_crashing(stubbed_ab, tmp_path):
    f1 = tmp_path / "a.wav"
    write_wav(f1)
    report = stubbed_ab.run_ab(
        ["fast-stub", "broken-transcribe", "broken-load", "no-such-provider"],
        [f1], stt_config={})

    # No crash; every failing provider is an error entry in the report.
    assert report["providers"]["broken-transcribe"]["error"] is not None
    assert report["providers"]["broken-load"]["error"] is not None
    assert "no-such-provider" in report["providers"]["no-such-provider"]["error"]
    entry = report["results"][0]
    assert entry["transcripts"]["broken-transcribe"]["error"] is not None
    assert entry["transcripts"]["broken-transcribe"]["transcript"] is None
    assert entry["transcripts"]["broken-load"]["error"] is not None
    # The one healthy provider still wins.
    assert entry["winner"] == "fast-stub"


def test_run_ab_bad_wav_raises_clear_error(stubbed_ab, tmp_path):
    p = tmp_path / "bad.wav"
    p.write_text("junk", encoding="utf-8")
    with pytest.raises(ValueError, match="not a readable WAV"):
        stubbed_ab.run_ab(["fast-stub"], [p], stt_config={})


def test_winner_none_when_all_fail(stubbed_ab, tmp_path):
    f1 = tmp_path / "a.wav"
    write_wav(f1)
    report = stubbed_ab.run_ab(["broken-transcribe", "broken-load"], [f1], stt_config={})
    assert report["results"][0]["winner"] is None


def test_dedupe():
    assert stt_ab.dedupe(["a", "b", "a", "c"]) == ["a", "b", "c"]


# ── CSV output ───────────────────────────────────────────────────────

def test_write_csv(stubbed_ab, tmp_path):
    f1 = tmp_path / "a.wav"
    write_wav(f1)
    report = stubbed_ab.run_ab(["fast-stub", "broken-transcribe"], [f1], stt_config={})
    csv_path = tmp_path / "r.csv"
    stubbed_ab.write_csv(report, csv_path)
    rows = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert rows[0] == "file,provider,latency_s,transcript,error"
    assert len(rows) == 3  # header + 2 providers
    assert any("fast-stub" in r and "hello world" in r for r in rows[1:])
    assert any("broken-transcribe" in r for r in rows[1:])


# ── main() end-to-end with stubs ─────────────────────────────────────

def test_main_writes_json_and_csv(stubbed_ab, tmp_path, capsys):
    f1 = tmp_path / "a.wav"
    write_wav(f1)
    out = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"
    rc = stubbed_ab.main([
        "--a", "fast-stub", "--b", "slow-stub",
        str(f1), "--out", str(out), "--csv", str(csv_path)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["results"][0]["winner"] == "fast-stub"
    assert csv_path.exists()
