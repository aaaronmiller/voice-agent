"""Echo-Node LemonSlice Video Client — Desktop avatar viewer + audio bridge.

This PyQt6 application:
  1. Connects to the local LiveKit server
  2. Finds the LemonSlice avatar participant
  3. Renders the avatar's video track in a window
  4. Plays the avatar's audio track through speakers
  5. Captures microphone audio and publishes it to the room
  6. Handles keyboard hotkeys and communicates via the FIFO

Requires: livekit, PyQt6, sounddevice, numpy
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
from livekit import rtc

# Qt — force offscreen if needed, then import
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QImage, QPixmap, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QPushButton,
)

logger = logging.getLogger("echo-node-client")

# ── Paths ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
AVATAR_FIFO = "/tmp/echo-node-avatar.fifo"

# ── Audio config ───────────────────────────────────────────────────

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = np.int16
CHUNK_SIZE = int(SAMPLE_RATE * 20 / 1000)  # 20ms

# ── LemonSlice avatar identity ─────────────────────────────────────

AVATAR_IDENTITY = "lemonslice-avatar-agent"


# ── Qt Video Window ────────────────────────────────────────────────

class VideoFrameProcessor(QThread):
    """Background thread that reads LiveKit video frames and emits them to Qt."""

    frame_ready = pyqtSignal(object)  # emits QImage
    
    def __init__(self, room: rtc.Room, parent=None):
        super().__init__(parent)
        self._room = room
        self._running = False
        self._video_stream = None
        self._avatar_track = None

    def set_avatar_track(self, track: rtc.RemoteVideoTrack):
        self._avatar_track = track

    async def _run(self):
        if self._avatar_track is None:
            return
        self._video_stream = rtc.VideoStream.from_track(self._avatar_track)
        try:
            async for event in self._video_stream:
                frame = event.frame
                # Convert to RGBA
                rgba = frame.convert(rtc.VideoBufferType.RGBA, flip_y=True)
                img = QImage(
                    rgba.data,
                    rgba.width,
                    rgba.height,
                    QImage.Format.Format_RGBA8888,
                )
                self.frame_ready.emit(img)
        except Exception as exc:
            logger.warning(f"Video stream error: {exc}")
        finally:
            await self._video_stream.aclose()

    def run(self):
        self._running = True
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._run())

    def stop(self):
        self._running = False
        if self._video_stream:
            asyncio.run_coroutine_threadsafe(
                self._video_stream.aclose(), asyncio.get_event_loop()
            )


class AvatarVideoWindow(QMainWindow):
    """Displays the LemonSlice avatar video feed."""

    def __init__(self, room: rtc.Room):
        super().__init__()
        self._room = room
        self._audio_queue: queue.Queue = queue.Queue()
        self._running = True
        self._audio_stream_obj = None

        # Window setup
        self.setWindowTitle("Jess — Echo-Node")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Central widget
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(320, 240)
        self._video_label.setStyleSheet(
            "border-radius: 16px; background: #1a1a2e;"
        )
        layout.addWidget(self._video_label)

        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(8, 4, 8, 4)

        self._state_label = QLabel("connecting...")
        self._state_label.setStyleSheet("color: #888; font-size: 11px;")
        self._state_label.setFont(QFont("monospace", 9))
        btn_layout.addWidget(self._state_label)

        btn_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { color: #f44; background: rgba(255,68,68,0.1); "
            "border-radius: 12px; border: none; font-size: 14px; }"
            "QPushButton:hover { background: rgba(255,68,68,0.3); }"
        )
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        # Set fixed size
        self.resize(360, 300)
        self._center_on_screen()

        # Register room handlers
        self._room.on("track_subscribed", self._on_track_subscribed)
        self._room.on("participant_connected", self._on_participant_connected)

        # Video processor
        self._video_processor = VideoFrameProcessor(self._room)
        self._video_processor.frame_ready.connect(self._on_frame)
        self._video_processor.start()

        # Timer for state updates via FIFO
        self._fifo_timer = QTimer()
        self._fifo_timer.timeout.connect(self._check_fifo)
        self._fifo_timer.start(100)

        # Timer to poll for avatar participant
        self._find_avatar_timer = QTimer()
        self._find_avatar_timer.timeout.connect(self._find_avatar)
        self._find_avatar_timer.start(500)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.center().x() - self.width() // 2
            y = geo.center().y() - self.height() // 2
            self.move(x, y)

    def _find_avatar(self):
        """Poll for avatar participant until found."""
        for participant in self._room.remote_participants.values():
            if participant.identity == AVATAR_IDENTITY:
                logger.info(f"Avatar found: {participant.identity}")
                self._find_avatar_timer.stop()
                self._state_label.setText("Jess is ready")
                # Find the video track
                for track_id, pub in participant.track_publications.items():
                    if pub.kind == rtc.TrackKind.KIND_VIDEO and pub.subscribed:
                        track = pub.track
                        if isinstance(track, rtc.RemoteVideoTrack):
                            self._video_processor.set_avatar_track(track)
                break

    def _on_participant_connected(self, participant: rtc.RemoteParticipant):
        logger.info(f"Participant joined: {participant.identity}")
        if participant.identity == AVATAR_IDENTITY:
            self._state_label.setText("Jess connected")
            # Subscribe to avatar's audio track
            for track_id, pub in participant.track_publications.items():
                if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.subscribed:
                    track = pub.track
                    if isinstance(track, rtc.RemoteAudioTrack):
                        self._start_audio_playback(track)

    def _on_track_subscribed(self, track: rtc.Track, *_args):
        """Handle tracks published by the avatar."""
        if isinstance(track, rtc.RemoteVideoTrack):
            logger.info(f"Video track subscribed: {track.sid}")
            self._video_processor.set_avatar_track(track)
        elif isinstance(track, rtc.RemoteAudioTrack):
            logger.info(f"Audio track subscribed: {track.sid}")
            self._start_audio_playback(track)

    def _start_audio_playback(self, track: rtc.RemoteAudioTrack):
        """Start reading audio frames from the avatar's audio track."""
        thread = threading.Thread(
            target=self._audio_playback_loop,
            args=(track,),
            daemon=True,
        )
        thread.start()

    def _audio_playback_loop(self, track: rtc.RemoteAudioTrack):
        """Read audio frames and play through speakers."""
        stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def read_audio():
                audio_stream = rtc.AudioStream.from_track(track)
                try:
                    async for event in audio_stream:
                        frame = event.frame
                        data = np.frombuffer(frame.data, dtype=DTYPE)
                        stream.write(data)
                except Exception as exc:
                    logger.warning(f"Audio stream error: {exc}")
                finally:
                    await audio_stream.aclose()

            loop.run_until_complete(read_audio())
        finally:
            stream.stop()

    def _on_frame(self, image: QImage):
        """Update the video display with a new frame."""
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self._video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(scaled)

    def _check_fifo(self):
        """Read commands from the FIFO."""
        try:
            with open(AVATAR_FIFO, "r") as f:
                line = f.readline().strip()
                if line:
                    try:
                        cmd = json.loads(line)
                        self._handle_fifo_cmd(cmd)
                    except json.JSONDecodeError:
                        pass
        except (FileNotFoundError, OSError):
            pass

    def _handle_fifo_cmd(self, cmd: dict):
        """Handle FIFO commands."""
        cmd_type = cmd.get("cmd")
        if cmd_type == "quit":
            QApplication.quit()
        elif cmd_type == "hide":
            self.hide()
        elif cmd_type == "show":
            self.show()
            self.raise_()
        elif cmd_type == "debug_update":
            state = cmd.get("state")
            if state:
                self._state_label.setText(state)

    def closeEvent(self, event):
        self._running = False
        if self._video_processor:
            self._video_processor.stop()
        super().closeEvent(event)


