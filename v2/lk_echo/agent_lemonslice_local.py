"""Echo-Node LemonSlice Agent (local plugins) — no LiveKit Cloud required.

Uses direct livekit-plugins (openai, deepgram, etc.) with their own API keys
instead of going through LiveKit Cloud inference. Runs with local lk-server.

This is the "bring your own API keys" version — you need:
  - DEEPGRAM_API_KEY (STT)
  - OPENAI_API_KEY or TTS_API_KEY (TTS)
  - An LLM API key (OpenAI, OpenRouter, Groq, etc.)

vs the cloud version which needs only LIVEKIT_API_KEY + LIVEKIT_API_SECRET.

Run:
  python -m lk_echo.agent_lemonslice_local dev

Environment:
  LEMONSLICE_API_KEY  (required)
  DEEPGRAM_API_KEY    (required)
  OPENAI_API_KEY      (required for LLM or TTS, or set TTS_API_KEY + LLM_BASE_URL)
  LLM_BASE_URL        (optional — OpenRouter/Groq/compatible endpoint)
  LLM_API_KEY         (optional — separate from TTS key)
  TTS_API_KEY         (optional — separate from LLM key)
  LIVEKIT_URL         (optional — default: ws://127.0.0.1:7880)
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    room_io,
)
from livekit.plugins import deepgram, lemonslice, openai

# ── Paths & env ────────────────────────────────────────────────────

_AGENT_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_DIR.parent

for envfile in (_AGENT_DIR / ".env", _AGENT_DIR / ".env.local",
                _REPO_ROOT / ".env", _REPO_ROOT / ".env.local"):
    if envfile.exists():
        load_dotenv(envfile)

logger = logging.getLogger("echo-node-lemonslice")

# ─── Configuration ──────────────────────────────────────────────────

LEMONSLICE_API_KEY = os.getenv("LEMONSLICE_API_KEY")
if not LEMONSLICE_API_KEY:
    print("ERROR: LEMONSLICE_API_KEY must be set", file=sys.stderr)
    print("Get one at https://lemonslice.com", file=sys.stderr)
    sys.exit(1)

AGENT_NAME = os.getenv("AGENT_NAME", "lemonslice-echo-node")

# ── API keys ────────────────────────────────────────────────────────

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    print("ERROR: DEEPGRAM_API_KEY must be set for STT", file=sys.stderr)
    sys.exit(1)

# LLM: can use OpenAI, OpenRouter, Groq, etc.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY") or OPENAI_API_KEY
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# TTS: needs OpenAI-compatible key (tts-1 endpoint)
TTS_API_KEY = os.getenv("TTS_API_KEY") or OPENAI_API_KEY

if not LLM_API_KEY or LLM_API_KEY == "dummy":
    print("ERROR: No valid API key for LLM", file=sys.stderr)
    print("Set OPENAI_API_KEY or LLM_API_KEY + LLM_BASE_URL", file=sys.stderr)
    sys.exit(1)

if not TTS_API_KEY or TTS_API_KEY == "dummy":
    print("ERROR: No valid API key for TTS", file=sys.stderr)
    print("OpenAI TTS (tts-1) needs a real OPENAI_API_KEY", file=sys.stderr)
    print("Or set TTS_API_KEY separately", file=sys.stderr)
    sys.exit(1)

# ── Avatar appearance ──────────────────────────────────────────────

AVATAR_IMAGE_URL = os.getenv(
    "AVATAR_IMAGE_URL",
    "https://6ammc3n5zzf5ljnz.public.blob.vercel-storage.com/"
    "inf2-uploads/image_9d0f6-WhaKqLKTzfVHlfe5jXzHE8Rpi9peF4.jpg",
)

# ── Instructions ───────────────────────────────────────────────────

ASSISTANT_INSTRUCTIONS = """
You are Jess, a friendly AI assistant with a realistic video avatar.
Speak naturally and conversationally — like a real person, not a robot.

# Personality
- Warm, helpful, concise (1-3 sentences per turn)
- A sense of humor but professional
- You appear as a friendly young woman with black hair

# Voice
- Short, natural sentences, no markdown or emojis

# Capabilities
- You can search the web and run system commands
- Offer to search if unsure

# Safety
Steer inappropriate topics back to acceptable conversation.
""".strip()


# ── Agent with tools ───────────────────────────────────────────────

class JessAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=ASSISTANT_INSTRUCTIONS)

    @function_tool
    async def search_web(self, ctx: RunContext, query: str) -> str:
        """Search the web. Use when the user asks about current events/news."""
        import subprocess
        try:
            result = subprocess.run(
                ["firecrawl", "search", query],
                capture_output=True, text=True, timeout=30,
            )
            return (result.stdout or result.stderr or "No results")[:2000]
        except Exception as e:
            return f"Search failed: {e}"

    @function_tool
    async def get_time(self, ctx: RunContext) -> str:
        """Get the current date and time."""
        import time
        return time.strftime("%A, %B %d, %Y at %I:%M %p")


# ── Server ─────────────────────────────────────────────────────────

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def echo_node_session(ctx: JobContext) -> None:
    logger.info(f"Session starting in room: {ctx.room.name}")

    # ── LLM ──
    llm_kwargs = {"model": LLM_MODEL}
    if LLM_BASE_URL:
        llm_kwargs["base_url"] = LLM_BASE_URL
    if LLM_API_KEY:
        llm_kwargs["api_key"] = LLM_API_KEY
    llm = openai.LLM(**llm_kwargs)
    logger.info(f"LLM: {LLM_MODEL}" + (f" @ {LLM_BASE_URL}" if LLM_BASE_URL else ""))

    # ── STT ──
    stt = deepgram.STT(model="nova-3", language="en", api_key=DEEPGRAM_API_KEY)
    logger.info("STT: Deepgram Nova-3")

    # ── TTS ──
    tts_kwargs = {"model": "tts-1", "voice": "alloy"}
    if TTS_API_KEY:
        tts_kwargs["api_key"] = TTS_API_KEY
    tts = openai.TTS(**tts_kwargs)
    logger.info(f"TTS: OpenAI tts-1 (voice: alloy)")

    # ── Session ──
    session = AgentSession(
        llm=llm,
        stt=stt,
        tts=tts,
        turn_handling=TurnHandlingOptions(
            interruption={"resume_false_interruption": True},
            preemptive_generation={"enabled": True, "max_retries": 3},
        ),
        min_endpointing_delay=0.5,
        max_endpointing_delay=2.0,
    )

    # Connect to room
    await ctx.connect()

    # LemonSlice avatar
    avatar = lemonslice.AvatarSession(
        agent_image_url=AVATAR_IMAGE_URL,
        agent_prompt="A person talking naturally with varied facial expressions.",
        api_key=LEMONSLICE_API_KEY,
    )

    session_id = await avatar.start(session, room=ctx.room)
    logger.info(f"LemonSlice session started: {session_id}")

    await session.start(
        room=ctx.room,
        agent=JessAgent(),
    )

    try:
        await avatar.wait_for_join()
        logger.info("Avatar ready — Jess is online")
    except Exception as e:
        logger.warning(f"Avatar join wait: {e}")

    await session.generate_reply(
        instructions="Greet the user warmly. Introduce yourself as Jess."
    )


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
