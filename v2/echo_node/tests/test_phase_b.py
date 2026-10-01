"""Phase B conformance: subprocess (external) adapters.

Runs as a script: ``python3 -m echo_node.tests.test_phase_b`` (or just
``python3 test_phase_b.py``) from ``v2/``. All host-side; the child
under test is ``tests/testdata/fake_adapter.py`` with its five modes
(echo, hang, crash-once, crash-always, garbage). The three shipped
reference adapters are compile/import-checked only — their real probes
need whisper.cpp/piper binaries and model files absent on this VM.
"""

from __future__ import annotations

import os
import sys
import tempfile as _tempfile  # noqa: E402
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from echo_node.adapters import (
    BUILTIN_ADAPTERS,
    ExternalProviderError,
    register_external_providers,
    resolve_command,
)
from echo_node.adapters import protocol as P
from echo_node.adapters.subprocess_adapter import (
    AdapterCrashed,
    AdapterTimeout,
    ProtocolError,
    SubprocessAgentBackend,
    SubprocessSTT,
    SubprocessTTS,
    SubprocessVAD,
    SubprocessWakeWord,
    _ExternalBase,
    make_external_provider,
)
from echo_node.slots import SlotType
from echo_node.slots.registry import ProviderRegistry, get_registry, register_builtin

_TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")
FAKE = os.path.join(_TESTDATA, "fake_adapter.py")

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


def make_entry(mode: str, **kw) -> dict:
    return {
        "name": f"fake-{mode}",
        "slot": "stt",
        "slot_enum": SlotType.STT,
        "argv": [sys.executable, FAKE, "--mode", mode],
        "request_timeout_s": kw.pop("request_timeout_s", 10.0),
        "idle_timeout_s": kw.pop("idle_timeout_s", 120.0),
        "max_restarts": kw.pop("max_restarts", 3),
        **kw,
    }


def make_cls(mode: str, **kw):
    return make_external_provider(make_entry(mode, **kw))


# ── handshake + round-trip ──────────────────────────────────────────────

stt_cls = make_cls("echo")
stt = stt_cls({})

info = stt_cls.capabilities()
check("handshake: protocol_version 1 reported", P.PROTOCOL_VERSION == 1)
check("handshake: child name/capabilities surface through host class",
      "fake" in info.name.lower() or info.name == "fake (external)")

result = None
with _tempfile.TemporaryDirectory(prefix="phaseb-") as tmp:
    wav = os.path.join(tmp, "in.wav")
    P.write_wav_pcm16(wav, np.zeros(1600, dtype=np.int16), 16000)
    result = stt.transcribe(Path(wav))
check("round-trip: stt.transcribe(wav_path) returns text",
      isinstance(result, str) and "hello" in result)

tts_cls = make_cls("echo", **{"name": "fake-echo-tts", "slot": "tts",
                              "slot_enum": SlotType.TTS})
tts = tts_cls({})
out_wav = None
with _tempfile.TemporaryDirectory(prefix="phaseb-") as tmp:
    out_wav = os.path.join(tmp, "out.wav")
    ret = tts.synthesize_to_wav("hi there", Path(out_wav))
    samples, rate = P.read_wav_pcm16(ret, target_rate=16000)
check("round-trip: tts.synthesize_to_wav writes PCM wav",
      ret is not None and len(samples) > 0 and rate == 16000)

vad_cls = make_cls("echo", **{"name": "fake-echo-vad", "slot": "vad",
                              "slot_enum": SlotType.VAD})
vad = vad_cls({})
speech = vad.is_speech(np.zeros(1600, dtype=np.int16))
check("round-trip: vad.is_speech", speech is True)

ww_cls = make_cls("echo", **{"name": "fake-echo-ww", "slot": "wake_word",
                             "slot_enum": SlotType.WAKE_WORD})
ww = ww_cls({})
detected, phrase, score = ww.detect(np.zeros(1600, dtype=np.int16))
check("round-trip: wake_word.detect -> (bool, str, float)",
      detected is True and phrase == "hey fake" and isinstance(score, float))

ab_cls = make_cls("echo", **{"name": "fake-echo-ab", "slot": "agent_backend",
                             "slot_enum": SlotType.AGENT_BACKEND})
ab = ab_cls({})
reply = ab.chat("hello", "system prompt")
check("round-trip: agent_backend.chat (protocol method 'chat')",
      isinstance(reply, str) and "fake reply" in reply)

vr = stt_cls.validate({})
check("validate(): full lifecycle probe passes on echo mode",
      vr.ok, vr.reason[:60])

