#!/usr/bin/env python3
"""
Echo-Node Audio Worker - Main Entry Point

WebSocket server on port 9001.
Manages audio capture, ML inference (STT/TTS/VAD/wake word), and pipeline state.
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from worker.config import Config, ConfigError
from worker.state_machine import StateMachine, State
from worker.vram_calculator import VRAMCalculator
from worker.audio.capture import AudioCapture
from worker.audio.playback import AudioPlayback
from worker.providers import create_provider, get_available_providers

# WebSocket server (using aiohttp for now)
try:
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class EchoNodeWorker:
    """
    Main worker instance for Echo-Node.

    Manages:
    - WebSocket connection to gateway
    - Audio capture and playback
    - Pipeline state machine
    - Provider initialization and lifecycle
    - Cloud mode (Gemini Live) integration
    """

    def __init__(self, config: Config):
        """
        Initialize worker.

        Args:
            config: Loaded configuration
        """
        self.config = config
        self.state_machine: StateMachine | None = None
        self.vram_calc = VRAMCalculator()
        self.audio_capture: AudioCapture | None = None
        self.audio_playback: AudioPlayback | None = None
        self.websocket: web.WebSocketResponse | None = None
        self._running = False
        self._ready = False
        self._cloud_mode = False
        self._gemini_adapter = None

    def _estimate_vram_needs(self) -> int:
        """
        Estimate total VRAM needed based on config.

        Returns:
            Estimated VRAM in MB
        """
        total = 0

        # STT VRAM
        stt_provider = self.config.get("stt", "provider", default="sherpa-onnx")
        stt_vram = {"sherpa-onnx": 1500, "faster-whisper": 2000, "vibevoice-asr": 6000}
        total += stt_vram.get(stt_provider, 1500)

        # TTS VRAM
        tts_provider = self.config.get("tts", "provider", default="kokoro")
        tts_vram = {"kokoro": 512, "chatterbox": 1000, "orpheus": 2000, "piper": 300}
        total += tts_vram.get(tts_provider, 512)

        # VAD VRAM (small, ~50MB)
        total += 50

        # Wake word VRAM (~100MB)
        total += 100

        # LLM VRAM (largest variable)
        llm_model = self.config.get("llm", "model", default="llama3.2:7b")
        if "7b" in llm_model.lower():
            total += 4096
        elif "13b" in llm_model.lower():
            total += 8192
        elif "70b" in llm_model.lower():
            total += 40960
        else:
            total += 4096  # Default

        return total

    async def initialize(self) -> None:
        """
        Initialize all components.

        Validates VRAM, loads providers, sets up audio.
        """
        print("[Worker] Initializing...")

        # Check pipeline mode
        pipeline_mode = self.config.get("echo_node", "pipeline_mode", default="local")
        self._cloud_mode = pipeline_mode == "cloud"

        if self._cloud_mode:
            print("[Worker] 🔀 Pipeline mode: CLOUD (Gemini Live)")
            await self._initialize_cloud_mode()
        else:
            print("[Worker] 🔀 Pipeline mode: LOCAL")
            await self._initialize_local_mode()

    async def _initialize_cloud_mode(self) -> None:
        """Initialize in cloud mode (Gemini Live)."""
        # In cloud mode, we still need audio capture/playback for relaying
        # but skip local STT/TTS/LLM providers
        print("[Worker] Cloud mode: Setting up audio relay only")

        # Initialize audio capture (for relaying to Gemini)
        self.audio_capture = AudioCapture(
            sample_rate=self.config.get("audio", "sample_rate", default=16000),
            channels=self.config.get("audio", "channels", default=1),
            chunk_size=self.config.get("audio", "chunk_size", default=512),
            device=self.config.get("audio", "device"),
        )
        await self.audio_capture.initialize()

        # Initialize audio playback (for Gemini audio output)
        self.audio_playback = AudioPlayback(
            sample_rate=self.config.get("tts", "sample_rate", default=24000),
        )
        await self.audio_playback.initialize()

        # Initialize state machine for cloud mode
        self.state_machine = StateMachine(on_transition=self._on_state_change)

        print("[Worker] Cloud mode initialization complete")

    async def _initialize_local_mode(self) -> None:
        """Initialize in local mode (all local providers)."""
        # Check VRAM requirements BEFORE loading providers
        print("[Worker] Checking VRAM...")
        vram_report = self.vram_calc.get_vram_report()
        has_gpu = vram_report["gpu_count"] > 0

        if has_gpu:
            print(
                f"[Worker] GPU: {vram_report['gpu_count']} devices, "
                f"{vram_report['total_mb']}MB total, "
                f"{vram_report['available_mb']}MB available"
            )
        else:
            print("[Worker] No GPU detected, will use CPU fallback")

        # Calculate estimated VRAM needs based on config
        estimated_vram = self._estimate_vram_needs()

        if has_gpu and estimated_vram > vram_report["available_mb"]:
            shortfall = estimated_vram - vram_report["available_mb"]
            print(
                f"[Worker] ⚠️  WARNING: Estimated VRAM need ({estimated_vram}MB) "
                f"exceeds available ({vram_report['available_mb']}MB) by {shortfall}MB"
            )
            print("[Worker] Suggest:")
            print("  - Use smaller models (kokoro instead of orpheus)")
            print("  - Enable CPU fallback for some providers")
            print("  - Use 4-bit quantization (e.g., vibevoice-asr q4)")

        # Initialize state machine
        self.state_machine = StateMachine(on_transition=self._on_state_change)

        # Initialize audio
        self.audio_capture = AudioCapture(
            sample_rate=self.config.get("audio", "sample_rate", default=16000),
            channels=self.config.get("audio", "channels", default=1),
            chunk_size=self.config.get("audio", "chunk_size", default=512),
            device=self.config.get("audio", "device"),
        )
        await self.audio_capture.initialize()

        self.audio_playback = AudioPlayback(
            sample_rate=self.config.get("tts", "sample_rate", default=24000),
        )
        await self.audio_playback.initialize()

        # Log active personality
        active_personality = self.config.get("personality", "active", default="hacker")
        custom_prompt = self.config.get("personality", "custom_prompt", default="")
        if active_personality == "custom" and custom_prompt:
            print(f"[Worker] Personality: {active_personality} (custom)")
        else:
            print(f"[Worker] Personality: {active_personality}")

        print("[Worker] Initialization complete")

    def _on_state_change(self, old: State, new: State) -> None:
        """
        Handle state transition.

        Emits state change event to gateway.
        """
        event = {
            "type": "state_change",
            "from": old.value,
            "to": new.value,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        self._send_event(event)
        print(f"[Worker] State: {old.value} → {new.value}")

    async def _send_event(self, event: dict) -> None:
        """Send event to gateway via WebSocket."""
        if self.websocket and not self.websocket.closed:
            import json

            await self.websocket.send_str(json.dumps(event))

    async def _send_ready(self) -> None:
        """Signal that worker is ready for voice input."""
        await self._send_event({"type": "ready"})
        self._ready = True
        print("[Worker] ✅ Ready for voice input")

    async def _play_startup_chime(self) -> None:
        """Play startup chime to signal readiness."""
        enabled = self.config.get("activation_sound", "enabled", default=True)
        if not enabled:
            return

        # Play chime sound (placeholder - actual implementation in Phase 3)
        print("[Worker] 🔔 Playing startup chime")

        # TODO: Load and play worker/sounds/chime.wav
        # For now, just log it

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """
        Handle WebSocket connection from gateway.
        """
        self.websocket = web.WebSocketResponse()
        await self.websocket.prepare(request)

        print("[Worker] Gateway connected")

        try:
            async for msg in self.websocket:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"[Worker] WebSocket error: {self.websocket.exception()}")
        finally:
            print("[Worker] Gateway disconnected")
            self.websocket = None

        return self.websocket

    async def _handle_message(self, data: str) -> None:
        """
        Handle message from gateway.

        Expected messages:
        - keyboard_trigger: Manual activation
        - barge_in: Interrupt speaking
        - config_update: Configuration change
        - stop: Halt pipeline
        """
        import json

        try:
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "keyboard_trigger":
                await self._handle_keyboard_trigger()
            elif msg_type == "barge_in":
                await self._handle_barge_in()
            elif msg_type == "config_update":
                await self._handle_config_update(message.get("config", {}))
            elif msg_type == "stop":
                await self._handle_stop()
            else:
                print(f"[Worker] Unknown message type: {msg_type}")
        except json.JSONDecodeError:
            print(f"[Worker] Invalid JSON: {data}")
        except Exception as e:
            print(f"[Worker] Error handling message: {e}")

    async def _handle_keyboard_trigger(self) -> None:
        """Handle manual keyboard trigger."""
        if self.state_machine and self.state_machine.state == State.DORMANT:
            await self.state_machine.transition(State.TRIGGERED)

            if self._cloud_mode:
                await self._start_cloud_stream()
            else:
                await self.state_machine.transition(State.LISTENING)

    async def _start_cloud_stream(self) -> None:
        """Start Gemini Live cloud stream."""
        if not self._cloud_mode:
            return

        print("[Worker] ☁️  Starting cloud stream (Gemini Live)")
        await self.state_machine.transition(State.LISTENING)

        # The gateway handles the actual Gemini Live WebSocket connection
        # We just need to signal that we're in cloud mode and relay audio
        await self._send_event(
            {
                "type": "cloud_stream_start",
                "provider": "gemini-live",
                "sample_rate": self.config.get("audio", "sample_rate", default=16000),
            }
        )

    async def _stop_cloud_stream(self) -> None:
        """Stop Gemini Live cloud stream."""
        print("[Worker] ☁️  Stopping cloud stream")
        await self._send_event(
            {
                "type": "cloud_stream_stop",
            }
        )

        if self.state_machine and self.state_machine.state != State.DORMANT:
            await self.state_machine.transition(State.DORMANT)

    async def _handle_barge_in(self) -> None:
        """Handle barge-in interrupt."""
        if self.state_machine and self.state_machine.state == State.SPEAKING:
            await self.state_machine.transition(State.LISTENING)

    async def _handle_config_update(self, updates: dict) -> None:
        """Handle configuration update."""
        try:
            self.config.update(updates)
            print("[Worker] Configuration updated")
        except ConfigError as e:
            print(f"[Worker] Config update failed: {e}")
            await self._send_event(
                {
                    "type": "error",
                    "message": str(e),
                    "code": "CONFIG_INVALID",
                }
            )

    async def _handle_stop(self) -> None:
        """Handle stop command."""
        if self.state_machine:
            await self.state_machine.reset()
        print("[Worker] Pipeline stopped")

    async def run(self) -> None:
        """
        Run the worker server.
        """
        if not AIOHTTP_AVAILABLE:
            print("[Worker] ERROR: aiohttp not installed. Run: pip install aiohttp")
            return

        await self.initialize()

        # Create web application
        app = web.Application()
        app.router.add_get("/ws", self.handle_websocket)

        # Get port from config
        port = self.config.get("worker", "port", default=9001)

        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", port)
        await site.start()

        print(f"[Worker] WebSocket server started on ws://localhost:{port}")

        # Signal ready for voice input
        await self._send_ready()

        # Play startup chime (if enabled)
        await self._play_startup_chime()

        self._running = True

        # Keep running until shutdown
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown worker gracefully."""
        print("[Worker] Shutting down...")
        self._running = False

        # Cleanup audio
        if self.audio_capture:
            await self.audio_capture.stop()
        if self.audio_playback:
            await self.audio_playback.stop()

        # Cleanup VRAM
        self.vram_calc.shutdown()

        print("[Worker] Shutdown complete")


async def main():
    """Main entry point."""
    worker = None

    def signal_handler(sig, frame):
        print("\n[Worker] Interrupt received, shutting down...")
        if worker:
            asyncio.create_task(worker.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Load configuration
        config = Config()
        worker = EchoNodeWorker(config)
        await worker.run()
    except ConfigError as e:
        print(f"[Worker] Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[Worker] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
