"""
Echo-Node Pipeline Integrations — Hermes Agent, Pi Agent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import requests


class HermesIntegration:
    """Direct Hermes integration via its API server.

    This is a thin wrapper around LLMRouter that ensures Hermes-specific
    defaults are always correct.
    """

    def __init__(self, config: dict[str, Any]):
        self.base_url = str(config.get("base_url", "http://127.0.0.1:8642/v1")).rstrip("/")
        self.api_key = str(config.get("api_key", "") or os.environ.get("HERMES_API_KEY", ""))
        self.model = str(config.get("model", "hermes-agent"))
        self.timeout = float(config.get("timeout_seconds", 90))

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url.rstrip('/v1')}/health", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def chat(self, text: str, system: str = "") -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return str(r.json()["choices"][0]["message"]["content"]).strip()
        except Exception as exc:
            return f"Hermes error: {exc}"

    def chat_stream(self, text: str, system: str = ""):
        """Stream response tokens from Hermes. Yields (token, is_first) tuples.
        
        is_first is True for the first non-empty token.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
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
                        yield piece, first
                        first = False
        except Exception as exc:
            yield f"Hermes stream error: {exc}", False


class PiIntegration:
    """Native Pi agent integration via subprocess."""

    def __init__(self, config: dict[str, Any]):
        self.command = config.get("command", ["pi", "-p"])
        self.timeout = int(config.get("timeout_seconds", 120))

    def is_available(self) -> bool:
        return shutil.which(self.command[0]) is not None

    def chat(self, text: str, system: str = "") -> str:
        cmd = self.command + [text]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            return output
        except subprocess.TimeoutExpired:
            return f"Pi agent timed out after {self.timeout}s."
        except Exception as exc:
            return f"Pi agent error: {exc}"


# ── Config validation ─────────────────────────────────────────────────