"""T010 gate probe: all four SPEC-009 refusal classes trigger.

Runs as a script: ``python3 -m echo_node.tests.test_config_gate`` from ``v2/``.
No hardware, no network, no secrets — every case is synthetic.

1. invalid fields — unknown provider name refused.
2. conflicting triggers — same combo on two actions refused.
3. inline secrets — credential-shaped value in the file refused, field
   named, value never echoed.
4. unavailable secret storage — env:/keyring: reference that cannot be
   resolved refused.
Plus: valid references (env set) pass; empty secret (local path) passes.

The probe asserts on ``security_gate`` + ``validate_config`` directly
(same functions startup calls), so it tests the real refusal path.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echo_node.config_security import (
    check_secret_store_available,
    security_gate,
)

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(label)
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""),
          flush=True)


def _base() -> dict:
    return {
        "hotkeys": {
            "enabled": True,
            "dictation_hotkey": "ctrl+shift+a",
            "dialogue_hotkey": "",
            "force_listen_hotkey": "",
            "cancel_hotkey": "escape",
        },
        "hermes": {"base_url": "http://127.0.0.1:8642/v1", "model": "x", "api_key": ""},
    }


# 1. conflicting triggers ------------------------------------------------
cfg = _base()
cfg["hotkeys"]["dialogue_hotkey"] = "Ctrl+Shift+A"  # case/space-insensitive clash
errors, _ = security_gate(cfg)
check("conflicting triggers refused",
      any("dictation_hotkey" in e or "dialogue_hotkey" in e for e in errors),
      "; ".join(errors))

# 2. inline secret --------------------------------------------------------
cfg = _base()
cfg["hermes"]["api_key"] = "sk-live-INLINE-SECRET-XYZ"
errors, _ = security_gate(cfg)
check("inline secret refused",
      any("hermes.api_key" in e and "inline" in e for e in errors),
      "; ".join(errors))
check("inline value never echoed",
      not any("INLINE-SECRET-XYZ" in e for e in errors))

# 3. unavailable secret storage (unset env ref) ---------------------------
cfg = _base()
cfg["hermes"]["api_key"] = "env:ECHO_GATE_PROBE_UNSET_VAR"
os.environ.pop("ECHO_GATE_PROBE_UNSET_VAR", None)
errors, _ = security_gate(cfg)
check("unresolvable env: reference refused",
      any("hermes.api_key" in e and "unset" in e for e in errors),
      "; ".join(errors))

# 3b. unavailable keyring entry -------------------------------------------
cfg = _base()
cfg["hermes"]["api_key"] = "keyring:echo-node-gate-probe/definitely-missing"
errors, _ = security_gate(cfg)
check("missing keyring entry refused",
      any("hermes.api_key" in e for e in errors),
      "; ".join(errors))

# 3c. file: references refused ---------------------------------------------
cfg = _base()
cfg["hermes"]["api_key"] = "file:/tmp/would-be-plaintext.txt"
errors, _ = security_gate(cfg)
check("file: reference refused",
      any("hermes.api_key" in e for e in errors),
      "; ".join(errors))

# 4. invalid provider names (validate_config needs the registry) ------------
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import assistant_v2
    cfg = _base()
    for section in ["assistant", "audio", "wake_word", "vad", "barge_in",
                    "stt", "tts", "performance"]:
        cfg.setdefault(section, {})
    cfg["audio"].update({"backend": "alsa", "sample_rate": 16000, "chunk_size": 1280})
    cfg["stt"]["provider"] = "no-such-stt-provider"
    verrs = assistant_v2.validate_config(cfg)
    check("invalid stt.provider refused",
          any("stt.provider" in e for e in verrs), "; ".join(verrs))
except Exception as exc:  # noqa: BLE001 — probe must report, not crash, when registry unimportable
    check("invalid stt.provider refused", False, f"{type(exc).__name__}: {exc}")

# Positive controls ---------------------------------------------------------
os.environ["ECHO_GATE_PROBE_SET_VAR"] = "not-a-real-secret"
cfg = _base()
cfg["hermes"]["api_key"] = "env:ECHO_GATE_PROBE_SET_VAR"
errors, resolved = security_gate(cfg)
check("valid env: reference passes", not errors, "; ".join(errors))
check("valid reference resolves", resolved.get("hermes.api_key") == "not-a-real-secret")
del os.environ["ECHO_GATE_PROBE_SET_VAR"]

cfg = _base()  # empty key = local path, no credential needed
errors, _ = security_gate(cfg)
check("empty secret (local path) passes", not errors, "; ".join(errors))

ok, backend = check_secret_store_available()
print(f"[info] secret store: available={ok} ({backend})", flush=True)

print(f"\nT010 gate: {len(PASSED)} passed, {len(FAILED)} failed", flush=True)
sys.exit(1 if FAILED else 0)
