"""Configuration security gate (T010, SPEC-009).

Four refusal classes, all BEFORE capture or provider contact:

1. invalid fields — unknown provider names, bad shapes (extends the
   registry-name checks in assistant_v2.validate_config).
2. conflicting triggers — two actions bound to the same hotkey.
3. inline secrets — a credential-shaped value sitting in the YAML
   instead of a ``secret:`` / ``env:`` reference.
4. unavailable secret storage — a secret reference that cannot be
   resolved (missing env var, empty keyring entry, no backend).

Secrets are NEVER echoed: errors name the field, never the value.
Resolution order for a ``secret:`` reference: ``env:NAME`` (process
environment) → ``keyring:service/account`` (platform store) →
unresolvable (fatal for the affected path).

On Windows the keyring backend is WinVaultKeyring (Windows Credential
Manager); on Linux it is Secret Service / file fallback. ``keyring``
absent entirely = unavailable storage (refuse, do not fall back to
plaintext — there is no plaintext fallback by design).
"""

from __future__ import annotations

import os
import re
from typing import Any

# Fields that hold credentials. A non-empty plain value here is an
# inline secret and MUST be refused — credentials live behind
# secret:/env: references or dedicated env vars (see _ENV_SECRET_VARS).
SECRET_FIELDS: tuple[tuple[str, str], ...] = (
    ("hermes", "api_key"),
    ("llama_swap", "api_key"),
    ("llm", "api_key"),
    ("openrouter", "api_key"),
    ("gemini", "api_key"),
    ("openai", "api_key"),
)

# Env vars that legitimately inject secrets (assistant_v2._apply_env_overrides
# writes ECHO_*_API_KEY into config). These are recorded as references,
# not inline values — the value never comes from the file.
_ENV_SECRET_VARS: tuple[str, ...] = (
    "ECHO_LLM_API_KEY",
    "HERMES_API_KEY",
    "LLAMA_SWAP_API_KEY",
)

_SECRET_REF_RE = re.compile(r"^(env|keyring|file):\S+$")
_KEYRING_REF_RE = re.compile(r"^keyring:([^/]+)/(.+)$")
_ENV_REF_RE = re.compile(r"^env:([A-Za-z_][A-Za-z0-9_]*)$")

_HOTKEY_TRIGGER_KEYS: tuple[str, ...] = (
    "dictation_hotkey",
    "dialogue_hotkey",
    "force_listen_hotkey",
    "cancel_hotkey",
)


def _resolve_keyring(service: str, account: str) -> tuple[bool, str]:
    """Return (available, value-or-reason). Never raises."""
    try:
        import keyring
        import keyring.errors
    except ImportError:
        return False, "keyring package not installed"
    try:
        value = keyring.get_password(service, account)
    except Exception as exc:  # noqa: BLE001 — keyring backends raise broadly; probe must never raise
        return False, f"secret store error: {type(exc).__name__}"
    if not value:
        return False, (
            f"no credential stored for keyring:{service}/{account}")
    return True, value


def resolve_secret(value: Any, *, field: str) -> tuple[bool, str]:
    """Resolve a config secret value.

    Returns (ok, resolved-or-error). Accepts:
    - ``env:NAME`` → process environment (missing = unavailable).
    - ``keyring:service/account`` → platform secret store.
    - ``file:/path`` → NOT supported (would be plaintext in a file);
      refused with guidance.
    - Empty/None → treated as unset (ok, empty — caller decides whether
      the path needs a credential).
    Anything else non-empty = inline secret → refuse.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return True, ""
    if not isinstance(value, str):
        return False, f"{field}: secret must be a string reference, not {type(value).__name__}"
    text = value.strip()
    env_m = _ENV_REF_RE.match(text)
    if env_m:
        name = env_m.group(1)
        got = os.environ.get(name)
        if not got:
            return False, (
                f"{field}: references env:{name} but it is unset or empty — "
                f"set it or fix the reference before using this path")
        return True, got
    kr_m = _KEYRING_REF_RE.match(text)
    if kr_m:
        ok, result = _resolve_keyring(kr_m.group(1), kr_m.group(2))
        if not ok:
            return False, f"{field}: {result}"
        return True, result
    if text.startswith("file:"):
        return False, (
            f"{field}: file: references are not accepted (plaintext in a "
            f"file is not protected storage) — use env: or keyring:")
    # Looks like a reference with an unknown scheme?
    if _SECRET_REF_RE.match(text):
        return False, (
            f"{field}: unknown secret scheme — use env:NAME or "
            f"keyring:service/account")
    # Otherwise: a real value sitting in the file = inline secret.
    return False, (
        f"{field}: inline secret in config file — move it to protected "
        f"storage and reference it as env:NAME or keyring:service/account")


def check_trigger_conflicts(config: dict[str, Any]) -> list[str]:
    """Detect two actions bound to the same hotkey. Returns error strings."""
    hotkeys = config.get("hotkeys", {})
    if not isinstance(hotkeys, dict):
        return ["hotkeys: section must be a mapping"]
    seen: dict[str, str] = {}
    errors: list[str] = []
    for key in _HOTKEY_TRIGGER_KEYS:
        combo = hotkeys.get(key)
        if combo is None or (isinstance(combo, str) and not combo.strip()):
            continue
        if not isinstance(combo, str):
            errors.append(f"hotkeys.{key}: must be a string, got {type(combo).__name__}")
            continue
        normalized = "+".join(
            sorted(part.strip().lower() for part in combo.split("+") if part.strip()))
        if normalized in seen:
            errors.append(
                f"hotkeys.{key} conflicts with hotkeys.{seen[normalized]} "
                f"(both {combo!r}) — each action needs its own trigger")
        else:
            seen[normalized] = key
    return errors


def check_secrets(config: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Validate credential fields. Returns (errors, resolved).

    ``resolved`` maps ``section.key`` → secret value for fields that
    resolved (callers use it instead of reading the raw config).
    No secret value ever appears in ``errors``.
    """
    errors: list[str] = []
    resolved: dict[str, str] = {}
    for section, key in SECRET_FIELDS:
        sec = config.get(section)
        if not isinstance(sec, dict) or key not in sec:
            continue
        ok, result = resolve_secret(sec[key], field=f"{section}.{key}")
        if not ok:
            errors.append(result)
        elif result:
            resolved[f"{section}.{key}"] = result
    return errors, resolved


def check_secret_store_available() -> tuple[bool, str]:
    """Is there a usable protected store on this machine? Never raises."""
    try:
        import keyring
    except ImportError:
        return False, "keyring not installed — env: references still work"
    try:
        backend = str(keyring.get_keyring())
    except Exception as exc:  # noqa: BLE001 — backend discovery raises broadly; probe must never raise
        return False, f"secret store unreachable: {type(exc).__name__}"
    if "fail" in backend.lower() or "null" in backend.lower():
        return False, f"no usable secret store backend ({backend})"
    return True, backend


def security_gate(config: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Run all T010 checks. Returns (errors, resolved_secrets).

    Empty ``errors`` = the affected paths may proceed to capture /
    provider contact. Non-empty = refuse startup (caller prints each
    error and exits non-zero, no secrets included).
    """
    errors: list[str] = []
    errors.extend(check_trigger_conflicts(config))
    secret_errors, resolved = check_secrets(config)
    errors.extend(secret_errors)
    return errors, resolved
