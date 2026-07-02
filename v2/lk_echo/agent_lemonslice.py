"""Echo-Node LemonSlice Agent — LiveKit voice pipeline + LemonSlice avatar.

Uses LiveKit Cloud inference (inference.LLM/STT/TTS) which routes through
LiveKit's Agent Gateway — so you only need LIVEKIT_API_KEY + LIVEKIT_API_SECRET
for all STT/LLM/TTS, no separate OpenAI/Deepgram/ElevenLabs keys required.

The avatar joins the room as a separate participant with identity
"lemonslice-avatar-agent" and publishes a video+audio track of the talking face.

Run:
  python -m lk_echo.agent_lemonslice dev     # development
  python -m lk_echo.agent_lemonslice start   # production

Environment:
  LEMONSLICE_API_KEY     (required — avatar rendering)
  LIVEKIT_API_KEY        (required — LiveKit Cloud for inference + WebRTC)
  LIVEKIT_API_SECRET     (required — LiveKit Cloud)
  LIVEKIT_URL            (required — LiveKit Cloud WebRTC endpoint, e.g. wss://my-project.livekit.cloud)
  AGENT_NAME             (optional — default: lemonslice-echo-node)

For local dev without LiveKit Cloud, see agent_lemonslice_local.py instead.
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    TurnHandlingOptions,
    inference,
    room_io,
)
from livekit.plugins import lemonslice

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

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
if not LIVEKIT_API_KEY:
    print("ERROR: LIVEKIT_API_KEY must be set", file=sys.stderr)
    print("Get LiveKit Cloud credentials at https://livekit.io", file=sys.stderr)
    sys.exit(1)

LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
if not LIVEKIT_API_SECRET:
    print("ERROR: LIVEKIT_API_SECRET must be set", file=sys.stderr)
    sys.exit(1)

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
if not LIVEKIT_URL:
    print("ERROR: LIVEKIT_URL must be set", file=sys.stderr)
    print("e.g. wss://my-project.livekit.cloud", file=sys.stderr)
    sys.exit(1)

AGENT_NAME = os.getenv("AGENT_NAME", "lemonslice-echo-node")

# Avatar appearance — must be a publicly reachable URL (LemonSlice servers fetch it)
AVATAR_IMAGE_URL = os.getenv(
    "AVATAR_IMAGE_URL",
    "https://6ammc3n5zzf5ljnz.public.blob.vercel-storage.com/"
    "inf2-uploads/image_9d0f6-WhaKqLKTzfVHlfe5jXzHE8Rpi9peF4.jpg",
)

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


# ── Server ─────────────────────────────────────────────────────────

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def echo_node_session(ctx: agents.JobContext) -> None:
    logger.info(f"Session starting in room: {ctx.room.name}")

    # ── Session with LiveKit Cloud inference ────────────────────
    # These inference.* wrappers go through LiveKit's Agent Gateway
    # (agent-gateway.livekit.cloud). LiveKit handles all provider
    # API keys server-side — you just need LIVEKIT_API_KEY/SECRET.
    #
    # Models available: https://docs.livekit.io/agents/models/

    session = AgentSession(
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        stt=inference.STT(model="deepgram/nova-3", language="en"),
        tts=inference.TTS(
            model="openai/tts-1",
            voice="alloy",
            language="en",
        ),
        turn_handling=TurnHandlingOptions(
            interruption={"resume_false_interruption": True},
            preemptive_generation={"enabled": True, "max_retries": 3},
        ),
        min_endpointing_delay=0.5,
        max_endpointing_delay=2.0,
    )

    logger.info("LLM: OpenAI gpt-4o-mini (via LiveKit Cloud)")
    logger.info("STT: Deepgram Nova-3 (via LiveKit Cloud)")
    logger.info("TTS: OpenAI tts-1, voice: alloy (via LiveKit Cloud)")

    # Connect to the LiveKit room
    await ctx.connect()

    # Create the LemonSlice avatar session
    avatar = lemonslice.AvatarSession(
        agent_image_url=AVATAR_IMAGE_URL,
        agent_prompt="A person talking naturally with varied facial expressions.",
        api_key=LEMONSLICE_API_KEY,
    )

    # Start the avatar — tells LemonSlice to join the room as a
    # separate participant publishing a video track of the talking face.
    session_id = await avatar.start(session, room=ctx.room)
    logger.info(f"LemonSlice session started: {session_id}")

    # Start the voice agent
    await session.start(
        room=ctx.room,
        agent=JessAgent(),
    )

    # Wait for the avatar to join the room
    try:
        await avatar.wait_for_join()
        logger.info("Avatar ready — Jess is online")
    except Exception as e:
        logger.warning(f"Avatar join wait: {e}")

    # Generate initial greeting
    await session.generate_reply(
        instructions="Greet the user warmly. Introduce yourself as Jess."
    )


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