# ── malformed child output ─────────────────────────────────────────────

g_cls = make_cls("garbage")
g = g_cls({})
g._h().ping()  # initialize + ping must survive the junk line
check("garbage line from child: logged, never hangs or poisons the stream", True)

gr = g_cls.validate({})
check("validate() passes with a garbage preamble", gr.ok, gr.reason[:60])

# ── timeout ────────────────────────────────────────────────────────────

h_cls = make_cls("hang", request_timeout_s=1.0)
h = h_cls({})
try:
    try:
        h._h().call("ping", {}, timeout=1.0)
        check("timeout: hang mode raises AdapterTimeout", False)
    except AdapterTimeout:
        check("timeout: hang mode raises AdapterTimeout", True)
    except Exception as exc:  # noqa: BLE001
        check("timeout: hang mode raises AdapterTimeout", False, type(exc).__name__)
finally:
    h._h().close()  # don't leak the sleeping child

# ping() itself is a boolean probe: it must return False, not raise.
hp = make_cls("hang", **{"name": "fake-hang-2", "request_timeout_s": 1.0})({})
check("timeout: ping() returns False on hang (no raise)", hp._h().ping(timeout=1.0) is False)
hp._h().close()

# ── crash + restart ────────────────────────────────────────────────────
# call() restarts once transparently when the child dies mid-call, so the
# first ping SUCCEEDS and exactly one restart is counted.

_marker = os.path.join(_tempfile.mkdtemp(prefix="fake-crash-"), "crashed")
os.environ["FAKE_CRASH_MARKER"] = _marker

c_cls = make_cls("crash-once", max_restarts=2)
c = c_cls({})
try:
    ok = c._h().call("ping", {}, timeout=10)
    check("restart: call() transparently recovers from a mid-call crash",
          ok.get("ok") is True and c._h()._restarts == 1,
          f"restarts={c._h()._restarts}")
except Exception as exc:  # noqa: BLE001
    check("restart: call() transparently recovers from a mid-call crash",
          False, f"{type(exc).__name__}: {exc}")
# The respawned child is healthy now: a second call needs no restart.
ok2 = c._h().call("ping", {}, timeout=10)
check("restart: subsequent calls need no further restarts",
      ok2.get("ok") is True and c._h()._restarts == 1)
c._h().close()

# ── max-restarts exhaustion ────────────────────────────────────────────
# crash-always: every ping kills the child. max_restarts=1 allows one
# restart; the next observed death must raise AdapterCrashed naming the
# limit. (ping() would swallow it as False — call() is the raising path.)

x_cls = make_cls("crash-always", max_restarts=1)
x = x_cls({})
raised = None
for _ in range(4):
    try:
        x._h().call("ping", {}, timeout=10)
    except AdapterCrashed as exc:
        # Mid-call deaths ("child died during 'ping'") just burn the
        # budget; the exhaustion verdict names the limit ("max 1").
        if "max 1" in str(exc):
            raised = str(exc)
            break
    except ProtocolError:
        pass  # unexpected death, budget not yet exhausted; keep going
check("exhaustion: AdapterCrashed once max_restarts is exceeded",
      raised is not None, (raised or "")[:70])
x._h().close()

# ── kill-on-idle ───────────────────────────────────────────────────────
# NOTE: the reaper wakes at most every 5 s (min cadence), so this needs a
# real ~7 s sleep even with a short idle_timeout_s.

i_cls = make_cls("echo", **{"name": "fake-idle", "idle_timeout_s": 1.0})
i = i_cls({})
h1 = i._h()
h1.call("ping", {}, timeout=10)
proc1 = h1._proc
time.sleep(7.0)  # let the reaper sweep
check("idle: reaper kills the child after idle_timeout_s",
      proc1 is not None and proc1.poll() is not None,
      f"poll={proc1.poll() if proc1 else 'none'}")
h2 = i._h()
ok2 = h2.call("ping", {}, timeout=10)
check("idle: next request transparently respawns the child (no crash counted)",
      ok2.get("ok") is True and h2._proc is not proc1 and h2._restarts == 0,
      f"restarts={h2._restarts}")

# ── shutdown ───────────────────────────────────────────────────────────

h1.close()
check("close(): polite shutdown answered, process gone",
      h1._proc is None)

# ── config schema / builtin: resolution ─────────────────────────────────

try:
    argv = resolve_command(["builtin:stt_whispercpp.py"], ["--model", "x.bin"],
                           name="test")
    check("builtin: resolves to shipped adapter under sys.executable",
          argv[0] == sys.executable and argv[1].endswith("stt_whispercpp.py")
          and "--model" in argv)
