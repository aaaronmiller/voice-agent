"""Agent backends for Echo-Node.

Each backend implements the ``AgentBackend`` interface and can be selected
at runtime via the avatar settings popup (or config.yaml).

Available backends:
  hermes      → Hermes Agent (localhost:8642)
  pi          → Pi agent subprocess
  claude      → Claude Code headless (claude -p "...")
  codex       → Codex CLI (codex "...")
  openai      → OpenAI API (direct)
  openrouter  → OpenRouter API (direct)

Experimental (voice-native, standalone CLI only — not text chat backends):
  gemini_live     → Gemini Multimodal Live API
  openai_realtime → OpenAI Realtime API

A CLI backend (claude / codex) is useful when you want local tool-calling
without running a full agent server.  A direct API backend (openai /
openrouter) is useful when you want a specific model and don't need tools.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from echo_node.slots import Capability
from echo_node.slots.validation import (
    ValidationResult,
    check_binary,
    check_env,
    check_http,
    check_paths,
    missing_result,
    ok_result,
)

_V2_ROOT = Path(__file__).resolve().parent.parent


def _env_or_missing(*names: str) -> ValidationResult | None:
    """Return a missing-API-key result, or None if all *names* are set."""
    missing = check_env(*names)
    if missing:
        return missing_result(f"API key ({' or '.join(missing)})",
                              {"env": missing})
    return None


def _cli_or_missing(binary: str, *env_names: str) -> ValidationResult | None:
    """Check CLI binary + env keys; return failure result or None."""
    found, path = check_binary(binary)
    if not found:
        return missing_result(binary, {"binary": path})
    if env_names:
        return _env_or_missing(*env_names)
    return None


# ── Backend registry ────────────────────────────────────────────────

def _spoken_error(name: str, exc: Exception) -> str:
    """Build a TTS-safe error message for a failed backend call.

    Backend ``chat()`` results flow straight into TTS in the assistant
    loop, so a failure must come back as a speakable sentence — never a
    raw traceback or a ``[bracket tag]`` the voice would read aloud.
    Mirrors ``backend_error_message()`` in ``assistant_v2.py``.
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 402:
            return f"The {name} backend needs credits or payment for that model."
        if status == 429:
            return f"The {name} backend is rate limiting requests. Try again later."
        if status == 401:
            return f"The {name} backend rejected the API key."
        if status == 404:
            return f"The {name} backend could not find that model."
        return f"The {name} backend returned HTTP {status}."
    return f"The {name} backend did not answer: {exc}"


