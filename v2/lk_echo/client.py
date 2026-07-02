"""Echo-Node LiveKit Client — bridges local microphone/speaker to WebRTC.

This process:
  1. Connects to the local LiveKit server
  2. Captures microphone audio via sounddevice → publishes as audio track
  3. Subscribes to the agent's audio output → plays via sounddevice
  4. Handles wake word detection (hey rhasspy)
  5. Handles hotkeys (Enter to toggle, Escape to exit)
  6. Communicates with the avatar window via the FIFO
  7. Sends debug/state data to the avatar overlay

Designed to pair with agent.py (the LiveKit Agents voice pipeline).
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import sounddevice as sd
from livekit import rtc

# ── Paths ────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
AVATAR_FIFO = "/tmp/echo-node-avatar.fifo"
VENDOR_RHUBARB = ROOT / "vendor" / "rhubarb" / "rhubarb"

# ── Audio config ─────────────────────────────────────────────────────

SAMPLE_RATE = 24000  # LiveKit standard
CHANNELS = 1
DTYPE = np.int16
CHUNK_MS = 20
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)  # 480 samples @ 24kHz

# ── Wake word model (openwakeword) ───────────────────────────────────

try:
    from openwakeword import Model as WakeModel
    HAS_WAKE = True
except ImportError:
    HAS_WAKE = False


# ── Silero VAD ───────────────────────────────────────────────────────

class SileroVad:
    """Minimal Silero VAD wrapper using openwakeword's bundled ONNX model."""

    def __init__(self, threshold: float = 0.40):
        self.threshold = threshold
        self._model = None
        try:
            from silero_vad import load_silero_vad
            self._model = load_silero_vad()
        except ImportError:
            pass

    def is_speech(self, audio: np.ndarray) -> bool:
        if self._model is None:
            return True  # no VAD = always active
        try:
            import torch
            audio_t = torch.from_numpy(audio.astype(np.float32) / 32768.0)
            prob = self._model(audio_t, 16000).item()
            return prob >= self.threshold
        except Exception:
            return True


# ── Audio bridge client ──────────────────────────────────────────────

