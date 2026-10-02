"""Surgical config.yaml block replacement (settings UI save path).

Qt-free: ``echo_node.adapters.ui_helpers.replace_top_level_block`` only.
Runs as a script: ``python3 -m echo_node.tests.test_config_surgery``
from ``v2/``.
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


import echo_node.adapters.ui_helpers as H  # noqa: E402
from echo_node.adapters.ui_helpers import replace_top_level_block  # noqa: E402

# ── ui_helpers stays stdlib-only ───────────────────────────────────

src = open(H.__file__, encoding="utf-8").read()
import_lines = [ln.strip() for ln in src.splitlines()
                if ln.strip().startswith(("import ", "from "))]
check("ui_helpers imports are stdlib-only",
      all(not ln.split()[1].split(".")[0] in {"echo_node", "PyQt6", "PySide"}
          for ln in import_lines), "; ".join(import_lines))

# ── block replaced in place; everything else byte-identical ─────────

BEFORE = """\
# Echo-Node example config

assistant:
  wake_phrase: "hey echo"

# TTS voice pick
tts:
  provider: kokoro
  voice: af_heart

external_providers:
  - slot: stt
    name: old-one
    command: ["whisper-cli"]

logging:
  level: info
"""

NEW_BLOCK = [
    "external_providers:\n",
    "  - slot: stt\n",
    "    name: new-one\n",
    '    command: ["builtin:stt_whispercpp.py"]\n',
]
out = replace_top_level_block(BEFORE, "external_providers", NEW_BLOCK)
check("replace returns text", out is not None)
assert out is not None
check("other keys/comments/blank lines preserved byte-for-byte",
      out.startswith("# Echo-Node example config\n\nassistant:\n"
                     '  wake_phrase: "hey echo"\n\n# TTS voice pick\ntts:\n'
                     "  provider: kokoro\n  voice: af_heart\n\n")
      and out.endswith("\nlogging:\n  level: info\n"))
check("old entry gone, new entry present",
      "old-one" not in out and "new-one" in out
      and "builtin:stt_whispercpp.py" in out)
check("exactly one external_providers header",
      out.count("external_providers:") == 1)

# The result must still parse to the intended entries.
import yaml  # noqa: E402
parsed = yaml.safe_load(out)
check("result parses; entries round-trip",
      parsed["external_providers"] == [
          {"slot": "stt", "name": "new-one",
           "command": ["builtin:stt_whispercpp.py"]}]
      and parsed["tts"]["provider"] == "kokoro")

# ── block inserted when absent ──────────────────────────────────────

NO_BLOCK = "# comment\n\naudio:\n  backend: alsa\n"
out2 = replace_top_level_block(NO_BLOCK, "external_providers", NEW_BLOCK)
check("insert returns text", out2 is not None)
assert out2 is not None
check("absent block appended, prefix untouched",
      out2.startswith(NO_BLOCK) and out2.count("external_providers:") == 1)
parsed2 = yaml.safe_load(out2)
check("appended result parses",
      parsed2["audio"]["backend"] == "alsa"
      and len(parsed2["external_providers"]) == 1)

# Missing trailing newline on the original file.
NO_NL = "audio:\n  backend: alsa"
out2b = replace_top_level_block(NO_NL, "external_providers", NEW_BLOCK)
check("insert without trailing newline",
      out2b is not None and yaml.safe_load(out2b)["audio"]["backend"] == "alsa")

# ── empty entries → canonical empty block ───────────────────────────

out3 = replace_top_level_block(BEFORE, "external_providers",
                               ["external_providers: []\n"])
check("empty entries produce 'external_providers: []'",
      out3 is not None and yaml.safe_load(out3)["external_providers"] == []
      and out3.count("external_providers:") == 1)

# ── inline existing block ───────────────────────────────────────────

INLINE = "a: 1\nexternal_providers: []\nb: 2\n"
out4 = replace_top_level_block(INLINE, "external_providers", NEW_BLOCK)
check("inline block replaced",
      out4 is not None and out4.count("external_providers:") == 1
      and yaml.safe_load(out4)["b"] == 2)

# ── space before colon ──────────────────────────────────────────────

SPACED = "a: 1\nexternal_providers :\n  - slot: stt\nb: 2\n"
out5 = replace_top_level_block(SPACED, "external_providers", NEW_BLOCK)
check("space-before-colon header replaced, not duplicated",
      out5 is not None and out5.count("external_providers") == 1)

# ── fallback triggers (must return None) ────────────────────────────

NESTED = "top:\n  external_providers:\n    - slot: stt\n"
check("nested occurrence → None (no silent duplication)",
      replace_top_level_block(NESTED, "external_providers", NEW_BLOCK) is None)

DUP = "external_providers:\n  - a\n\nexternal_providers:\n  - b\n"
check("duplicate top-level keys → None",
      replace_top_level_block(DUP, "external_providers", NEW_BLOCK) is None)

# Column-0 content inside the block that is not a new key (e.g. a literal
# block scalar with unindented content) → extent unclear → None.
WEIRD = "external_providers: |\nthis line is at column zero\nnext: 1\n"
check("column-0 non-key content in block → None",
      replace_top_level_block(WEIRD, "external_providers", NEW_BLOCK) is None)

check("bad key → None",
      replace_top_level_block(BEFORE, "not a key!", NEW_BLOCK) is None)
check("replacement without header → None",
      replace_top_level_block(BEFORE, "external_providers",
                              ["  - slot: stt\n"]) is None)

# A commented-out header is not a header.
COMMENTED = "# external_providers:\n#   - slot: stt\na: 1\n"
out6 = replace_top_level_block(COMMENTED, "external_providers", NEW_BLOCK)


def _header_lines(text: str) -> int:
    import re as _re
    return sum(1 for ln in text.splitlines()
               if _re.match(r"^external_providers\s*:(?=[\s#]|$)", ln))


check("commented-out header treated as absent (appended)",
      out6 is not None and out6.startswith(COMMENTED)
      and _header_lines(out6) == 1)

# ── comment between block and next key is preserved ─────────────────

COMMENT_AFTER = """\
external_providers:
  - slot: stt
    name: old

# this comment belongs to tts, not to the block
tts:
  provider: kokoro
"""
out7 = replace_top_level_block(COMMENT_AFTER, "external_providers", NEW_BLOCK)
check("comment after block preserved",
      out7 is not None
      and "# this comment belongs to tts, not to the block" in out7
      and yaml.safe_load(out7)["tts"]["provider"] == "kokoro"
      and "old" not in out7)

# Comment inside the block (between entries) does NOT truncate the span.
COMMENT_INSIDE = """\
external_providers:
  - slot: stt
    name: keep-a
  # note about the next entry
  - slot: tts
    name: keep-b
next: 1
"""
out8 = replace_top_level_block(COMMENT_INSIDE, "external_providers", NEW_BLOCK)
check("comment inside block does not truncate",
      out8 is not None and "keep-a" not in out8 and "keep-b" not in out8
      and yaml.safe_load(out8)["next"] == 1)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