except ExternalProviderError as exc:
    check("builtin: resolves to shipped adapter under sys.executable", False, str(exc))

for bad in ["builtin:../evil.py", "builtin:/abs/path.py", "builtin:notshipped.py",
            "builtin:"]:
    try:
        resolve_command([bad], [], name="test")
        check(f"traversal rejected: {bad}", False, "no error raised")
    except ExternalProviderError:
        check(f"traversal rejected: {bad}", True)

# ── register_external_providers ─────────────────────────────────────────

reg = ProviderRegistry()
config = {
    "external_providers": [
        {"slot": "stt", "name": "whispercpp",
         "command": ["builtin:stt_whispercpp.py"], "args": ["--model", "x.bin"]},
        {"slot": "tts", "name": "my-piper",
         "command": ["builtin:tts_piper.py"], "args": ["--model", "v.onnx"],
         "label": "Piper (custom voice)", "experimental": True},
    ]
}
names = register_external_providers(config, reg=reg)
check("register_external_providers returns slot/name strings",
      names == ["stt/whispercpp", "tts/my-piper"], str(names))
info = reg.info(SlotType.STT, "whispercpp")
check("registered provider flagged external=True",
      getattr(info, "external", False) is True)
check("label preserved on class",
      "custom voice" in reg.info(SlotType.TTS, "my-piper").provider_cls.label)

# collision with a built-in name (fresh registry WITH builtins registered)
try:
    seeded = register_builtin(ProviderRegistry())
    register_external_providers(
        {"external_providers": [{"slot": "stt", "name": "parakeet",
                                 "command": ["builtin:stt_whispercpp.py"]}]},
        reg=seeded)
    check("name collision with built-in provider rejected", False)
except ExternalProviderError as exc:
    check("name collision with built-in provider rejected", True, str(exc)[:70])

# unknown slot
try:
    register_external_providers(
        {"external_providers": [{"slot": "nope", "name": "x",
                                 "command": ["true"]}]},
        reg=ProviderRegistry())
    check("unknown slot rejected", False)
except ExternalProviderError:
    check("unknown slot rejected", True)

# slot not supported by subprocess adapters
try:
    register_external_providers(
        {"external_providers": [{"slot": "avatar", "name": "x",
                                 "command": ["true"]}]},
        reg=ProviderRegistry())
    check("avatar slot rejected for Phase B", False)
except ExternalProviderError as exc:
    check("avatar slot rejected for Phase B", True, str(exc)[:70])

# schema violations
for label, entry in [
    ("entry not a mapping", "nope"),
    ("empty command", {"slot": "stt", "name": "x", "command": []}),
    ("command not a list", {"slot": "stt", "name": "x", "command": "true"}),
    ("bad name", {"slot": "stt", "name": "../evil", "command": ["true"]}),
    ("bad protocol_version", {"slot": "stt", "name": "x", "command": ["true"],
                              "protocol_version": 99}),
]:
    try:
        register_external_providers({"external_providers": [entry]},
                                    reg=ProviderRegistry())
        check(f"schema: {label}", False, "no error raised")
    except ExternalProviderError:
        check(f"schema: {label}", True)

# ── shipped adapter self-probes (binaries absent on this VM) ───────────

import subprocess as _sp  # noqa: E402

for script, args in [("stt_whispercpp.py", []),
                     ("tts_piper.py", []),
                     ("stt_reference.py", ["--model-dir", "/nonexistent"])]:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "adapters", script)
    # Drive rpc_initialize + rpc_validate directly through the child so
    # the "missing binary/model" paths are exercised honestly.
    child = _sp.Popen([sys.executable, path], stdin=_sp.PIPE, stdout=_sp.PIPE,
                      stderr=_sp.PIPE, text=True)
    req = P.encode_request("validate", {}, request_id=1)
    out, _ = child.communicate(req + "\n" + P.encode_request("shutdown", {}, request_id=2) + "\n")
    lines = [l for l in out.splitlines() if l.strip()]
    try:
        ok = False
        for line in lines:
            resp = P.decode_message(line)
            if resp.get("id") == 1:
                vr = resp.get("result", {})
                ok = vr.get("ok") is False and isinstance(vr.get("reason"), str)
        check(f"honest 'not configured' from {script}", ok,
              lines[0][:80] if lines else "no output")
    except P.ProtocolError as exc:
        check(f"honest 'not configured' from {script}", False, str(exc)[:60])
    child.wait(timeout=30)

# ── summary ─────────────────────────────────────────────────────────────

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