@dataclass
class LiveKitClient:
    """Connects local audio to a LiveKit room."""

    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_token: str = ""
    room_name: str = "echo-node"
    input_device: int | None = None
    output_device: int | None = None
    sample_rate: int = SAMPLE_RATE
    wake_enabled: bool = False
    wake_model_paths: list[str] = field(default_factory=list)

    # Internal state
    _room: rtc.Room | None = None
    _audio_source: rtc.AudioSource | None = None
    _mic_track: rtc.LocalAudioTrack | None = None
    _running: bool = False
    _agent_track: rtc.RemoteAudioTrack | None = None
    _audio_queue: queue.Queue = field(default_factory=queue.Queue)
    _wake_model: Any = None
    _vad: SileroVad = field(default_factory=SileroVad)

    # Callbacks
    on_state_change: Callable[[str], None] | None = None
    on_user_text: Callable[[str], None] | None = None

    def __post_init__(self):
        if self.wake_enabled and HAS_WAKE:
            try:
                self._wake_model = WakeModel(
                    wakeword_models=self.wake_model_paths
                    if self.wake_model_paths else None
                )
                print(f"[wake] openwakeword loaded", flush=True)
            except Exception as exc:
                print(f"[wake] failed: {exc}", flush=True)

    # ── FIFO communication with avatar ──

    def _fifo_send(self, payload: dict) -> None:
        try:
            with open(AVATAR_FIFO, "w") as f:
                f.write(json.dumps(payload) + "\n")
        except (OSError, IOError):
            pass

    def set_state(self, state: str) -> None:
        self._fifo_send({"cmd": "debug_update", "state": state})
        if self.on_state_change:
            self.on_state_change(state)

    # ── Room event handlers ──

    def _on_track_subscribed(self, track: rtc.Track, *_args: Any) -> None:
        """Called when the agent publishes an audio track to the room."""
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"[client] subscribed to agent audio: {track.sid}", flush=True)
            self._agent_track = track
            track.add_listener(self._on_audio_frame)

    def _on_audio_frame(self, frame: rtc.AudioFrame) -> None:
        """Queue agent audio frames for playback."""
        self._audio_queue.put(frame)

    def _on_connection_state(self, state: rtc.ConnectionState) -> None:
        print(f"[client] connection: {state}", flush=True)

    # ── Audio capture (mic → room) ──

    def _mic_callback(self, indata: np.ndarray, frames: int,
                      _time_info: Any, _status: Any) -> None:
        """sounddevice callback: push mic audio to LiveKit room."""
        if self._audio_source is None:
            return

        # Wake word detection
        if self._wake_model is not None:
            audio_float = indata.flatten().astype(np.float32) / 32768.0
            prediction = self._wake_model.predict(audio_float)
            for ww_name, score in prediction.items():
                if score > 0.5:
                    print(f"[wake] {ww_name}: {score:.3f}", flush=True)
                    self.set_state("listening")
                    # In a full implementation, this would trigger the agent

        # Create LiveKit AudioFrame and push to source
        frame = rtc.AudioFrame(
            data=indata.tobytes(),
            sample_rate=self.sample_rate,
            num_channels=1,
            samples_per_channel=frames,
        )
        self._audio_source.capture_frame(frame)

    # ── Audio playback (room → speaker) ──

    def _playback_thread(self) -> None:
        """Consume audio frames from the agent and play via sounddevice."""
        stream = sd.OutputStream(
            samplerate=self.sample_rate,
            device=self.output_device,
            channels=CHANNELS,
            dtype=np.int16,
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while self._running:
                try:
                    frame = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Convert AudioFrame bytes to numpy
                data = np.frombuffer(frame.data, dtype=np.int16)
                stream.write(data)

                # Send debug data
                rms = int(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                self._fifo_send({
                    "cmd": "debug_update",
                    "rms": rms,
                    "state": "responding",
                })
        finally:
            stream.stop()

    # ── Main loop ──

    def run(self) -> None:
        """Connect to LiveKit and start the audio bridge."""
        self._running = True

        # Validate env
        livekit_url = self.livekit_url or os.environ.get(
            "LIVEKIT_URL", "ws://127.0.0.1:7880"
        )
        token = self.livekit_token or os.environ.get("LIVEKIT_TOKEN", "")

        if not token:
            # Generate a token for anonymous access
            token = self._generate_token()

        # Create room and connect
        self._room = rtc.Room()
        self._room.on("track_subscribed", self._on_track_subscribed)
        self._room.on("connection_state", self._on_connection_state)

        print(f"[client] connecting to {livekit_url}", flush=True)
        self._room.connect(livekit_url, token)
        print(f"[client] connected to room: {self._room.name}", flush=True)

        # Create audio source (24000 Hz, mono)
        self._audio_source = rtc.AudioSource(self.sample_rate, 1)

        # Create and publish mic track
        self._mic_track = rtc.LocalAudioTrack.create_audio_track(
            "mic", self._audio_source
        )
        self._room.local_participant.publish_track(
            self._mic_track, rtc.TrackPublishOptions()
        )
        print(f"[client] mic track published", flush=True)

        # Start mic capture
        mic_stream = sd.InputStream(
            samplerate=self.sample_rate,
            device=self.input_device,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            callback=self._mic_callback,
        )
        mic_stream.start()

        # Start playback thread
        playback = threading.Thread(target=self._playback_thread, daemon=True)
        playback.start()

        self.set_state("idle")
        print(f"[ready] LiveKit Echo-Node running", flush=True)
        print(f"[ready] Press Ctrl+C to stop", flush=True)

        # Keep running until interrupted
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup(mic_stream)

    def _generate_token(self) -> str:
        """Generate a local dev token for the LiveKit server."""
        from livekit import api
        try:
            token = api.AccessToken(
                os.environ.get("LIVEKIT_API_KEY", "devkey"),
                os.environ.get("LIVEKIT_API_SECRET", "secret"),
            )\
                .with_identity("echo-node-client")\
                .with_name("Echo-Node Client")\
                .with_grants(api.VideoGrants(
                    room_join=True,
                    room=self.room_name,
                ))\
                .to_jwt()
            return token
        except Exception as exc:
            print(f"[client] token gen failed: {exc}", flush=True)
            return ""

    def _cleanup(self, mic_stream: sd.InputStream | None = None) -> None:
        self._running = False
        if mic_stream:
            mic_stream.stop()
        if self._room:
            self._room.disconnect()
        print("[client] cleaned up", flush=True)


# ── Entry point ──────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Echo-Node LiveKit Client")
    parser.add_argument("--url", default=os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880"))
    parser.add_argument("--token", default=os.environ.get("LIVEKIT_TOKEN", ""))
    parser.add_argument("--room", default="echo-node")
    parser.add_argument("--input-device", type=int, default=None)
    parser.add_argument("--output-device", type=int, default=None)
    parser.add_argument("--no-wake", action="store_true", help="Disable wake word")
    args = parser.parse_args()

    client = LiveKitClient(
        livekit_url=args.url,
        livekit_token=args.token,
        room_name=args.room,
        input_device=args.input_device,
        output_device=args.output_device,
        wake_enabled=not args.no_wake,
    )

    client.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
