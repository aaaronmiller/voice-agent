"""Echo-Node Google Gemini Voice Agent — uses Gemini Multimodal Live API.

No separate STT/LLM/TTS needed — Gemini handles voice-in → voice-out natively
via the Multimodal Live API (WebSocket-based, real-time).

Architecture:
  lk-server (self-hosted, local) → WebRTC
  Agent (google.realtime.RealtimeModel) → Gemini API (GOOGLE_API_KEY)
  Client (PyQt6 + sounddevice) → desktop video/audio bridge

Quotas (Google free tier):
  - Gemini API: 60 requests/minute (free, no credit card)
  - No per-character STT/TTS costs — Gemini does everything
  - Only need for avatar video: LemonSlice (separate service)

Run:
  python -m lk_google.agent dev     # development
  python -m lk_google.agent start   # production

Environment:
  GOOGLE_API_KEY         (required — for Gemini API, already set!)
  LEMONSLICE_API_KEY     (optional — for avatar video)
  LIVEKIT_URL            (optional — default: ws://127.0.0.1:7880)
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
    JobContext,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    room_io,
)
from livekit.plugins.google import realtime as google_realtime

# ── Paths & env ────────────────────────────────────────────────────

_AGENT_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_DIR.parent

for envfile in (_AGENT_DIR / ".env", _AGENT_DIR / ".env.local",
                _REPO_ROOT / ".env", _REPO_ROOT / ".env.local"):
    if envfile.exists():
        load_dotenv(envfile)

logger = logging.getLogger("echo-node-google")

# ── Configuration ──────────────────────────────────────────────────

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY must be set", file=sys.stderr)
    print("You already have one: export GOOGLE_API_KEY=...", file=sys.stderr)
    sys.exit(1)

AGENT_NAME = os.getenv("AGENT_NAME", "echo-node-google")

# Optional LemonSlice for avatar video
LEMONSLICE_API_KEY = os.environ.get("LEMONSLICE_API_KEY")

# ── Available Gemini models for the Live API ──────────────────────
# From livekit-plugins-google:
#   Gemini API: gemini-2.5-flash-native-audio-preview-12-2025
#               gemini-3.1-flash-live-preview (latest)
#   Vertex AI:  gemini-live-2.5-flash-native-audio
#
# The Gemini API models use GOOGLE_API_KEY, Vertex AI needs GCP project.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Puck")

ASSISTANT_INSTRUCTIONS = """
You are a friendly AI assistant having a voice conversation.
Speak naturally and conversationally — like a real person, not a robot.

# Personality
- Warm, helpful, and concise (1-3 sentences per turn)
- You have a sense of humor but stay professional

# Voice
- Use natural speech patterns with varied intonation
- No markdown, emojis, or special characters in your speech
- Sound like a real human conversation, not a text response read aloud

# Capabilities
- You can search the web and run system commands
- If the user asks about something you don't know, offer to search

# Safety
Steer inappropriate topics back to acceptable conversation.
""".strip()


# ── Agent ──────────────────────────────────────────────────────────

class GeminiAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=ASSISTANT_INSTRUCTIONS)

    @function_tool
    async def search_web(self, ctx: RunContext, query: str) -> str:
        """Search the web for current information. Use when the user asks
        about news, facts, or anything that needs up-to-date information."""
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

    @function_tool
    async def run_command(self, ctx: RunContext, command: str) -> str:
        """Run a shell command and return output.
        Use for system tasks, file operations, or running scripts."""
        import subprocess
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=15,
            )
            return (result.stdout or result.stderr or "(no output)")[:2000]
        except subprocess.TimeoutExpired:
            return "Command timed out after 15s."
        except Exception as e:
            return f"Command failed: {e}"


# ── Server ─────────────────────────────────────────────────────────

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def echo_node_session(ctx: JobContext) -> None:
    logger.info(f"Session starting in room: {ctx.room.name}")

    # ── Gemini Multimodal Live API ──────────────────────────────
    # This single model handles speech recognition, language understanding,
    # and speech synthesis — no pipeline of separate STT/LLM/TTS services.
    #
    # Benefits:
    #   - Lower latency (single model, no pipeline stages)
    #   - No per-provider API keys (uses GOOGLE_API_KEY)
    #   - Generous free tier (60 req/min)
    #   - Built-in turn detection, barge-in, emotional awareness
    
    logger.info(f"Gemini model: {GEMINI_MODEL}")
    logger.info(f"Gemini voice: {GEMINI_VOICE}")

    gemini = google_realtime.RealtimeModel(
        model=GEMINI_MODEL,
        voice=GEMINI_VOICE,
        api_key=GOOGLE_API_KEY,  # Uses your existing GOOGLE_API_KEY
        enable_affective_dialog=True,  # Emotional awareness
        # modalities defaults to ["AUDIO"] — voice in/out
    )

    # Create the session — NO separate stt/tts needed!
    # Gemini handles everything end-to-end.
    session = AgentSession(
        llm=gemini,
        # No stt parameter — Gemini processes audio natively
        # No tts parameter — Gemini generates audio natively
        turn_handling=TurnHandlingOptions(
            interruption={"resume_false_interruption": True},
        ),
    )

    # Connect to the room
    await ctx.connect()

    # Optional: LemonSlice avatar
    avatar = None
    if LEMONSLICE_API_KEY:
        from livekit.plugins import lemonslice
        AVATAR_IMAGE_URL = os.getenv(
            "AVATAR_IMAGE_URL",
            "https://6ammc3n5zzf5ljnz.public.blob.vercel-storage.com/"
            "inf2-uploads/image_9d0f6-WhaKqLKTzfVHlfe5jXzHE8Rpi9peF4.jpg",
        )
        avatar = lemonslice.AvatarSession(
            agent_image_url=AVATAR_IMAGE_URL,
            agent_prompt="A person talking naturally.",
            api_key=LEMONSLICE_API_KEY,
        )
        await avatar.start(session, room=ctx.room)
        logger.info("LemonSlice avatar started")

    # Start the voice agent
    await session.start(
        room=ctx.room,
        agent=GeminiAgent(),
    )

    if avatar:
        try:
            await avatar.wait_for_join()
            logger.info("Avatar ready")
        except Exception as e:
            logger.warning(f"Avatar join: {e}")

    # Gemini generates the greeting as part of its voice output
    await session.generate_reply(
        instructions="Greet the user warmly. Ask how you can help."
    )


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
