#!/usr/bin/env python3
"""Quick test: join a LiveKit room, see if the Gemini agent joins.

Usage:
  python lk_google/test_connect.py        # default room
  python lk_google/test_connect.py myroom
"""

import asyncio, json, logging, os, sys
from pathlib import Path
from dotenv import load_dotenv
from livekit import api as lk_api
from livekit import rtc as lk_rtc

_REPO = Path(__file__).resolve().parent.parent
for envfile in (Path(__file__).parent / ".env", _REPO / ".env"):
    if envfile.exists():
        load_dotenv(envfile)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test")

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
LIVEKIT_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
ROOM = sys.argv[1] if len(sys.argv) > 1 else "echo-node-test"

async def main():
    print(f"── Gemini Agent Test ──")
    print(f"Server: {LIVEKIT_URL}")
    print(f"Room:   {ROOM}")
    print()

    token = lk_api.AccessToken(LIVEKIT_KEY, LIVEKIT_SECRET) \
        .with_identity("test-user") \
        .with_grants(lk_api.VideoGrants(
            room_join=True, room=ROOM,
            can_publish=True, can_subscribe=True,
        )).to_jwt()

    room = lk_rtc.Room(loop=asyncio.get_running_loop())

    @room.on("participant_connected")
    def on_join(p):
        print(f"  ✅ Participant joined: {p.identity} ({p.name or 'no name'})")

    @room.on("participant_disconnected")
    def on_leave(p):
        print(f"  ❌ Participant left: {p.identity}")

    @room.on("track_subscribed")
    def on_track(track, pub, participant):
        print(f"  🔊 Track: {track.kind} from {participant.identity}")

    print("Connecting...")
    await room.connect(LIVEKIT_URL, token)
    print(f"✅ Connected to room '{room.name}'")
    print(f"   Participants: {len(room.participants)}")

    print("\nWaiting 15s for agent to join...")
    for i in range(15):
        await asyncio.sleep(1)
        n = len(room.participants)
        if n > 0:
            print(f"   t={i+1}s: {n} participant(s)")
            for pid, p in room.participants.items():
                print(f"     - {p.identity}")
            break
        print(f"   t={i+1}s: waiting...")

    # Keep alive for a bit
    print("\n✅ Agent is talking! Listen through speakers.")
    print("Press Ctrl+C to disconnect.")
    try:
        await asyncio.sleep(30)
    except KeyboardInterrupt:
        pass

    print("\nDisconnecting...")
    await room.disconnect()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
