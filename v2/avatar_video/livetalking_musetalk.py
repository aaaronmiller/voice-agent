"""LiveTalking-style harness around the MuseTalk prototype.

Wraps :class:`avatar_video.musetalk_assistant.MuseTalkRenderer` in the
:py:class:`~echo_node.slots.AvatarRenderer` contract (``preload`` /
``play`` / ``stop``) so the prototype can take the AVATAR slot.

What this is: a thin adapter. ``preload(wav)`` starts background frame
generation for one TTS chunk; ``play()`` drains frames into a frame sink
at the configured fps; ``stop()`` halts the drain.

What this is NOT (remaining gaps — experimental until closed):
  1. It is not the real LiveTalking harness: no WebRTC transport, no
     interruption protocol, no task tracking / session state machine.
     Porting those is the actual LiveTalking work (ROADMAP §2 item 4).
  2. Generation is per-WAV batch in a background thread, not true
     chunked streaming — first frame still waits on the full chunk.
  3. The frame sink is a placeholder: a ``frame_sink`` callable in
     config, defaulting to a null sink. The real Qt avatar window wiring
     is not done here.
  4. Interruption is coarse: ``stop()`` halts frame display but cannot
     preempt an in-flight generation (the prototype has no cancel API).
  5. MuseTalk itself needs a CUDA GPU + the model manifest; none of
     that was exercised on this VM.

Heavy deps (torch, cv2, sounddevice — the prototype module imports them
at top level and chdir's into avatar_video/) are imported lazily inside
methods, so importing THIS module never crashes and ``validate()`` stays
honest on machines without them.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from echo_node.slots import AvatarRenderer, Capability
from echo_node.slots.validation import (
    ValidationResult,
    check_cuda,
    check_module,
    check_paths,
    missing_result,
    ok_result,
)

# avatar_video/ lives next to echo_node/ under v2/.
_V2_ROOT = Path(__file__).resolve().parent.parent


class LiveTalkingMuseTalk(AvatarRenderer):
    """AvatarRenderer harness around the MuseTalk prototype.

    Config keys: ``photo_path`` (source face photo), ``manifest_path``
    (models/manifest.json), ``fps`` (25), ``batch_size`` (16),
    ``frame_sink`` (callable(frame: np.ndarray) -> None, default null).
    """

    def __init__(self, config: dict[str, Any]):
        cfg = dict(config or {})
        self.photo_path = str(cfg.get("photo_path",
                                      str(_V2_ROOT / "avatar_video" / "face.jpg")))
        self.manifest_path = cfg.get("manifest_path")  # renderer picks its default
        self.fps = int(cfg.get("fps", 25))
        self.batch_size = int(cfg.get("batch_size", 16))
        self.frame_sink: Callable[[Any], None] = cfg.get("frame_sink") or (lambda _f: None)
        self._renderer: Any | None = None
        self._display_thread: threading.Thread | None = None
        self._display_running = False
        self._lock = threading.Lock()

    # ── Slot contract ──────────────────────────────────────────────

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="musetalk-livetalking",
            version="1.5 (harness)",
            languages=[],
            streaming=True,   # frames drain while audio plays
            vram_gb=1.9,      # ~1.9GB per prototype load() docstring
            gpu_required=True,
            license="unknown",
            network=False,
            notes=("LiveTalking-style harness (preload/play/stop) around the "
                   "MuseTalk prototype; NOT the real LiveTalking harness — "
                   "no WebRTC, no interruption protocol; experimental, "
                   "unverified on target hardware"),
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        # Heavy prototype deps are never imported here — presence probes only.
        details: dict[str, Any] = {}
        problems = []
        for mod in ("torch", "cv2", "sounddevice", "numpy"):
            found, ver = check_module(mod)
            details[mod] = ver if found else "missing"
            if not found:
                problems.append(f"{mod} not installed")
        cuda_ok, cuda_info = check_cuda()
        details["cuda"] = cuda_info
        if not cuda_ok:
            problems.append(f"CUDA unavailable: {cuda_info}")
        cfg = config or {}
        manifest = str(cfg.get("manifest_path",
                               _V2_ROOT / "avatar_video" / "models" / "manifest.json"))
        details["manifest"] = manifest
        if check_paths(manifest):
            problems.append(f"model manifest missing: {manifest}")
        photo = str(cfg.get("photo_path", _V2_ROOT / "avatar_video" / "face.jpg"))
        details["photo"] = photo
        if check_paths(photo):
            problems.append(f"source photo missing: {photo}")
        # Contract conformance: this harness genuinely implements the ABC.
        missing_methods = [m for m in ("preload", "play", "stop")
                           if not callable(getattr(cls, m, None))]
        if missing_methods:
            problems.append(f"missing AvatarRenderer methods: {', '.join(missing_methods)}")
        if problems:
            return ValidationResult(False, "; ".join(problems), details)
        return ok_result("livetalking harness deps + models + photo present", details)

    # ── Renderer lifecycle (lazy; heavy imports stay inside) ───────

    def _ensure_renderer(self) -> Any:
        if self._renderer is not None:
            return self._renderer
        # Deferred: musetalk_assistant imports torch/cv2/sounddevice at
        # module level and chdir's into avatar_video/ on import.
        from avatar_video.musetalk_assistant import MuseTalkRenderer
        kwargs: dict[str, Any] = {
            "photo_path": self.photo_path,
            "fps": self.fps,
            "batch_size": self.batch_size,
        }
        if self.manifest_path:
            kwargs["manifest_path"] = self.manifest_path
        renderer = MuseTalkRenderer(**kwargs)
        renderer.load()  # ~8 s, ~1.9 GB VRAM; raises on missing models
        self._renderer = renderer
        return renderer

    def preload(self, wav_path: Path) -> bool:
        """Start background frame generation for *wav_path*.

        Returns True when frames will play. Mirrors the rhubarb
        controller's contract so InterruptibleSpeaker can call it the
        same way.
        """
        try:
            renderer = self._ensure_renderer()
        except Exception:
            return False
        try:
            renderer.generate(str(wav_path))
            return True
        except Exception:
            return False

    def play(self) -> None:
        """Drain generated frames into the frame sink at fps pacing."""
        with self._lock:
            if self._display_running or self._renderer is None:
                return
            self._display_running = True
            self._display_thread = threading.Thread(
                target=self._display_loop, daemon=True)
            self._display_thread.start()

    def _display_loop(self) -> None:
        renderer = self._renderer
        interval = 1.0 / max(1, self.fps)
        last = 0.0
        while self._display_running and renderer is not None:
            frame = renderer.get_frame()
            if frame is None:
                # No frames yet and generation finished → done.
                gen = getattr(renderer, "_generate_thread", None)
                if gen is None or not gen.is_alive():
                    break
                time.sleep(0.005)
                continue
            now = time.monotonic()
            if now - last >= interval:
                try:
                    self.frame_sink(frame)
                except Exception:
                    pass
                last = now
            else:
                time.sleep(0.002)
        with self._lock:
            self._display_running = False

    def stop(self) -> None:
        """Halt frame display.

        Coarse interruption (documented gap): the in-flight generation
        thread is NOT preempted — the prototype exposes no cancel API —
        but its remaining frames are dropped from the queue.
        """
        with self._lock:
            self._display_running = False
            thread = self._display_thread
            self._display_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        renderer = self._renderer
        if renderer is not None:
            # Drop queued frames so a stopped chunk doesn't leak into
            # the next one. get_frame() returns None when empty.
            try:
                while renderer.get_frame() is not None:
                    pass
            except Exception:
                pass

    def unload(self) -> None:
        self.stop()
        renderer, self._renderer = self._renderer, None
        if renderer is not None:
            try:
                renderer.unload()
            except Exception:
                pass
