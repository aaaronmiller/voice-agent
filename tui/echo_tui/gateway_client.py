"""Gateway WebSocket client for the TUI frontend."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import websockets


class GatewayClient:
    """Connects to the Echo-Node gateway via WebSocket."""

    def __init__(self, url: str):
        self.url = url
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._handlers: dict[str, list[Callable]] = {}
        self._connected = False

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler."""
        self._handlers.setdefault(event, []).append(handler)

    def _emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._handlers.get(event, []):
            handler(*args, **kwargs)

    async def connect(self) -> None:
        """Connect to the gateway WebSocket."""
        self.ws = await websockets.connect(self.url)
        self._connected = True

    async def send(self, message: dict) -> None:
        """Send a JSON message to the gateway."""
        if self.ws and self._connected:
            await self.ws.send(json.dumps(message))

    async def message_loop(self) -> None:
        """Receive and dispatch messages from the gateway."""
        while self._connected and self.ws:
            try:
                raw = await self.ws.recv()
            except websockets.ConnectionClosed:
                self._connected = False
                self._emit("disconnected")
                break

            try:
                data = json.loads(raw)
                self._dispatch(data)
            except json.JSONDecodeError:
                continue

    def _dispatch(self, data: dict) -> None:
        """Dispatch a message to the appropriate handler."""
        msg_type = data.get("type", "")

        if msg_type == "state_change":
            self._emit("state_change", data.get("state", ""))

        elif msg_type == "transcript":
            self._emit("transcript",
                       data.get("text", ""),
                       data.get("source", ""),
                       data.get("final", False))

        elif msg_type == "latency":
            self._emit("latency", data.get("metrics", data))

        elif msg_type == "latency_snapshot":
            self._emit("latency_snapshot", data.get("snapshot", {}))

        elif msg_type == "providers":
            self._emit("providers", data.get("list", []))

        elif msg_type == "error":
            self._emit("error", data.get("message", ""))

    async def close(self) -> None:
        """Close the connection."""
        self._connected = False
        if self.ws:
            await self.ws.close()
