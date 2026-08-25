#!/usr/bin/env python3
"""
Echo-Node: OpenAI Realtime API — standalone CLI mode.

CLI-first implementation of the OpenAI Realtime voice agent.
Proves the low-latency (~450ms) voice path works.

Usage:
  export OPENAI_API_KEY="your-key-here"
  python -m echo_node.providers.openai_realtime

  # Options:
  python -m echo_node.providers.openai_realtime --voice alloy --model gpt-4o-realtime-preview
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import numpy as np

try:
    from costs import SessionCostTracker
except ImportError:
    from echo_node.providers.costs import SessionCostTracker


@dataclass
class TurnMetrics:
    turn_id: int = 0
    provider: str = "openai-realtime"
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


class OpenAIRealtimeClient:
    """Real OpenAI Realtime API client.

    WebSocket-based bidirectional audio with built-in server VAD.
    """

    WS_URL = "wss://api.openai.com/v1/realtime"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-realtime-preview-2024-12-17",
        voice: str = "alloy",
        instructions: str = "You are a helpful voice assistant. Be concise.",
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.ws: Any = None
        self._running = False
        self._turn_id = 0
        self._current_turn = TurnMetrics()
        self._response_start = 0.0
        self._metrics_log: list[TurnMetrics] = []
        self._session_start: float = 0.0
        self._cost_tracker = SessionCostTracker("openai-realtime")

    async def connect(self) -> None:
        """Connect and configure the session."""
        import websockets

        print(f"[openai-realtime] connecting {self.model}...", flush=True)

        extra_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        self.ws = await websockets.connect(self.WS_URL, extra_headers=extra_headers)

        # Configure session
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": self.instructions,
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "silence_duration_ms": 500,
                    "prefix_padding_ms": 300,
                },
                "input_audio_transcription": {
                    "enabled": True,
                    "model": "whisper-1",
                },
            },
        }
        await self.ws.send(json.dumps(config))
        print("[openai-realtime] session configured", flush=True)

    async def run(self) -> None:
        """Run the live voice session."""
        import pyaudio

        if not self.ws:
            raise RuntimeError("Not connected. Call connect() first.")

        self._running = True
        self._session_start = time.perf_counter()

        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 24000
        CHUNK = 4800  # 200ms at 24kHz

        p = pyaudio.PyAudio()

        mic = p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK,
        )
        speaker = p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            output=True, frames_per_buffer=CHUNK,
        )

        print("\n  🎤 OpenAI Realtime — speak now (Ctrl+C to quit)\n", flush=True)

        async def send_audio():
            """Send mic audio to OpenAI."""
            while self._running:
                data = mic.read(CHUNK, exception_on_overflow=False)
                await self.ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(data).decode(),
                }))
                await asyncio.sleep(0)

        async def receive_messages():
            """Receive events from OpenAI and handle them."""
            while self._running:
                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                await self._handle_event(event, speaker)

        try:
            await asyncio.gather(send_audio(), receive_messages())
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            mic.stop_stream(); mic.close()
            speaker.stop_stream(); speaker.close()
            p.terminate()
            if self.ws:
                await self.ws.close()

        # Session summary
        if self._metrics_log:
            latencies = [m.ears_to_mouth for m in self._metrics_log if m.ears_to_mouth > 0]
            if latencies:
                session_duration_s = time.perf_counter() - self._session_start
                est_cost = self._cost_tracker.estimate_turn(
                    audio_input_ms=int(session_duration_s * 1000),
                    audio_output_ms=int(session_duration_s * 500),
                )
                print(f"\n  ── Session Summary ──")
                print(f"  Duration: {session_duration_s:.0f}s")
                print(f"  Turns: {len(self._metrics_log)}")
                print(f"  Avg latency: {sum(latencies)/len(latencies):.0f}ms")
                print(f"  Min latency: {min(latencies):.0f}ms")
                print(f"  Max latency: {max(latencies):.0f}ms")
                print(f"  {self._cost_tracker.summary()}")

    async def _handle_event(self, event: dict, speaker: Any) -> None:
        event_type = event.get("type", "")

        if event_type == "session.created":
            print("[openai-realtime] session ready", flush=True)

        elif event_type == "input_audio_buffer.speech_started":
            self._turn_id += 1
            self._current_turn = TurnMetrics(turn_id=self._turn_id, t_wake=time.perf_counter())
            print(f"\n  [turn {self._turn_id}] listening...", flush=True)

        elif event_type == "input_audio_buffer.speech_stopped":
            self._current_turn.t_user_done = time.perf_counter()

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "")
            if transcript.strip():
                print(f"  [you] {transcript}", flush=True)

        elif event_type == "response.audio.delta":
            if self._current_turn.t_first_token == 0:
                self._current_turn.t_first_token = time.perf_counter()
            audio_data = base64.b64decode(event["delta"])
            speaker.write(audio_data)

        elif event_type == "response.audio.done":
            self._current_turn.t_response_done = time.perf_counter()

        elif event_type == "response.text.delta":
            # Print for transcript visibility
            text = event.get("delta", "")
            if text:
                print(text, end="", flush=True)

        elif event_type == "response.done":
            self._current_turn.t_playback_done = time.perf_counter()
            self._current_turn.compute()
            self._metrics_log.append(self._current_turn)
            print(f"\n  [perf] {self._current_turn}", flush=True)

        elif event_type == "error":
            err = event.get("error", {}).get("message", "unknown")
            print(f"\n  [error] {err}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Echo-Node OpenAI Realtime CLI")
    parser.add_argument("--model", default=os.environ.get("OPENAI_REALTIME_MODEL",
                        "gpt-4o-realtime-preview-2024-12-17"))
    parser.add_argument("--voice", default=os.environ.get("OPENAI_VOICE", "alloy"),
                        choices=["alloy", "echo", "shimmer", "verse", "ballad"])
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    async def _run():
        client = OpenAIRealtimeClient(api_key=args.api_key, model=args.model, voice=args.voice)
        await client.connect()
        await client.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n[openai-realtime] stopped", flush=True)
    except Exception as e:
        print(f"\n[openai-realtime] error: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
