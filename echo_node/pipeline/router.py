"""
Echo-NDde Pipeline Router — LLM routing, Ollama/OpenAI/Hermes/Odysseus backends.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from typing import Any, Iterable

import requests


class LLMRouter:
    def __init__(self, config: dict[str, Any], system_prompt: str):
        self.provider = str(config.get("provider", "ollama"))
        self.base_url = str(config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.api_key = str(config.get("api_key", "") or os.environ.get("OPENROUTER_API_KEY", ""))
        self.model = str(config.get("model", "") or "")
        self.timeout = float(config.get("timeout_seconds", 60))
        self.max_history_turns = int(config.get("max_history_turns", 8))
        self.keep_alive = str(config.get("keep_alive", "30m"))
        self.stream = bool(config.get("stream", True))
        self.system_prompt = system_prompt
        self.history: list[dict[str, str]] = []

    def warmup(self) -> None:
        if self.provider == "ollama":
            self._warmup_ollama()
        elif self.provider in {"openai-compatible", "hermes"}:
            self._warmup_openai_compatible(default_model="hermes-agent" if self.provider == "hermes" else "")
        elif self.provider == "odysseus":
            print("[warmup] skipping Odysseus backend warmup", flush=True)

    def respond(self, user_text: str) -> str:
        built_in = self._built_in(user_text)
        if built_in:
            return built_in
        if self.provider == "hermes":
            return self._openai_compatible(user_text, default_model="hermes-agent")
        if self.provider == "odysseus":
            return self._odysseus(user_text)
        if self.provider == "openai-compatible":
            return self._openai_compatible(user_text)
        return self._ollama(user_text)

    def response_chunks(self, user_text: str) -> tuple[Iterable[str], bool]:
        built_in = self._built_in(user_text)
        if built_in:
            return [built_in], False
        if not self.stream:
            return [self.respond(user_text)], False
        if self.provider == "openai-compatible":
            return self._openai_compatible_chunks(user_text), True
        if self.provider == "hermes":
            return self._openai_compatible_chunks(user_text, default_model="hermes-agent"), True
        if self.provider == "ollama":
            return self._ollama_chunks(user_text), True
        return [self.respond(user_text)], False

    def remember_response(self, user_text: str, answer: str) -> None:
        if answer:
            self._remember(user_text, answer)

    @staticmethod
    def _built_in(text: str) -> str:
        lowered = text.lower().strip()
        now = dt.datetime.now().astimezone()
        if lowered in {"time", "what time is it", "what's the time"}:
            return f"It is {now:%I:%M %p}."
        if lowered in {"date", "what date is it", "what's the date"}:
            return f"Today is {now:%A, %B %d, %Y}."
        if lowered.startswith("repeat "):
            return text[7:].strip()
        return ""

    def _messages(self, user_text: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history[-self.max_history_turns * 2 :])
        messages.append({"role": "user", "content": user_text})
        return messages

    def _remember(self, user_text: str, answer: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": answer})

    def _ollama_model(self) -> str | None:
        if self.model:
            return self.model
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            return models[0].get("name") if models else None
        except Exception:
            return None

    def _ollama(self, user_text: str) -> str:
        model = self._ollama_model()
        if not model:
            return f"I heard: {user_text}. No Ollama model is installed."
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": self._messages(user_text), "stream": False, "keep_alive": self.keep_alive},
                timeout=self.timeout,
            )
            response.raise_for_status()
            answer = str(response.json().get("message", {}).get("content", "")).strip()
        except Exception as exc:
            answer = f"I heard: {user_text}. Ollama did not answer: {exc}"
        self._remember(user_text, answer)
        return answer

    def _ollama_chunks(self, user_text: str) -> Iterable[str]:
        model = self._ollama_model()
        if not model:
            yield f"I heard: {user_text}. No Ollama model is installed."
            return
        started = time.perf_counter()
        first_token: float | None = None
        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": self._messages(user_text), "stream": True, "keep_alive": self.keep_alive},
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line.decode("utf-8"))
                    piece = str(data.get("message", {}).get("content", "") or "")
                    if piece and first_token is None:
                        first_token = time.perf_counter()
                        print(f"[timing] backend_first_token={first_token - started:.2f}s model={model}", flush=True)
                    if piece:
                        yield piece
                    if data.get("done"):
                        break
            print(f"[timing] backend_stream_total={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            yield f"I heard: {user_text}. Ollama did not answer: {exc}"

    def _warmup_ollama(self) -> None:
        model = self._ollama_model()
        if not model:
            print("[warmup] skipping Ollama backend warmup; no model installed", flush=True)
            return
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "stream": False, "keep_alive": self.keep_alive, "options": {"num_predict": 1}},
                timeout=min(self.timeout, 30),
            )
            response.raise_for_status()
            print(f"[timing] backend_warm={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            print(f"[warmup] Ollama backend warmup failed: {backend_error_message(exc)}", flush=True)

    def _openai_compatible(self, user_text: str, default_model: str = "") -> str:
        model = self.model or default_model
        if not model:
            return f"I heard: {user_text}. No OpenAI-compatible model is configured."
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            started = time.perf_counter()
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": self._messages(user_text), "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            answer = str(response.json()["choices"][0]["message"]["content"]).strip()
            print(f"[timing] backend={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            answer = f"I heard: {user_text}. {backend_error_message(exc)}"
        self._remember(user_text, answer)
        return answer

    def _openai_compatible_chunks(self, user_text: str, default_model: str = "") -> Iterable[str]:
        model = self.model or default_model
        if not model:
            yield f"I heard: {user_text}. No OpenAI-compatible model is configured."
            return
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.perf_counter()
        first_token: float | None = None
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": self._messages(user_text), "stream": True},
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
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
                    if piece and first_token is None:
                        first_token = time.perf_counter()
                        print(f"[timing] backend_first_token={first_token - started:.2f}s model={model}", flush=True)
                    if piece:
                        yield piece
            print(f"[timing] backend_stream_total={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            yield f"I heard: {user_text}. {backend_error_message(exc)}"

    def _warmup_openai_compatible(self, default_model: str = "") -> None:
        model = self.model or default_model
        if not model:
            print("[warmup] skipping OpenAI-compatible backend warmup; no model configured", flush=True)
            return
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 1, "stream": False},
                timeout=min(self.timeout, 30),
            )
            response.raise_for_status()
            print(f"[timing] backend_warm={time.perf_counter() - started:.2f}s model={model}", flush=True)
        except Exception as exc:
            print(f"[warmup] OpenAI-compatible backend warmup failed: {backend_error_message(exc)}", flush=True)

    def _odysseus(self, user_text: str) -> str:
        if not self.api_key:
            return "Odysseus is configured, but no API token is set."
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {"message": user_text}
        if self.model:
            payload["model"] = self.model
        session_id = getattr(self, "_odysseus_session_id", "")
        if session_id:
            payload["session"] = session_id
        try:
            response = requests.post(f"{self.base_url}/api/v1/chat", headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            self._odysseus_session_id = str(data.get("session_id", "") or session_id)
            answer = str(data.get("response", "")).strip()
            if not answer:
                answer = "Odysseus answered, but returned an empty response."
        except Exception as exc:
            answer = f"I heard: {user_text}. {backend_error_message(exc)}"
        self._remember(user_text, answer)
        return answer


# ── Keyboard hotkey listener (non-blocking, Escape key) ─────────────