#!/usr/bin/env python3
"""
Echo-Node TUI — Terminal Voice Assistant Interface.

Full Textual-based TUI that connects to the gateway via WebSocket.
Supports push-to-talk, transcript view, live latency dashboard,
and provider switching.

Usage:
  python -m echo_tui
  python -m echo_tui --url ws://localhost:3000/ws
  python -m echo_tui --provider gemini-live
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from echo_tui.gateway_client import GatewayClient
from echo_tui.widgets.transcript import TranscriptWidget
from echo_tui.widgets.latency import LatencyWidget
from echo_tui.widgets.status import StatusWidget

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import Header, Footer, Static, Button, Select, Input
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


class EchoTUI(App):
    """Echo-Node Terminal Voice Assistant."""

    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-layout {
        height: 100%;
    }
    
    #transcript-panel {
        height: 1fr;
        border: solid $primary;
        margin: 1;
    }
    
    #latency-panel {
        height: 10;
        border: solid $secondary;
        margin: 1;
    }
    
    #control-bar {
        height: 3;
        dock: bottom;
        padding: 0 1;
    }
    
    #provider-select {
        width: 20;
    }
    
    #ptt-button {
        width: 20;
    }
    
    .metric-value {
        color: $accent;
        text-style: bold;
    }
    
    .metric-label {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("space", "push_to_talk", "Push to Talk", show=True),
        Binding("escape", "interrupt", "Interrupt", show=True),
        Binding("p", "toggle_providers", "Provider", show=False),
        Binding("l", "toggle_latency", "Latency", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, gateway_url: str, provider: str = ""):
        super().__init__()
        self.gateway = GatewayClient(gateway_url)
        self.gateway_url = gateway_url
        self.initial_provider = provider
        self._ptt_active = False
        self._metrics_collector: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-layout"):
            yield TranscriptWidget(id="transcript-panel")
            yield LatencyWidget(id="latency-panel")
            with Horizontal(id="control-bar"):
                yield Select(
                    id="provider-select",
                    prompt="Provider",
                    options=[],
                )
                yield Button("Push to Talk (Space)", id="ptt-button", variant="primary")
                yield Static(id="status-display")
        yield Footer()

    async def on_mount(self) -> None:
        """Connect to gateway on startup."""
        status = self.query_one("#status-display", Static)
        status.update("Connecting...")

        try:
            await self.gateway.connect()
            status.update("● Connected")
            self.gateway.on("state_change", self._on_state_change)
            self.gateway.on("transcript", self._on_transcript)
            self.gateway.on("latency", self._on_latency)
            self.gateway.on("providers", self._on_providers)

            # Start the message loop
            asyncio.create_task(self.gateway.message_loop())

            # Set initial provider if specified
            if self.initial_provider:
                await self.gateway.send({"type": "set_provider", "provider": self.initial_provider})

        except Exception as e:
            status.update(f"❌ Connection failed: {e}")

    def _on_state_change(self, state: str) -> None:
        """Handle state change events."""
        status = self.query_one("#status-display", Static)
        status.update(f"● {state}")

    def _on_transcript(self, text: str, source: str, final: bool) -> None:
        """Handle transcript events."""
        transcript = self.query_one("#transcript-panel", TranscriptWidget)
        prefix = "You" if source == "user" else "Assistant"
        transcript.add_line(f"[{prefix}] {text}")

    def _on_latency(self, metrics: dict) -> None:
        """Handle latency metrics."""
        self._metrics_collector.append(metrics)
        latency = self.query_one("#latency-panel", LatencyWidget)
        latency.update_metrics(metrics)

    def _on_providers(self, providers: list[dict]) -> None:
        """Handle provider list updates with pricing info."""
        select = self.query_one("#provider-select", Select)
        options = []
        for p in providers:
            name = p["name"]
            pricing = p.get("pricing", {})
            label = pricing.get("label", "") if isinstance(pricing, dict) else ""
            is_free = pricing.get("isFree", False) if isinstance(pricing, dict) else False
            if is_free or not label:
                display = f"{name} 🆓"
            else:
                display = f"{name} 💰{label}"
            options.append((display, name))
        select.set_options(options)

    @on(Button.Pressed, "#ptt-button")
    async def handle_ptt(self) -> None:
        """Push-to-talk button handler."""
        self._ptt_active = not self._ptt_active
        await self.gateway.send({
            "type": "push_to_talk",
            "active": self._ptt_active,
        })
        btn = self.query_one("#ptt-button", Button)
        btn.label = "Release to Send" if self._ptt_active else "Push to Talk (Space)"

    @on(Select.Changed, "#provider-select")
    async def handle_provider_change(self, event: Select.Changed) -> None:
        """Handle provider selection."""
        if event.value:
            await self.gateway.send({
                "type": "set_provider",
                "provider": event.value,
            })

    async def action_push_to_talk(self) -> None:
        """Space bar handler."""
        await self.handle_ptt()

    async def action_interrupt(self) -> None:
        """Escape handler."""
        await self.gateway.send({"type": "interrupt"})

    async def action_toggle_providers(self) -> None:
        """Toggle provider selection focus."""
        select = self.query_one("#provider-select", Select)
        select.focus()

    async def action_toggle_latency(self) -> None:
        """Toggle latency panel visibility."""
        panel = self.query_one("#latency-panel", LatencyWidget)
        panel.display = not panel.display


def main():
    parser = argparse.ArgumentParser(description="Echo-Node TUI Voice Assistant")
    parser.add_argument("--url", default=os.environ.get("ECHO_GATEWAY_URL", "ws://127.0.0.1:3000/ws"),
                        help="Gateway WebSocket URL")
    parser.add_argument("--provider", default=os.environ.get("ECHO_DEFAULT_PROVIDER", ""),
                        help="Initial provider")
    args = parser.parse_args()

    if not TEXTUAL_AVAILABLE:
        print("Error: 'textual' library required. Install: pip install textual", file=sys.stderr)
        sys.exit(1)

    app = EchoTUI(gateway_url=args.url, provider=args.provider)
    app.run()


if __name__ == "__main__":
    main()