# ── Audio bridge (mic → room) ─────────────────────────────────────

class MicBridge:
    """Captures microphone audio and publishes to the LiveKit room."""

    def __init__(self, room: rtc.Room):
        self._room = room
        self._audio_source = None
        self._mic_track = None

    async def start(self):
        self._audio_source = rtc.AudioSource(SAMPLE_RATE, CHANNELS)
        self._mic_track = rtc.LocalAudioTrack.create_audio_track(
            "mic", self._audio_source
        )
        await self._room.local_participant.publish_track(
            self._mic_track, rtc.TrackPublishOptions()
        )
        logger.info("Mic track published")

        # Start sounddevice capture in a thread
        thread = threading.Thread(target=self._capture_loop, daemon=True)
        thread.start()

    def _capture_loop(self):
        def callback(indata: np.ndarray, frames: int, _time, _status):
            if self._audio_source is None:
                return
            frame = rtc.AudioFrame(
                data=indata.tobytes(),
                sample_rate=SAMPLE_RATE,
                num_channels=CHANNELS,
                samples_per_channel=frames,
            )
            self._audio_source.capture_frame(frame)

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            callback=callback,
        )
        stream.start()
        try:
            while True:
                time.sleep(1)
        finally:
            stream.stop()


# ── Main entry point ───────────────────────────────────────────────

async def run_client(livekit_url: str, token: str, room_name: str):
    """Connect to LiveKit and start the desktop video client."""
    
    room = rtc.Room()

    # Create Qt app in main thread
    app = QApplication.instance() or QApplication(sys.argv)
    window = AvatarVideoWindow(room)
    window.show()

    # Connect to LiveKit
    @room.on("connection_state")
    def on_conn_state(state: rtc.ConnectionState):
        logger.info(f"Room connection state: {state}")

    logger.info(f"Connecting to {livekit_url} room={room_name}")
    await room.connect(livekit_url, token, room_name)
    logger.info(f"Connected to room: {room.name}")

    # Start mic bridge
    bridge = MicBridge(room)
    await bridge.start()

    # Write ready message to FIFO
    try:
        with open(AVATAR_FIFO, "w") as f:
            f.write(json.dumps({"cmd": "debug_update", "state": "connected"}) + "\n")
    except (OSError, IOError):
        pass

    # Run Qt event loop
    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(description="Echo-Node LemonSlice Video Client")
    parser.add_argument("--url", default=os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880"))
    parser.add_argument("--token", default=os.environ.get("LIVEKIT_TOKEN", ""))
    parser.add_argument("--room", default="echo-node")
    parser.add_argument("--api-key", default=os.environ.get("LIVEKIT_API_KEY", "devkey"))
    parser.add_argument("--api-secret", default=os.environ.get("LIVEKIT_API_SECRET", "secret"))
    args = parser.parse_args()

    # Generate token if not provided
    token = args.token
    if not token:
        from livekit import api
        token = api.AccessToken(args.api_key, args.api_secret) \
            .with_identity("echo-node-client") \
            .with_name("Echo-Node Desktop") \
            .with_grants(api.VideoGrants(room_join=True, room=args.room)) \
            .to_jwt()

    # Run the async client
    asyncio.run(run_client(args.url, token, args.room))


if __name__ == "__main__":
    main()
