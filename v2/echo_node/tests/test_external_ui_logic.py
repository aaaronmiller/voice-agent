"""External-providers settings UI logic (Phase C).

Qt-free: ``echo_node.adapters.ui_helpers`` plus the entry validation
round-trip and registry unregister/re-register used by the save path.
Runs as a script: ``python3 -m echo_node.tests.test_external_ui_logic``
from ``v2/``. No PyQt6 needed — that is asserted.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


# ── ui_helpers is Qt-free ────────────────────────────────────────────

import echo_node.adapters.ui_helpers as H  # noqa: E402

src = open(H.__file__, encoding="utf-8").read()
import_lines = [ln.strip() for ln in src.splitlines()
                if ln.strip().startswith(("import ", "from "))]
check("ui_helpers has no PyQt6/PySide imports",
      all("pyqt6" not in ln.lower() and "pyside" not in ln.lower()
          for ln in import_lines))
check("ui_helpers imports are stdlib-only",
      all(not ln.split()[1].split(".")[0] in {"echo_node", "PyQt6", "PySide"}
          for ln in import_lines), "; ".join(import_lines))

# ── validate_name ──────────────────────────────────────────────────

for good in ["whispercpp", "my-adapter_2.0", "A", "a.b-c_d", "x9"]:
    check(f"validate_name accepts {good!r}", H.validate_name(good) is None)
for bad, why in [("", "empty"), ("bad name", "space"), ("-lead", "leading dash"),
                 (".lead", "leading dot"), ("_lead", "leading underscore"),
                 ("a/b", "slash"), ("a:b", "colon"), (None, "non-string"),
                 ("semi;colon", "semicolon")]:
    err = H.validate_name(bad)
    check(f"validate_name rejects {bad!r} ({why})",
          isinstance(err, str) and len(err) > 0, str(err)[:60])

# ── parse/format args text ─────────────────────────────────────────

check("parse_args_text drops blanks, keeps inner spaces",
      H.parse_args_text("  /bin/a  \n\n--model\nmy model.bin\n") ==
      ["/bin/a", "--model", "my model.bin"])
check("parse/format round-trip",
      H.parse_args_text(H.format_args_text(["a", "b c", "--x"])) == ["a", "b c", "--x"])
check("format_args_text joins with newlines",
      H.format_args_text(["a", "b"]) == "a\nb")

# ── build_entry_dict ───────────────────────────────────────────────

cmd, args = ["/bin/a", "--flag"], ["--x", "1"]
entry = H.build_entry_dict(slot="stt", name="demo", command=cmd, args=args)
check("build_entry_dict shape",
      entry["slot"] == "stt" and entry["name"] == "demo"
      and entry["command"] == ["/bin/a", "--flag"] and entry["args"] == ["--x", "1"])
check("build_entry_dict defaults",
      entry["protocol_version"] == 1 and entry["request_timeout_s"] == 30.0
      and entry["idle_timeout_s"] == 120.0 and entry["max_restarts"] == 3
      and entry["label"] == "demo" and entry["experimental"] is False
      and entry["capabilities"] == {})
cmd.append("--mutated"); args.append("--mutated")
check("build_entry_dict copies lists (no aliasing)",
      entry["command"] == ["/bin/a", "--flag"] and entry["args"] == ["--x", "1"])
e2 = H.build_entry_dict(slot="tts", name="n", command=["c"], label="My Label",
                        experimental=True, request_timeout_s=5)
check("build_entry_dict honors label/experimental/timeouts",
      e2["label"] == "My Label" and e2["experimental"] is True
      and e2["request_timeout_s"] == 5.0)

# ── summarize_command ──────────────────────────────────────────────

check("summarize_command empty", H.summarize_command([]) == "(no command)")
check("summarize_command short",
      H.summarize_command(["/bin/a", "--x"]) == "/bin/a --x")
long_argv = ["python3", "/very/long/path/to/adapter.py", "--model",
             "/models/some-quite-long-model-name-here.bin", "--extra-flag"]
summ = H.summarize_command(long_argv)
check("summarize_command truncates at 72",
      len(summ) == 72 and summ.endswith("..."), summ)

# ── entry validation round-trip (UI dict -> _validate_entry) ───────

from echo_node.adapters import (  # noqa: E402
    ExternalProviderError,
    _validate_entry,
    register_external_providers,
)
from echo_node.slots import SlotType  # noqa: E402
from echo_node.slots.registry import ProviderRegistry  # noqa: E402

ui_entry = H.build_entry_dict(
    slot="stt", name="whispercpp",
    command=["builtin:stt_whispercpp.py"], args=["--model", "/m.bin"])
try:
    norm = _validate_entry(ui_entry, 0)
    check("round-trip: UI dict passes _validate_entry", True)
    check("round-trip: slot_enum resolved",
          norm["slot_enum"] is SlotType.STT and norm["slot"] == "stt")
    check("round-trip: builtin argv resolved",
          norm["argv"][0] == sys.executable and norm["argv"][1].endswith("stt_whispercpp.py"),
          " ".join(norm["argv"][:2]))
except ExternalProviderError as exc:
    check("round-trip: UI dict passes _validate_entry", False, str(exc)[:80])

bad_name_entry = H.build_entry_dict(slot="tts", name="bad name", command=["/bin/x"])
try:
    _validate_entry(bad_name_entry, 0)
    check("round-trip: bad name rejected", False, "no error raised")
except ExternalProviderError as exc:
    check("round-trip: bad name rejected", True, str(exc)[:60])

bad_slot_entry = H.build_entry_dict(slot="avatar", name="x", command=["/bin/x"])
try:
    _validate_entry(bad_slot_entry, 0)
    check("round-trip: unsupported slot rejected", False, "no error raised")
except ExternalProviderError as exc:
    check("round-trip: unsupported slot rejected", True, str(exc)[:60])

# ── registry unregister / re-register ─────────────────────────────

from echo_node.slots import Capability  # noqa: E402


class _Stub:
    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(name="stub")


reg = ProviderRegistry()
check("unregister missing entry -> False, no raise",
      reg.unregister(SlotType.STT, "nope") is False)
reg.register(SlotType.STT, "tmp-ext", _Stub, external=True)
check("unregister existing entry -> True", reg.unregister(SlotType.STT, "tmp-ext") is True)
try:
    reg.info(SlotType.STT, "tmp-ext")
    check("unregistered entry gone from info()", False)
except KeyError:
    check("unregistered entry gone from info()", True)
check("unregister twice -> False", reg.unregister(SlotType.STT, "tmp-ext") is False)
# Built-ins registered on a fresh registry survive an unrelated unregister.
from echo_node.slots.registry import register_builtin  # noqa: E402
reg2 = register_builtin(ProviderRegistry())
reg2.register(SlotType.TTS, "ext-voice", _Stub, external=True)
reg2.unregister(SlotType.TTS, "ext-voice")
check("unregister does not disturb built-ins",
      "kokoro" in reg2.all_names(SlotType.TTS)
      and "ext-voice" not in reg2.all_names(SlotType.TTS))

# ── register_external_providers + unregister + re-register ─────────

reg3 = ProviderRegistry()
cfg = {"external_providers": [H.build_entry_dict(
    slot="tts", name="piper-ext", command=["builtin:tts_piper.py"])]}
names = register_external_providers(cfg, reg3)
check("register_external_providers registers entry",
      names == ["tts/piper-ext"] and reg3.info(SlotType.TTS, "piper-ext").external is True)
check("unregister external -> True",
      reg3.unregister(SlotType.TTS, "piper-ext") is True)
names2 = register_external_providers(cfg, reg3)
check("re-register after unregister works", names2 == ["tts/piper-ext"])

# Collision with a same-named provider is still rejected.
reg4 = register_builtin(ProviderRegistry())
collide = {"external_providers": [H.build_entry_dict(
    slot="tts", name="kokoro", command=["builtin:tts_piper.py"])]}
try:
    register_external_providers(collide, reg4)
    check("name collision with built-in rejected", False, "no error raised")
except ExternalProviderError as exc:
    check("name collision with built-in rejected", True, str(exc)[:60])

# ── summary ────────────────────────────────────────────────────────

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
