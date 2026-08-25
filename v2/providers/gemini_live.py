#!/usr/bin/env python3
"""
Echo-Node: Gemini Multimodal Live API — standalone CLI mode.

This is the CLI-FIRST implementation of the Gemini Live voice agent.
It proves the low-latency (~500ms) voice path works BEFORE any TUI
or Web frontend is built.

Usage:
  export GEMINI_API_KEY="your-key-here"
  python -m echo_node.providers.gemini_live

  # Or via env var overrides:
  GEMINI_MODEL=gemini-3.1-flash-live-preview GEMINI_VOICE=Puck \\
    python -m echo_node.providers.gemini_live

Exit:
  Ctrl+C to quit. Interruptions are handled by Gemini natively.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

# ── Provider interface ──

try:
    from costs import SessionCostTracker
except ImportError:
    from echo_node.providers.costs import SessionCostTracker

@dataclass
class TurnMetrics:
    turn_id: int = 0
    provider: str = "gemini-live"
    t_wake: float = 0.0
    t_user_done: float = 0.0
    t_first_token: float = 0.0
    t_response_done: float = 0.0
    t_playback_start: float = 0.0
    t_playback_done: float = 0.0
    ears_to_mouth: float = 0.0
    llm_first_token: float = 0.0
    total_latency: float = 0.0
    interrupted: bool = False
    error: str = ""

    def compute(self) -> None:
        if self.t_playback_start and self.t_user_done:
            self.ears_to_mouth = (self.t_playback_start - self.t_user_done) * 1000
        if self.t_first_token and self.t_user_done:
            self.llm_first_token = (self.t_first_token - self.t_user_done) * 1000
        if self.t_playback_done and self.t_wake:
            self.total_latency = (self.t_playback_done - self.t_wake) * 1000

    def __str__(self) -> str:
        return (
            f"turn={self.turn_id} | "
            f"ears→mouth={self.ears_to_mouth:.0f}ms | "
            f"first_token={self.llm_first_token:.0f}ms | "
            f"total={self.total_latency:.0f}ms"
            + (" | INTERRUPTED" if self.interrupted else "")
            + (f" | ERROR={self.error}" if self.error else "")
        )


# ── Gemini Live Client ──

class GeminiLiveClient:
    """Real Gemini Multimodal Live API client.

    Connects via WebSocket to Google's Gemini Live API.
    Handles bidirectional audio streaming natively.
    """

    API_BASE = "wss://generativelanguage.googleapis.com/ws/"
    API_PATH = "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-live-preview", voice: str = "Puck"):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.ws: Any = None
        self._running = False
        self._turn_id = 0
        self._current_turn = TurnMetrics()
        self._interrupted = False
        self._cost_tracker = SessionCostTracker("gemini-live")
        self._session_start: float = 0.0

    async def connect(self) -> None:
        """Connect to Gemini Live and set up the session."""
        import json
        import websockets

        url = f"{self.API_BASE}{self.API_PATH}?key={self.api_key}"
        print(f"[gemini-live] connecting to {self.model}...", flush=True)

        self.ws = await websockets.connect(url)

        # Send setup message
        setup = {
            "setup": {
                "model": f"models/{self.model}",
                "systemInstruction": {
                    "parts": [{"text": "You are a helpful voice assistant. Be concise and natural."}]
                },
                "generationConfig": {
                    "temperature": 0.7,
                    "topP": 0.95,
                    "maxOutputTokens": 8192,
                },
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": self.voice,
                    }
                },
                "audioConfig": {
                    "inputAudioFormat": "PCM16_16000",
                    "outputAudioFormat": "PCM16_24000",
                },
            }
        }
        await self.ws.send(json.dumps(setup))

        # Wait for setup confirmation
        async for msg in self.ws:
            data = json.loads(msg)
            if data.get("setupComplete"):
                print("[gemini-live] session ready", flush=True)
                break

    async def run(self) -> None:
        """Run the live voice session.

        Captures mic audio, sends to Gemini, plays back responses.
        Uses Gemini's built-in VAD and interruption handling.
        """
        import pyaudio
        import json

        if not self.ws:
            raise RuntimeError("Not connected. Call connect() first.")

        self._running = True
        self._session_start = time.perf_counter()

        # Audio config
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 3200  # 200ms at 16kHz

        p = pyaudio.PyAudio()

        # Open mic stream
        mic = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        # Open speaker stream
        speaker = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=24000,  # Gemini outputs at 24kHz
            output=True,
            frames_per_buffer=CHUNK,
        )

        print("\n  🎤 Gemini Live — speak now (Ctrl+C to quit)\n", flush=True)

        # Metrics
        metrics_log: list[TurnMetrics] = []
        turn_start = time.perf_counter()

        async def send_audio():
            """Read from mic and send to Gemini."""
            while self._running and not self._interrupted:
                data = mic.read(CHUNK, exception_on_overflow=False)
                import base64
                msg = {
                    "realtimeInput": {
                        "mediaChunks": [{
                            "data": base64.b64encode(data).decode(),
                            "mimeType": "audio/pcm;rate=16000",
                        }]
                    }
                }
                await self.ws.send(json.dumps(msg))
                await asyncio.sleep(0)  # yield

        async def receive_audio():
            """Receive from Gemini and play through speaker."""
            nonlocal turn_start
            import base64
            import json

            while self._running:
                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if isinstance(raw, bytes):
                    # Binary audio
                    speaker.write(raw)
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if "serverContent" in msg:
                    content = msg["serverContent"]

                    if content.get("turnStart"):
                        # New turn
                        self._turn_id += 1
                        self._current_turn = TurnMetrics(
                            turn_id=self._turn_id,
                            t_wake=time.perf_counter(),
                        )
                        turn_start = time.perf_counter()

                    if content.get("turnComplete"):
                        # End of turn
                        self._current_turn.t_response_done = time.perf_counter()
                        self._current_turn.t_playback_done = time.perf_counter()
                        self._current_turn.compute()
                        metrics_log.append(self._current_turn)
                        print(f"  [perf] {self._current_turn}", flush=True)

                    if "parts" in content:
                        for part in content["parts"]:
                            if "inlineData" in part:
                                audio_bytes = base64.b64decode(part["inlineData"]["data"])
                                speaker.write(audio_bytes)
                            if "text" in part:
                                print(f"\n  [{self.model}] {part['text']}", flush=True)

                elif msg.get("toolCall"):
                    # Tool calling — log for now
                    print(f"\n  [tool] {msg['toolCall']}", flush=True)

        # Run send and receive concurrently
        try:
            await asyncio.gather(send_audio(), receive_audio())
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            mic.stop_stream()
            mic.close()
            speaker.stop_stream()
            speaker.close()
            p.terminate()
            if self.ws:
                await self.ws.close()

            # Print summary
            if metrics_log:
                latencies = [m.ears_to_mouth for m in metrics_log if m.ears_to_mouth > 0]
                if latencies:
                    session_duration_s = time.perf_counter() - self._session_start
                    avg_lat = sum(latencies) / len(latencies)
                    max_lat = max(latencies)
                    min_lat = min(latencies)
                    print(f"\n  ── Session Summary ──")
                    print(f"  Duration: {session_duration_s:.0f}s")
                    print(f"  Turns: {len(metrics_log)}")
                    print(f"  Avg latency: {avg_lat:.0f}ms")
                    print(f"  Min latency: {min_lat:.0f}ms")
                    print(f"  Max latency: {max_lat:.0f}ms")
                    print(f"  Cost: {self._cost_tracker.format_cost(0.0)} (Free - preview)")

    def interrupt(self) -> None:
        """Interrupt the current response."""
        self._interrupted = True
        if self.ws:
            import json
            asyncio.create_task(self.ws.send(json.dumps({
                "serverContent": {"interruption": True}
            })))


# ── CLI entry point ──

def main():
    parser = argparse.ArgumentParser(description="Echo-Node Gemini Live CLI")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-live-preview"),
                        help="Gemini model name")
    parser.add_argument("--voice", default=os.environ.get("GEMINI_VOICE", "Puck"),
                        choices=["Puck", "Charon", "Kore", "Fenrir", "Aoede"],
                        help="Gemini voice name")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="Google API key (or set GEMINI_API_KEY)")
    parser.add_argument("--metrics", action="store_true", default=True,
                        help="Show latency metrics after each turn")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: GEMINI_API_KEY is not set.", file=sys.stderr)
        print("Usage: export GEMINI_API_KEY=your-key && python -m echo_node.providers.gemini_live", file=sys.stderr)
        sys.exit(1)

    async def _run():
        client = GeminiLiveClient(
            api_key=args.api_key,
            model=args.model,
            voice=args.voice,
        )
        await client.connect()
        await client.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n[gemini-live] stopped", flush=True)
    except Exception as e:
        print(f"\n[gemini-live] error: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
