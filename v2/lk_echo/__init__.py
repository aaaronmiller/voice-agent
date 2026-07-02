"""LiveKit-based Echo-Node voice agent.

Architecture:
  lk-server (WebRTC) ←→ Agent (voice pipeline) ←→ Client (local audio)

The LiveKit server provides WebRTC transport. The Agent uses the
livekit-agents SDK with Deepgram STT, OpenAI LLM, and OpenAI TTS.
The Client bridges local microphone/speaker to the WebRTC room.

Run:
  ./run.sh          # starts lk-server + agent + client
  ./run.sh --dev    # same with verbose logging

Requires:
  - livekit-agents[openai,deepgram] installed
  - lk-server binary in v2/vendor/
  - OPENAI_API_KEY and DEEPGRAM_API_KEY env vars
"""

from __future__ import annotations

__version__ = "0.1.0"