@dataclass
class AgentBackend(ABC):
    """Interface all backends must implement.

    Subclasses set ``name`` and ``config_key`` as class-level constants
    so the settings popup can auto-discover them.
    """

    name: str = ""              # human-readable label for the settings popup
    config_key: str = ""        # key in config.yaml (backend.provider)
    config: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend can be used right now."""
        ...

    @abstractmethod
    def chat(self, text: str, system: str = "") -> str:
        """Send a single-turn prompt and return the full response text."""
        ...

    def chat_stream(self, text: str, system: str = "") -> Iterable[tuple[str, bool]]:
        """Yield ``(token, is_first)`` pairs for streaming TTS.

        The default implementation wraps ``chat()`` as a single chunk.
        Override this for true streaming backends.
        """
        result = self.chat(text, system)
        if result:
            yield result, True


# ── Hermes Agent ────────────────────────────────────────────────────

class HermesBackend(AgentBackend):
    name: str = "Hermes Agent"
    config_key: str = "hermes"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="hermes",
            languages=["en"],
            streaming=True,   # chat_stream() implements SSE streaming
            gpu_required=False,  # server-side concern, not the client's
            license="unknown",
            network=False,       # localhost / LAN server
            notes="local Hermes agent server (default http://127.0.0.1:8642)",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        cfg = config or {}
        base = str(cfg.get("base_url", "http://127.0.0.1:8642/v1")).rstrip("/")
        health = (base[:-3] if base.endswith("/v1") else base).rstrip("/") + "/health"
        ok, info = check_http(health, timeout=1.5)
        if ok:
            return ok_result(f"Hermes server reachable ({info})",
                             {"health_url": health})
        return ValidationResult(False, f"Hermes server not reachable: {info}",
                                {"health_url": health})

    def is_available(self) -> bool:
        try:
            base = str(self.config.get("base_url", "http://127.0.0.1:8642/v1")).rstrip("/")
            # Strip a trailing "/v1" API suffix with endswith(), NOT str.rstrip():
            # rstrip("/v1") strips a *character set*, so "http://host:8641/v1"
            # would be corrupted to "http://host:864".
            health = (base[:-3] if base.endswith("/v1") else base).rstrip("/") + "/health"
            r = requests.get(health, timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def chat(self, text: str, system: str = "") -> str:
        base = str(self.config.get("base_url", "http://127.0.0.1:8642/v1")).rstrip("/")
        key = str(self.config.get("api_key", "") or os.environ.get("HERMES_API_KEY", ""))
        model = str(self.config.get("model", "hermes-agent"))
        timeout = float(self.config.get("timeout_seconds", 90))

        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})

        try:
            r = requests.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "stream": False},
                timeout=timeout,
            )
            r.raise_for_status()
            return str(r.json()["choices"][0]["message"]["content"]).strip()
        except Exception as exc:
            return _spoken_error("Hermes", exc)

    def chat_stream(self, text: str, system: str = "") -> Iterable[tuple[str, bool]]:
        base = str(self.config.get("base_url", "http://127.0.0.1:8642/v1")).rstrip("/")
        key = str(self.config.get("api_key", "") or os.environ.get("HERMES_API_KEY", ""))
        model = str(self.config.get("model", "hermes-agent"))
        timeout = float(self.config.get("timeout_seconds", 90))

        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})

        try:
            with requests.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "stream": True},
                timeout=timeout,
                stream=True,
            ) as r:
                r.raise_for_status()
                first = True
                for line in r.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    payload = decoded[6:].strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    piece = str(data.get("choices", [{}])[0].get("delta", {}).get("content", "") or "")
                    if piece:
                        yield piece, first
                        first = False
        except Exception as exc:
            yield _spoken_error("Hermes", exc), True


# ── Pi Agent ────────────────────────────────────────────────────────

class PiBackend(AgentBackend):
    name: str = "Pi Agent"
    config_key: str = "pi_agent"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.command = list(config.get("command", ["pi", "-p"]))
        self.timeout = int(config.get("timeout_seconds", 120))

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="pi",
            languages=["en"],
            streaming=False,  # subprocess.run captures full output
            gpu_required=False,
            license="unknown",
            network=False,
            notes="pi CLI subprocess (local tool-calling agent)",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        bad = _cli_or_missing("pi")
        if bad:
            return bad
        return ok_result("pi CLI present", {"binary": check_binary("pi")[1]})

    def is_available(self) -> bool:
        return shutil.which(self.command[0]) is not None

    def chat(self, text: str, system: str = "") -> str:
        cmd = self.command + [text]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            return (result.stdout or result.stderr or "(no output)").strip()
        except subprocess.TimeoutExpired:
            return f"The Pi agent timed out after {self.timeout} seconds."
        except Exception as exc:
            return _spoken_error("Pi", exc)


# ── Claude Code (headless) ──────────────────────────────────────────

class ClaudeCodeBackend(AgentBackend):
    """Runs ``claude -p "<text>" --output-format text`` in headless mode.

    Requires the ``claude`` CLI and ``ANTHROPIC_API_KEY`` environment
    variable to be set.
    """

    name: str = "Claude Code"
    config_key: str = "claude"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.command = list(config.get("command", ["claude", "-p"]))
        self.timeout = int(config.get("timeout_seconds", 120))
        self._check = None  # cached is_available result

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="claude",
            languages=["en"],
            streaming=False,  # subprocess.run captures full output
            gpu_required=False,
            license="unknown",
            network=True,       # calls the Anthropic API
            notes="claude CLI headless (-p); needs ANTHROPIC_API_KEY",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        bad = _cli_or_missing("claude", "ANTHROPIC_API_KEY")
        if bad:
            return bad
        return ok_result("claude CLI + ANTHROPIC_API_KEY present",
                         {"binary": check_binary("claude")[1]})

    def is_available(self) -> bool:
        if self._check is not None:
            return self._check
        # Need both the CLI binary AND an API key
        has_cli = shutil.which(self.command[0]) is not None
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self._check = has_cli and has_key
        return self._check

    def chat(self, text: str, system: str = "") -> str:
        if system:
            full_prompt = f"{system}\n\n{text}"
        else:
            full_prompt = text
        # Claude Code supports: claude -p "prompt" --output-format text
        cmd = self.command + [full_prompt, "--output-format", "text", "--no-progress"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            return (result.stdout or result.stderr or "(no output)").strip()
        except subprocess.TimeoutExpired:
            return f"Claude Code timed out after {self.timeout} seconds."
        except Exception as exc:
            return _spoken_error("Claude Code", exc)


# ── Codex CLI ───────────────────────────────────────────────────────

class CodexBackend(AgentBackend):
    """Runs ``codex "<text>"``.

    Requires the ``codex`` CLI and ``OPENAI_API_KEY`` environment variable.
    """

    name: str = "Codex CLI"
    config_key: str = "codex"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.command = list(config.get("command", ["codex"]))
        self.timeout = int(config.get("timeout_seconds", 120))
        self._check = None

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="codex",
            languages=["en"],
            streaming=False,  # subprocess.run captures full output
            gpu_required=False,
            license="unknown",
            network=True,       # calls the OpenAI API
            notes="codex CLI; needs OPENAI_API_KEY",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        bad = _cli_or_missing("codex", "OPENAI_API_KEY")
        if bad:
            return bad
        return ok_result("codex CLI + OPENAI_API_KEY present",
                         {"binary": check_binary("codex")[1]})

    def is_available(self) -> bool:
        if self._check is not None:
            return self._check
        has_cli = shutil.which("codex") is not None
        has_key = bool(os.environ.get("OPENAI_API_KEY"))
        self._check = has_cli and has_key
        return self._check

    def chat(self, text: str, system: str = "") -> str:
        # Codex doesn't support system prompt directly, prepend if needed
        if system:
            full_prompt = f"{system}\n\n{text}"
        else:
            full_prompt = text
        cmd = self.command + [full_prompt]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            return (result.stdout or result.stderr or "(no output)").strip()
        except subprocess.TimeoutExpired:
            return f"Codex timed out after {self.timeout} seconds."
        except Exception as exc:
            return _spoken_error("Codex", exc)


# ── Direct OpenAI API ───────────────────────────────────────────────

class OpenAIBackend(AgentBackend):
    """Calls the OpenAI Chat Completions API directly.

    Config (under ``backend`` section):
      api_key: "<key>"         (or OPENAI_API_KEY env var)
      model: "gpt-4o"          (default)
      base_url: "https://api.openai.com/v1"
      timeout_seconds: 60
      max_history_turns: 0     (0 = single-turn, >0 maintains conversation)
    """

    name: str = "OpenAI API"
    config_key: str = "openai"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.api_key = str(config.get("api_key", "") or os.environ.get("OPENAI_API_KEY", ""))
        self.model = str(config.get("model", "gpt-4o"))
        self.base_url = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.timeout = float(config.get("timeout_seconds", 60))
        self.max_history = int(config.get("max_history_turns", 0))
        self._history: list[dict[str, str]] = []

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="openai",
            languages=["en"],
            streaming=True,   # chat_stream() implements SSE streaming
            gpu_required=False,
            license="unknown",
            network=True,
            notes="direct OpenAI Chat Completions API; needs OPENAI_API_KEY",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        cfg = config or {}
        if str(cfg.get("api_key", "")).strip():
            return ok_result("api_key present in config", {})
        bad = _env_or_missing("OPENAI_API_KEY")
        if bad:
            return bad
        return ok_result("OPENAI_API_KEY present", {})

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _reset_history(self) -> None:
        self._history = []

    def chat(self, text: str, system: str = "") -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        # Include history if configured
        if self.max_history > 0 and self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": text})

        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            reply = str(data["choices"][0]["message"]["content"]).strip()

            # Maintain history
            if self.max_history > 0:
                self._history.append({"role": "user", "content": text})
                self._history.append({"role": "assistant", "content": reply})
                # Trim to max_history * 2 (user+assistant pairs)
                if len(self._history) > self.max_history * 2:
                    self._history = self._history[-(self.max_history * 2):]

            return reply
        except Exception as exc:
            return _spoken_error("OpenAI", exc)

    def chat_stream(self, text: str, system: str = "") -> Iterable[tuple[str, bool]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if self.max_history > 0 and self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": text})

        full_reply: list[str] = []
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={"model": self.model, "messages": messages, "stream": True},
                timeout=self.timeout,
                stream=True,
            ) as r:
                r.raise_for_status()
                first = True
                for line in r.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    payload = decoded[6:].strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    piece = str(data.get("choices", [{}])[0].get("delta", {}).get("content", "") or "")
                    if piece:
                        full_reply.append(piece)
                        yield piece, first
                        first = False
        except Exception as exc:
            yield _spoken_error("OpenAI", exc), True
            return

        # Store assistant reply in history
        if self.max_history > 0 and full_reply:
            reply = "".join(full_reply).strip()
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": reply})
            if len(self._history) > self.max_history * 2:
                self._history = self._history[-(self.max_history * 2):]


# ── Direct OpenRouter API ───────────────────────────────────────────

class OpenRouterBackend(AgentBackend):
    """Calls the OpenRouter Chat Completions API directly.

    Config (under ``backend`` section):
      api_key: "<key>"         (or OPENROUTER_API_KEY env var)
      model: "gpt-4o"          (default OpenRouter model name)
      timeout_seconds: 60
      max_history_turns: 0
    """

    name: str = "OpenRouter API"
    config_key: str = "openrouter"

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.api_key = str(config.get("api_key", "") or os.environ.get("OPENROUTER_API_KEY", ""))
        self.model = str(config.get("model", "openai/gpt-4o"))
        self.timeout = float(config.get("timeout_seconds", 90))
        self.max_history = int(config.get("max_history_turns", 0))
        self._history: list[dict[str, str]] = []

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="openrouter",
            languages=["en"],
            streaming=True,   # chat_stream() implements SSE streaming
            gpu_required=False,
            license="unknown",
            network=True,
            notes="OpenRouter Chat Completions API; needs OPENROUTER_API_KEY",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        cfg = config or {}
        if str(cfg.get("api_key", "")).strip():
            return ok_result("api_key present in config", {})
        bad = _env_or_missing("OPENROUTER_API_KEY")
        if bad:
            return bad
        return ok_result("OPENROUTER_API_KEY present", {})

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, text: str, system: str = "") -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if self.max_history > 0 and self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": text})

        try:
            r = requests.post(
                f"{self.BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/aaaronmiller/voice-agent",
                },
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            reply = str(data["choices"][0]["message"]["content"]).strip()

            if self.max_history > 0:
                self._history.append({"role": "user", "content": text})
                self._history.append({"role": "assistant", "content": reply})
                if len(self._history) > self.max_history * 2:
                    self._history = self._history[-(self.max_history * 2):]

            return reply
        except Exception as exc:
            return _spoken_error("OpenRouter", exc)

    def chat_stream(self, text: str, system: str = "") -> Iterable[tuple[str, bool]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if self.max_history > 0 and self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": text})

        full_reply: list[str] = []
        try:
            with requests.post(
                f"{self.BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/aaaronmiller/voice-agent",
                },
                json={"model": self.model, "messages": messages, "stream": True},
                timeout=self.timeout,
                stream=True,
            ) as r:
                r.raise_for_status()
                first = True
                for line in r.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    payload = decoded[6:].strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    piece = str(data.get("choices", [{}])[0].get("delta", {}).get("content", "") or "")
                    if piece:
                        full_reply.append(piece)
                        yield piece, first
                        first = False
        except Exception as exc:
            yield _spoken_error("OpenRouter", exc), True
            return

        if self.max_history > 0 and full_reply:
            reply = "".join(full_reply).strip()
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": reply})
            if len(self._history) > self.max_history * 2:
                self._history = self._history[-(self.max_history * 2):]


# ── Experimental: live-voice providers ────────────────────────────
#
# NOTE: Gemini Live and OpenAI Realtime are voice-native WebSocket
# providers, NOT text chat backends.  They run as standalone interactive
# CLI apps with their own mic/speaker loops (run from v2/):
#   python providers/gemini_live.py
#   python providers/openai_realtime.py
# They are registered here so tooling can enumerate them.  The text
# chat() path is intentionally unsupported — chat() returns a spoken-safe
# pointer to the CLI instead of faking a text response.
#
# Model IDs below were flagged STALE in the 2026-09 audit — re-verify
# against current provider docs before use:
#   gemini-3.1-flash-live-preview, gpt-4o-realtime-preview(-2024-12-17)

class GeminiLiveBackend(AgentBackend):
    """Experimental: Gemini Multimodal Live API (voice-native).

    Requires GEMINI_API_KEY.  Standalone CLI (run from v2/):
    ``python providers/gemini_live.py``.
    """

    name: str = "Gemini Live (experimental)"
    config_key: str = "gemini_live"
    # STALE? re-verify — flagged in 2026-09 audit
    default_model: str = "gemini-3.1-flash-live-preview"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="gemini_live",
            version="gemini-3.1-flash-live-preview (STALE — re-verify)",
            languages=["en"],
            streaming=True,   # voice-native WebSocket
            gpu_required=False,
            license="unknown",
            network=True,
            notes=("experimental: voice-native provider, NOT a text backend; "
                   "standalone CLI at v2/providers/gemini_live.py"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        bad = _env_or_missing("GEMINI_API_KEY")
        if bad:
            return bad
        cli = str(_V2_ROOT / "providers" / "gemini_live.py")
        missing = check_paths(cli)
        if missing:
            return missing_result(f"CLI script: {cli}", {"cli": cli})
        return ok_result("GEMINI_API_KEY + CLI script present", {"cli": cli})

    def is_available(self) -> bool:
        return bool(self.config.get("api_key") or os.environ.get("GEMINI_API_KEY"))

    def chat(self, text: str, system: str = "") -> str:
        return ("Gemini Live is a voice-native provider, not a text backend. "
                "Run it directly: python providers/gemini_live.py")


class OpenAIRealtimeBackend(AgentBackend):
    """Experimental: OpenAI Realtime API (voice-native).

    Requires OPENAI_API_KEY.  Standalone CLI (run from v2/):
    ``python providers/openai_realtime.py``.
    """

    name: str = "OpenAI Realtime (experimental)"
    config_key: str = "openai_realtime"
    # STALE? re-verify — flagged in 2026-09 audit
    default_model: str = "gpt-4o-realtime-preview-2024-12-17"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="openai_realtime",
            version="gpt-4o-realtime-preview-2024-12-17 (STALE — re-verify)",
            languages=["en"],
            streaming=True,   # voice-native WebSocket
            gpu_required=False,
            license="unknown",
            network=True,
            notes=("experimental: voice-native provider, NOT a text backend; "
                   "standalone CLI at v2/providers/openai_realtime.py"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        bad = _env_or_missing("OPENAI_API_KEY")
        if bad:
            return bad
        cli = str(_V2_ROOT / "providers" / "openai_realtime.py")
        missing = check_paths(cli)
        if missing:
            return missing_result(f"CLI script: {cli}", {"cli": cli})
        return ok_result("OPENAI_API_KEY + CLI script present", {"cli": cli})

    def is_available(self) -> bool:
        return bool(self.config.get("api_key") or os.environ.get("OPENAI_API_KEY"))

    def chat(self, text: str, system: str = "") -> str:
        return ("OpenAI Realtime is a voice-native provider, not a text backend. "
                "Run it directly: python providers/openai_realtime.py")


# ── llama-swap (local model router) ─────────────────────────────────
# Phase C (item f): treats llama-swap's OpenAI-compatible endpoint as the
# chat backend. llama-swap proxies to llama-server instances and hot-swaps
# models on demand, so this one backend serves many local models.

class LlamaSwapBackend(AgentBackend):
    """Local model router via llama-swap (OpenAI-compatible chat completions).

    Config (new ``llama_swap:`` section — added Phase C, no existing key
    renamed):
      base_url: "http://127.0.0.1:8080"   (llama-swap listener; /v1 appended)
      model: "<model id>"                 (as listed by GET /v1/models)
      api_key: ""                          (optional; llama-swap usually needs none)
      timeout_seconds: 90
    """

    name: str = "llama-swap (experimental)"
    config_key: str = "llama-swap"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.base_url = str(config.get("base_url", "http://127.0.0.1:8080")).rstrip("/")
        self.model = str(config.get("model", ""))
        self.api_key = str(config.get("api_key", "")
                           or os.environ.get("LLAMA_SWAP_API_KEY", ""))
        self.timeout = float(config.get("timeout_seconds", 90))

    def _models_url(self) -> str:
        return self.base_url + "/v1/models"

    def _chat_url(self) -> str:
        return self.base_url + "/v1/chat/completions"

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="llama-swap",
            languages=["en"],
            streaming=False,    # chat() only; chat_stream() wraps it
            gpu_required=False,  # server-side concern, not the client's
            license="unknown",
            network=True,        # localhost HTTP (127.0.0.1 by default)
            notes=("local model router: hot-swaps llama-server models behind "
                   "an OpenAI-compatible endpoint; experimental — needs a "
                   "running llama-swap server, not validated on target hardware yet"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        # Never downloads, never raises: a connection-refused/timeout
        # becomes an honest missing-result.
        cfg = config or {}
        base = str(cfg.get("base_url", "http://127.0.0.1:8080")).rstrip("/")
        url = base + "/v1/models"
        try:
            r = requests.get(url, timeout=5)
        except Exception as exc:
            return ValidationResult(
                False, f"llama-swap not reachable: {exc}", {"models_url": url})
        if r.status_code != 200:
            return ValidationResult(
                False, f"llama-swap returned HTTP {r.status_code}",
                {"models_url": url})
        try:
            data = r.json()
            models = [m.get("id") for m in data.get("data", [])
                      if isinstance(m, dict)]
        except Exception:
            models = []
        return ok_result(f"llama-swap reachable ({url})",
                         {"models_url": url, "models": models})

    def is_available(self) -> bool:
        try:
            r = requests.get(self._models_url(), timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def chat(self, text: str, system: str = "") -> str:
        if not self.model:
            return _spoken_error(
                "llama-swap", ValueError("no model configured (set llama_swap.model)"))
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            r = requests.post(
                self._chat_url(),
                headers=headers,
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        except Exception as exc:
            return _spoken_error("llama-swap", exc)


# ── Registry ────────────────────────────────────────────────────────

REGISTRY: dict[str, type[AgentBackend]] = {
    "hermes": HermesBackend,
    "pi": PiBackend,
    "claude": ClaudeCodeBackend,
    "codex": CodexBackend,
    "openai": OpenAIBackend,
    "openrouter": OpenRouterBackend,
    # Experimental voice-native providers (standalone CLI; chat() unsupported)
    "gemini_live": GeminiLiveBackend,
    "openai_realtime": OpenAIRealtimeBackend,
    # Experimental: local model router via llama-swap's OpenAI-compatible
    # endpoint (needs a running llama-swap server)
    "llama-swap": LlamaSwapBackend,
}

# Backends that stay out of settings dropdowns unless experimental
# providers are explicitly opted in (ECHO_INCLUDE_EXPERIMENTAL=1).
EXPERIMENTAL_BACKENDS: set[str] = {"gemini_live", "openai_realtime", "llama-swap"}

# Labels for the settings popup dropdown (provider_key → display name)
BACKEND_LABELS: dict[str, str] = {
    bk.config_key: bk.name
    for bk in REGISTRY.values()
}


def create_backend(provider: str, config: dict[str, Any]) -> AgentBackend:
    """Factory: instantiate the backend for *provider* with *config*.

    ``config`` should be the full config dict; each backend pulls
    its own subsection using ``config.get(backend.config_key, {})``.
    """
    cls = REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unknown backend provider: {provider!r}.  "
                         f"Choose from: {', '.join(REGISTRY)}")
    # Merge provider-level config into a single dict
    backend_cfg = dict(config.get("backend", {}))
    # Layer on the provider-specific subsection
    provider_cfg = dict(config.get(cls.config_key, {}))
    merged = {**backend_cfg, **provider_cfg}
    return cls(config=merged)


def check_backend_availability(provider: str, config: dict[str, Any]) -> bool:
    """Quick availability check without instantiating."""
    try:
        backend = create_backend(provider, config)
        return backend.is_available()
    except Exception:
        return False


# ── Backend enumeration for settings popup ──────────────────────────

# Glyph icons for the avatar settings popup (kept here so the popup code
# doesn't need its own icon table).
_BACKEND_GLYPHS: dict[str, str] = {
    "hermes": "",
    "pi": "",
    "claude": "",
    "codex": "",
    "openai": "",
    "openrouter": "",
}


def _build_backend_options() -> list[tuple[str, str, str]]:
    """Dropdown options for the settings popup, driven by the slot registry.

    Only providers that pass validation appear (experimental ones are
    excluded unless ECHO_INCLUDE_EXPERIMENTAL=1). Falls back to every
    registered non-experimental backend if validation finds nothing, so
    the popup never renders an empty dropdown. External (subprocess)
    providers get an " (external)" suffix on the label; the config key
    (userData) is unchanged.
    """
    from echo_node.slots import SlotType
    from echo_node.slots.registry import get_registry
    working = get_registry().working(SlotType.AGENT_BACKEND)
    if not working:
        working = [i for i in get_registry().all_providers(SlotType.AGENT_BACKEND)
                   if not i.experimental]
    return [(i.name,
             (i.provider_cls.name or i.name) + (" (external)" if i.external else ""),
             _BACKEND_GLYPHS.get(i.name, ""))
            for i in working]


# Ordered list of (provider_key, label, icon_glyph) for the settings popup.
# Registry-driven: validated, non-experimental backends only.
BACKEND_OPTIONS: list[tuple[str, str, str]] = _build_backend_options()
