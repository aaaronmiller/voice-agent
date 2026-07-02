#!/usr/bin/env python3
"""Quick test client for the Google Gemini voice agent.

Creates a LiveKit room, generates a token, connects, and
bridges mic/speakers via sounddevice so you can talk to Gemini.

Usage:
  python lk_google/test_client.py
  python lk_google/test_client.py --room test-room
  python lk_google/test_client.py --audio-only  (no avatar window)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from livekit import api as lk_api
from livekit import rtc as lk_rtc

# Load env
_REPO = Path(__file__).resolve().parent.parent
for envfile in (Path(__file__).parent / ".env", _REPO / ".env"):
    if envfile.exists():
        load_dotenv(envfile)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("test-client")

# ── Config ─────────────────────────────────────────────────────────

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
ROOM_NAME = os.getenv("ROOM_NAME", "echo-node-test")


async def main():
    parser = argparse.ArgumentParser(description="Test Google Gemini voice agent")
    parser.add_argument("--room", default=ROOM_NAME, help="Room name")
    parser.add_argument("--audio-only", action="store_true", help="No video window")
    parser.add_argument("--duration", type=int, default=60, help="Test duration (s)")
    args = parser.parse_args()

    logger.info("── Gemini Voice Agent Test ──")
    logger.info(f"Server:  {LIVEKIT_URL}")
    logger.info(f"Room:    {args.room}")
    logger.info(f"Audio:   {'yes' if not args.audio_only else 'no (audio only)'}")
    logger.info(f"Duration: {args.duration}s")
    logger.info("")

    # ── Generate token ──────────────────────────────────────────
    token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
        .with_identity("test-user") \
        .with_name("Test User") \
        .with_grants(lk_api.VideoGrants(
            room_join=True,
            room=args.room,
            can_publish=True,
            can_subscribe=True,
        )).to_jwt()
    logger.info("Token generated")

    # ── Connect to room ─────────────────────────────────────────
    room = lk_rtc.Room()
    @room.on("participant_connected")
    def on_participant(participant: lk_rtc.RemoteParticipant):
        logger.info(f"  Participant joined: {participant.identity} ({participant.name})")

    @room.on("track_subscribed")
    def on_track(track: lk_rtc.Track, publication: lk_rtc.TrackPublication, participant: lk_rtc.RemoteParticipant):
        logger.info(f"  Track subscribed: {track.kind} from {participant.identity}")

    @room.on("participant_disconnected")
    def on_part_disconnect(participant: lk_rtc.RemoteParticipant):
        logger.info(f"  Participant left: {participant.identity}")

    logger.info("Connecting to room...")
    await room.connect(LIVEKIT_URL, token)
    logger.info(f"  Connected! Room: {room.name}")
    logger.info(f"  Participants: {len(room.participants)}")

    # The agent should join automatically since it's registered
    logger.info("Waiting for Gemini agent to join...")
    await asyncio.sleep(5)
    logger.info(f"  Now {len(room.participants)} participants")

    # List participants
    for pid, p in room.participants.items():
        logger.info(f"  - {p.identity} ({p.name})")

    if args.audio_only:
        logger.info(f"\nTest running for {args.duration}s. Talk to Gemini!")
        logger.info("Press Ctrl+C to stop.")
        try:
            await asyncio.sleep(args.duration)
        except KeyboardInterrupt:
            pass
    else:
        # Launch the PyQt6 video client
        logger.info("\nLaunching avatar video window...")
        sys.path.insert(0, str(_REPO))
        from lk_echo.client_video import run_qt_client
        # This will block
        await run_qt_client(room)

    logger.info("Disconnecting...")
    await room.disconnect()
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
