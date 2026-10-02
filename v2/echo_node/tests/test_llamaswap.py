"""Tests for LlamaSwapBackend (Phase C, item f).

Uses a fake HTTP server (http.server in a thread) for the positive
validator path; the connection-refused path uses a port with nothing
listening. No network beyond localhost, no models.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import sys

V2_ROOT = Path(__file__).resolve().parents[2]
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from echo_node import backends
from echo_node.backends import LlamaSwapBackend
from echo_node.slots import SlotType
from echo_node.slots.registry import get_registry


# ── Fake llama-swap server ───────────────────────────────────────────

REQUEST_PATHS: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # keep test output clean
        pass

    def do_GET(self):
        REQUEST_PATHS.append(self.path)
        if self.path == "/v1/models":
            body = json.dumps(
                {"object": "list",
                 "data": [{"id": "qwen2.5-7b", "object": "model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def fake_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def _closed_port() -> int:
    """A localhost port that (right now) has nothing listening on it."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Validator ────────────────────────────────────────────────────────

def test_validate_ok_when_server_up(fake_server):
    REQUEST_PATHS.clear()
    result = LlamaSwapBackend.validate({"base_url": fake_server})
    assert result.ok, result.reason
    assert "reachable" in result.reason
    assert result.details["models_url"] == fake_server + "/v1/models"
    assert REQUEST_PATHS == ["/v1/models"]  # proves the URL is built as {base}/v1/models


def test_validate_default_base_url_shape():
    # No config → defaults to http://127.0.0.1:8080/v1/models; nothing
    # listens there, so we get an honest missing-result, never a raise.
    result = LlamaSwapBackend.validate()
    assert result.ok is False
    assert result.details["models_url"] == "http://127.0.0.1:8080/v1/models"


def test_validate_honest_missing_on_connection_refused():
    port = _closed_port()
    result = LlamaSwapBackend.validate({"base_url": f"http://127.0.0.1:{port}"})
    assert result.ok is False
    assert "not reachable" in result.reason
    assert result.details["models_url"] == f"http://127.0.0.1:{port}/v1/models"


def test_validate_never_raises():
    # Garbage base_url must still produce a result, not an exception.
    result = LlamaSwapBackend.validate({"base_url": "http://"})
    assert result.ok is False


# ── URL building / chat ──────────────────────────────────────────────

class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "  hi there  "}}]}


def test_chat_posts_to_chat_completions_with_model(fake_server):
    seen: dict[str, Any] = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return _FakeResponse()

    backend = LlamaSwapBackend(
        {"base_url": fake_server, "model": "qwen2.5-7b", "timeout_seconds": 5})
    with patch.object(backends.requests, "post", fake_post):
        reply = backend.chat("hello", system="be nice")
    assert reply == "hi there"  # stripped
    assert seen["url"] == fake_server + "/v1/chat/completions"
    payload = seen["kwargs"]["json"]
    assert payload["model"] == "qwen2.5-7b"
    assert payload["messages"][0] == {"role": "system", "content": "be nice"}
    assert payload["messages"][1] == {"role": "user", "content": "hello"}
    assert seen["kwargs"]["timeout"] == 5.0


def test_chat_without_model_returns_spoken_error():
    backend = LlamaSwapBackend({"base_url": "http://127.0.0.1:8080"})
    reply = backend.chat("hello")
    assert "no model configured" in reply


def test_is_available_true_when_up(fake_server):
    backend = LlamaSwapBackend({"base_url": fake_server})
    assert backend.is_available() is True


def test_is_available_false_on_refused():
    port = _closed_port()
    backend = LlamaSwapBackend({"base_url": f"http://127.0.0.1:{port}"})
    assert backend.is_available() is False


# ── Registration ─────────────────────────────────────────────────────

def test_registered_in_backends_registry():
    assert backends.REGISTRY["llama-swap"] is LlamaSwapBackend


def test_marked_experimental():
    assert "llama-swap" in backends.EXPERIMENTAL_BACKENDS


def test_registered_in_slot_registry_as_experimental():
    info = get_registry().info(SlotType.AGENT_BACKEND, "llama-swap")
    assert info.provider_cls is LlamaSwapBackend
    assert info.experimental is True


def test_config_key_and_contract():
    assert LlamaSwapBackend.config_key == "llama-swap"
    # ABC contract: is_available + chat exist and are callable on an instance
    backend = LlamaSwapBackend({"base_url": "http://127.0.0.1:8080"})
    assert callable(backend.is_available) and callable(backend.chat)


def test_capabilities():
    caps = LlamaSwapBackend.capabilities()
    assert caps.name == "llama-swap"
    assert caps.network is True
