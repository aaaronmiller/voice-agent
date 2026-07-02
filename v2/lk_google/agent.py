"""Echo-Node × Google Gemini — Full-featured voice agent.

Voice-in → voice-out via Gemini Multimodal Live API.
All tools routed through MCP to Hermes Agent (localhost:8642).
Cost tracking, conversation logging, FIFO avatar IPC, LemonSlice video.

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │  Gemini Multimodal Live API (WebSocket)             │
  │       ↕ (voice in/out + function calls)             │
  │  AgentSession                                       │
  │    ├── GeminiAgent (instructions + tools)           │
  │    ├── MCP server → Hermes Agent :8642              │
  │    ├── CostTracker → logs/cost-*.jsonl              │
  │    └── FIFO IPC → Avatar Window (PyQt6)             │
  └─────────────────────────────────────────────────────┘
         ↕ WebRTC
  lk-server (self-hosted, local)
         ↕ WebRTC  
  Client (mic/speaker via sounddevice)

Environment:
  GOOGLE_API_KEY          — Gemini API key (required)
  HERMES_URL              — Hermes Agent URL (default: http://127.0.0.1:8642)
  LEMONSLICE_API_KEY      — LemonSlice avatar key (optional)
  AVATAR_IMAGE_URL        — Public URL for avatar image (optional)
  GEMINI_VOICE            — Voice name (default: Puck)
  LIVEKIT_URL             — lk-server URL (default: ws://127.0.0.1:7880)
  COST_LOG_DIR            — Cost log directory (default: logs)
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import time

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    llm,
)
from livekit.plugins.google import realtime as google_realtime

# ── Paths & env ────────────────────────────────────────────────────

_AGENT_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_DIR.parent

for envfile in (_AGENT_DIR / ".env", _AGENT_DIR / ".env.local",
                _REPO_ROOT / ".env", _REPO_ROOT / ".env.local"):
    if envfile.exists():
        load_dotenv(envfile)


# ── Logging ────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("echo-node-google")


# ── Configuration ──────────────────────────────────────────────────

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY must be set", file=sys.stderr)
    sys.exit(1)

AGENT_NAME = os.getenv("AGENT_NAME", "echo-node-google")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash-native-audio-preview-12-2025",
)
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Puck")
HERMES_URL = os.getenv("HERMES_URL", "http://127.0.0.1:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "pass")
LEMONSLICE_API_KEY = os.environ.get("LEMONSLICE_API_KEY")
COST_LOG_DIR = os.getenv("COST_LOG_DIR", "logs")
FIFO_PATH = os.getenv("AVATAR_FIFO", "/tmp/echo-node-avatar.fifo")


# ── Instructions ───────────────────────────────────────────────────

ASSISTANT_INSTRUCTIONS = """
You are a friendly AI assistant having a voice conversation.
Speak naturally and conversationally — like a real person, not a robot.

# Personality
- Warm, helpful, and concise (1-3 sentences per turn)
- You have a sense of humor but stay professional
- If you don't know something, say so and offer to look it up

# Voice
- Use natural speech patterns with varied intonation
- No markdown, emojis, or special characters in your speech
- Sound like a real human conversation, not a text response read aloud

# Capabilities
Use the tools available to you (web search, commands, files) whenever the
user asks for information, actions, or tasks. You have full access to
Hermes Agent which can search the web, run commands, read/write files,
and analyze data.

