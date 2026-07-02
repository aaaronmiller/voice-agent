"""Echo-Node LemonSlice Agent — LiveKit voice pipeline + LemonSlice avatar.

Connects to the local LiveKit server, runs a voice pipeline using direct
plugins (Deepgram STT, OpenAI/OpenRouter LLM, OpenAI TTS), and generates
a real-time video avatar via LemonSlice.

The avatar joins the room as a separate participant with identity
"lemonslice-avatar-agent" and publishes a video+audio track of the talking face.

Run:
  python -m lk_echo.agent_lemonslice dev     # development
  python -m lk_echo.agent_lemonslice start   # production

Environment:
  LEMONSLICE_API_KEY  (required)
  DEEPGRAM_API_KEY    (required)
  OPENAI_API_KEY      (required for LLM + TTS, or set LLM_BASE_URL for OpenRouter)
  LLM_BASE_URL        (optional — use OpenRouter/compatible endpoint instead of OpenAI)
  LLM_API_KEY         (optional — for custom LLM endpoint)
  LLM_MODEL           (optional — default: openai/gpt-4o-mini or anthropic/claude-3-haiku)
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
from livekit.agents.llm import FunctionContext
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

# Avatar appearance — must be a publicly reachable URL (LemonSlice servers fetch it)
AVATAR_IMAGE_URL = os.getenv(
    "AVATAR_IMAGE_URL",
    "https://6ammc3n5zzf5ljnz.public.blob.vercel-storage.com/"
    "inf2-uploads/image_9d0f6-WhaKqLKTzfVHlfe5jXzHE8Rpi9peF4.jpg",
)

# ── API keys sanity checks ─────────────────────────────────────────

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY") or OPENAI_API_KEY
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TTS_API_KEY = os.getenv("TTS_API_KEY") or OPENAI_API_KEY

if not DEEPGRAM_API_KEY:
    print("ERROR: DEEPGRAM_API_KEY must be set for STT", file=sys.stderr)
    sys.exit(1)

if not LLM_API_KEY or LLM_API_KEY == "dummy":
    print("ERROR: No valid API key for LLM/TTS", file=sys.stderr)
    print("Set OPENAI_API_KEY or LLM_API_KEY", file=sys.stderr)
    sys.exit(1)

# ── Instructions ───────────────────────────────────────────────────

ASSISTANT_INSTRUCTIONS = """
You are Jess, a friendly AI assistant with a realistic video avatar powered by LemonSlice.
You speak naturally and conversationally — like a real person, not a robot.

# Personality
- Warm, helpful, and concise (1-3 sentences per turn)
- You have a sense of humor but stay professional
- You appear as a friendly young woman with black hair

# Voice
- Short, natural sentences
- No markdown, emojis, or special characters in your speech
- Sound like a real human conversation

# Capabilities
- You can search the web and run system commands
- Offer to search if unsure

# Safety
Steer inappropriate topics back to acceptable conversation.
""".strip()


# ── Agent ──────────────────────────────────────────────────────────

class JessAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=ASSISTANT_INSTRUCTIONS)

    @function_tool
    async def search_web(self, ctx: RunContext, query: str) -> str:
        """Search the web. Use when the user asks about current events."""
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

    # ── LLM: OpenAI or OpenRouter ──
    llm_kwargs = {"model": LLM_MODEL}
    if LLM_BASE_URL:
        llm_kwargs["base_url"] = LLM_BASE_URL
    if LLM_API_KEY:
        llm_kwargs["api_key"] = LLM_API_KEY

    llm = openai.LLM(**llm_kwargs)
    logger.info(f"LLM: {LLM_MODEL}" + (f" @ {LLM_BASE_URL}" if LLM_BASE_URL else ""))

    # ── STT: Deepgram ──
    stt = deepgram.STT(model="nova-3", language="en", api_key=DEEPGRAM_API_KEY)
    logger.info("STT: Deepgram Nova-3")

    # ── TTS: OpenAI ──
    tts_kwargs = {"model": "tts-1", "voice": "alloy"}
    if LLM_BASE_URL:
        # If using custom base URL for LLM, TTS might need different endpoint
        pass
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

    # Start voice agent
    await session.start(
        room=ctx.room,
        agent=JessAgent(),
    )

    # Wait for avatar to be ready
    try:
        await avatar.wait_for_join()
        logger.info("Avatar ready — Jess is online")
    except Exception as e:
        logger.warning(f"Avatar join wait: {e}")

    # Greeting
    await session.generate_reply(
        instructions="Greet the user warmly. Introduce yourself as Jess."
    )


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
