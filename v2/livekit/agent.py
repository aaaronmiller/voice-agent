"""Echo-Node LiveKit Agent — voice pipeline using livekit-agents SDK.

This process runs the AgentSession with Deepgram STT, OpenAI LLM, and
OpenAI TTS. It connects to the local LiveKit server, waits for a room
to become available (the client joins it), then starts the voice loop.

Designed to be drop-in replaceable with the existing assistant_v2.py.
The avatar system talks to this process via a socket (for viseme data
from TTS) and to the client via the FIFO (for state/debug updates).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    MetricsCollectedEvent,
    RunContext,
    TurnHandlingOptions,
    cli,
    inference,
    metrics,
    room_io,
    text_transforms,
)
from livekit.agents.llm import function_tool

logger = logging.getLogger("echo-node-agent")

ROOT = Path(__file__).resolve().parent.parent

# ── Avatar IPC (via stdout to controller, same as v2/avatar/controller.py) ──

class AvatarBridge:
    """Sends viseme/lip-sync data to the avatar via stdout."""
    
    def __init__(self):
        self._enabled = True
        
    def send(self, payload: dict) -> None:
        if self._enabled:
            print(json.dumps(payload), flush=True)
    
    def play_cues(self, cues: list[dict], duration: float) -> None:
        self.send({"cmd": "play", "cues": cues, "duration": duration})
    
    def stop(self) -> None:
        self.send({"cmd": "stop"})
    
    def set_state(self, state: str) -> None:
        self.send({"cmd": "debug_update", "state": state})


avatar_bridge = AvatarBridge()


# ── The Agent ─────────────────────────────────────────────────────────

class EchoNodeAgent(Agent):
    """The Echo-Node voice agent with tool access."""

    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a helpful voice assistant running on a local machine. "
                "Keep responses concise and natural for spoken conversation. "
                "Do not use markdown, emojis, or special characters. "
                "Speak in complete sentences."
            ),
            # Allow the agent to use any tools defined in this class
        )

    async def on_enter(self) -> None:
        avatar_bridge.set_state("idle")
        logger.info("Agent entered session")

    @function_tool
    async def search_web(self, context: RunContext, query: str) -> str:
        """Search the web for current information.
        
        Args:
            query: The search query string
        """
        logger.info(f"[tool] search_web: {query}")
        try:
            import subprocess
            result = subprocess.run(
                ["firecrawl", "search", query],
                capture_output=True, text=True, timeout=30
            )
            return result.stdout[:2000] or result.stderr[:2000] or "No results found."
        except Exception as exc:
            return f"Search failed: {exc}"

    @function_tool
    async def get_time(self, context: RunContext) -> str:
        """Get the current date and time."""
        return time.strftime("%A, %B %d, %Y at %I:%M %p")

    @function_tool
    async def run_command(self, context: RunContext, command: str) -> str:
        """Run a shell command and return its output.
        
        Args:
            command: The shell command to execute
        """
        logger.info(f"[tool] run_command: {command}")
        try:
            import subprocess
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=15
            )
            output = (result.stdout or result.stderr or "(no output)")[:2000]
            return output
        except subprocess.TimeoutExpired:
            return f"Command timed out after 15s."
        except Exception as exc:
            return f"Command failed: {exc}"


# ── Server ────────────────────────────────────────────────────────────

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info(f"Session started in room: {ctx.room.name}")

    session: AgentSession = AgentSession(
        stt=inference.STT("deepgram/nova-3", language="multi"),
        llm=inference.LLM("openai/gpt-4o-mini"),
        tts=inference.TTS("openai/tts-1", voice="alloy"),
        turn_handling=TurnHandlingOptions(
            interruption={
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.0,
            },
            preemptive_generation={"enabled": True, "max_retries": 3},
        ),
        aec_warmup_duration=2.0,
        tts_text_transforms=[
            "filter_emoji",
            "filter_markdown",
        ],
        min_endpointing_delay=0.5,
        max_endpointing_delay=2.0,
    )

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        if ev.metrics.type == "stt_metrics":
            return
        metrics.log_metrics(ev.metrics)

    @session.on("user_started_speaking")
    def _on_user_speaking() -> None:
        avatar_bridge.set_state("listening")

    @session.on("agent_started_speaking")
    def _on_agent_speaking() -> None:
        avatar_bridge.set_state("responding")

    async def log_usage():
        logger.info(f"Session usage: {session.usage}")

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=EchoNodeAgent(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
        ),
    )


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