# Safety
Steer inappropriate topics back to acceptable conversation.
""".strip()


# ── Cost Tracker (lazy import) ────────────────────────────────────

_cost_tracker: "CostTracker | None" = None


def get_cost_tracker():
    global _cost_tracker
    if _cost_tracker is None:
        from lk_google.cost_tracker import CostTracker
        session_id = f"gemini-{AGENT_NAME}-{int(time.time())}"
        _cost_tracker = CostTracker(
            model=GEMINI_MODEL,
            log_dir=COST_LOG_DIR,
            session_id=session_id,
        )
    return _cost_tracker


# ── FIFO IPC ──────────────────────────────────────────────────────

def _fifo_send(data: dict) -> None:
    """Send a JSON command to the avatar window via FIFO."""
    if not os.path.exists(FIFO_PATH):
        return
    try:
        with open(FIFO_PATH, "w") as f:
            f.write(json.dumps(data) + "\n")
    except (BrokenPipeError, OSError):
        pass  # avatar not running


def _fifo_state(state: str) -> None:
    """Update avatar with current assistant state."""
    _fifo_send({"cmd": "set_state", "state": state})
    # Also update cost tracker
    try:
        get_cost_tracker().on_state_change(state)
    except Exception:
        pass


# ── Hermes API Client ─────────────────────────────────────────────

def _hermes_query(prompt: str, tool_hint: str | None = None) -> str:
    """Send a prompt to Hermes Agent and return the response."""
    import httpx
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a tool-using agent. Answer concisely with just "
                    "the result. If you search the web or run commands, "
                    "return only the relevant output."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    try:
        resp = httpx.post(
            f"{HERMES_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {HERMES_API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return "Hermes did not respond in time. Please try again."
    except Exception as e:
        return f"Could not reach Hermes Agent: {e}"


# ── Agent ──────────────────────────────────────────────────────────

class GeminiAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=ASSISTANT_INSTRUCTIONS)

    # ── Tool: Run command via Hermes or locally ──────────────

    @function_tool
    async def run_command(self, ctx: RunContext, command: str) -> str:
        """Run a shell command or system task.
        Use for: checking system status, running scripts, file operations,
        installing packages, git commands, process management."""
        import subprocess
        _fifo_state("working")
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30,
            )
            output = result.stdout or result.stderr or "(no output)"
            return output[:4000]
        except subprocess.TimeoutExpired:
            return "Command timed out after 30s."
        except Exception as e:
            return f"Command failed: {e}"

    # ── Tool: Search web ─────────────────────────────────────

    @function_tool
    async def search_web(self, ctx: RunContext, query: str) -> str:
        """Search the web for current information.
        Use for: news, facts, research, prices, weather, recent events."""
        _fifo_state("working")
        return _hermes_query(f"Search the web for: {query}")

    # ── Tool: Read file ──────────────────────────────────────

    @function_tool
    async def read_file(self, ctx: RunContext, path: str) -> str:
        """Read a file from the local filesystem. Use for checking configs,
        logs, code files, documentation."""
        _fifo_state("working")
        try:
            with open(path) as f:
                return f.read()[:8000]
        except Exception as e:
            return f"Error reading {path}: {e}"

    # ── Tool: Write file ─────────────────────────────────────

    @function_tool
    async def write_file(self, ctx: RunContext, path: str, content: str) -> str:
        """Write or overwrite a file. Use for creating scripts, configs,
        notes, or saving data."""
        _fifo_state("working")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error writing {path}: {e}"

    # ── Tool: Get time ───────────────────────────────────────

    @function_tool
    async def get_time(self, ctx: RunContext) -> str:
        """Get the current date, time, and timezone."""
        import datetime
        now = datetime.datetime.now()
        return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")

    # ── Tool: Cost summary ───────────────────────────────────

    @function_tool
    async def show_cost(self, ctx: RunContext) -> str:
        """Show the current session's cost summary.
        Use when the user asks how much this conversation has cost."""
        try:
            return get_cost_tracker().final_summary()
        except Exception as e:
            return f"Cost tracking error: {e}"

    # ── Tool: Schedule task ──────────────────────────────────

    @function_tool
    async def schedule_task(self, ctx: RunContext, command: str, 
                            schedule: str = "now") -> str:
        """Schedule a command to run now or later via cron.
        Use for: reminders, recurring backups, periodic checks.
        Args:
            command: Shell command to run
            schedule: 'now' for immediate, or cron expression like '0 9 * * 1'
        """
        _fifo_state("working")
        import subprocess
        if schedule == "now":
            subprocess.Popen(command, shell=True)
            return f"✅ Started in background: {command}"
        else:
            cron_line = f"{schedule} cd {os.getcwd()} && {command}"
            try:
                existing = subprocess.run(
                    "crontab -l", shell=True, capture_output=True, text=True,
                ).stdout
                if cron_line not in existing:
                    new_cron = existing.strip() + "\n" + cron_line + "\n"
                    proc = subprocess.run(
                        "crontab", input=new_cron, capture_output=True,
                        text=True, shell=True,
                    )
                    if proc.returncode == 0:
                        return f"✅ Scheduled: {cron_line}"
                    return f"Error: {proc.stderr}"
                return "✅ Already scheduled"
            except Exception as e:
                return f"Error: {e}"


# ── Server ─────────────────────────────────────────────────────────

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def echo_node_session(ctx: JobContext) -> None:
    """Main session handler — runs when a room dispatch occurs."""
    room_name = ctx.room.name
    logger.info(f"Session starting in room: {room_name}")

    # ── Initialize subsystems ─────────────────────────────────

    # Cost tracker
    cost = get_cost_tracker()
    logger.info(f"Gemini model: {GEMINI_MODEL}")
    logger.info(f"Gemini voice: {GEMINI_VOICE}")
    logger.info(f"Hermes Agent: {HERMES_URL}")
    logger.info(f"Cost tracking: {COST_LOG_DIR}")

    # ── Build the Gemini RealtimeModel ───────────────────────
    #
    # This is the key component — it replaces the entire STT→LLM→TTS
    # pipeline with a single WebSocket connection to Gemini that
    # handles voice-in, understanding, and voice-out end-to-end.
    #
    # Benefits vs the v1 pipeline (Whisper + Kokoro + Hermes):
    #   - 5 pipeline stages → 1 model (10-50x fewer components)
    #   - 37-64s per turn → ~500ms-2s latency
    #   - No local GPU memory needed
    #   - Built-in turn detection, barge-in, emotional awareness

    gemini = google_realtime.RealtimeModel(
        model=GEMINI_MODEL,
        voice=GEMINI_VOICE,
        api_key=GOOGLE_API_KEY,
        enable_affective_dialog=True,
    )

    # ── MCP Server for Hermes Integration ─────────────────────
    #
    # This connects Gemini to Hermes Agent via the Model Context Protocol.
    # Hermes provides: web search, bash commands, file ops, data analysis.
    #
    # The MCP server runs as a subprocess (stdio) and exposes Hermes's
    # capabilities as function tools that Gemini can call directly.
    #
    # Alternative: We also include direct function tools above for the
    # most common operations (run_command, search_web, read/write file)
    # so the most latency-sensitive tools skip the MCP round-trip.

    mcp_servers = []
    mcp_server_path = _AGENT_DIR / "mcp_servers" / "hermes.py"
    if mcp_server_path.exists():
        mcp_servers.append(
            llm.mcp.MCPServerStdio(
                command=sys.executable,
                args=[str(mcp_server_path)],
                client_session_timeout_seconds=10,
            )
        )
        logger.info(f"MCP server: {mcp_server_path}")

    # ── State tracking via agent events ───────────────────────

    def on_state_change(state: str):
        _fifo_state(state)
        cost.on_state_change(state)
        logger.info(f"  [{state}]")

    # ── Create the AgentSession ───────────────────────────────
    #
    # This is the LiveKit voice pipeline manager. It:
    #   1. Listens to the room mic (via WebRTC)
    #   2. Feeds audio to Gemini (RealtimeModel)
    #   3. Receives Gemini voice responses
    #   4. Plays them back through room speakers
    #   5. Handles turn detection, interruptions, state management

    session = AgentSession(
        llm=gemini,
        mcp_servers=mcp_servers if mcp_servers else None,
        # Turn handling — Gemini's server-side detection is built-in
        turn_handling=TurnHandlingOptions(
            interruption={
                "resume_false_interruption": True,
                "allow_interruptions": True,
            },
        ),
    )

    # ── Wire state change events ──────────────────────────────

    @session.on("agent_state_changed")
    def _on_agent_state(event):
        on_state_change(event.state.value if hasattr(event.state, 'value') else str(event.state))

    # ── Wire user interaction events for logging ──────────────

    @session.on("user_input_transcribed")
    def _on_transcription(event):
        """Log user transcription for cost tracking."""
        logger.debug(f"[user] {event.transcript}")

    @session.on("conversation_item_added")
    def _on_item(event):
        """Log conversation items for the session log."""
        if hasattr(event.item, 'type'):
            logger.debug(f"[item] {event.item.type}")

    # ── Connect to LiveKit room ───────────────────────────────

    await ctx.connect()

    # ── Optional: LemonSlice video avatar ─────────────────────

    avatar = None
    if LEMONSLICE_API_KEY:
        from livekit.plugins import lemonslice
        AVATAR_IMAGE_URL = os.getenv(
            "AVATAR_IMAGE_URL",
            "https://6ammc3n5zzf5ljnz.public.blob.vercel-storage.com/"
            "inf2-uploads/image_9d0f6-WhaKqLKTzfVHlfe5jXzHE8Rpi9peF4.jpg",
        )
        try:
            avatar = lemonslice.AvatarSession(
                agent_image_url=AVATAR_IMAGE_URL,
                agent_prompt="A person talking naturally, reacting to conversation.",
                api_key=LEMONSLICE_API_KEY,
            )
            await avatar.start(session, room=ctx.room)
            logger.info("✅ LemonSlice avatar started")
        except Exception as e:
            logger.warning(f"LemonSlice avatar failed: {e}")
            avatar = None

    # ── Start the voice agent ─────────────────────────────────

    _fifo_state("listening")
    agent = GeminiAgent()
    
    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Wait for avatar to be ready if enabled
    if avatar:
        try:
            await avatar.wait_for_join()
            logger.info("✅ Avatar joined room")
        except Exception as e:
            logger.warning(f"Avatar join timeout: {e}")

    # ── Greeting ──────────────────────────────────────────────

    logger.info(f"✅ Agent ready in room '{room_name}' — cost tracking active")
    await session.generate_reply(
        instructions=(
            "Greet the user warmly. Tell them you're powered by Google Gemini "
            "with Hermes Agent tools. Ask how you can help."
        ),
    )


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    from livekit import agents as lk_agents
    lk_agents.cli.run_app(server)


if __name__ == "__main__":
    main()
