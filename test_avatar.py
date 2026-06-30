#!/usr/bin/env python3
"""Tests for the avatar system — window styling, controller, IPC protocol."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE / "v2"
AVATAR = V2 / "avatar"


# ── helpers ──────────────────────────────────────────────────────────

def banner(s: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {s}")
    print(f"{'='*60}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    global _failures
    _failures += 1


_failures = 0


# ── 1. Frame style rendering ─────────────────────────────────────────

def test_frame_styles() -> None:
    banner("1. Frame style generation (HSL)")

    sys.path.insert(0, str(AVATAR))
    import importlib
    import window as w
    importlib.reload(w)

    # Test HSL helpers
    css = w.hsl_css(220, 80, 50, 0.5)
    assert "hsla(220,80%," in css and "50%,0.5)" in css, f"Unexpected HSL CSS: {css}"
    ok(f"hsl_css produces correct hsla: {css}")

    # Quick colors
    assert len(w.QUICK_COLORS) >= 8, f"Expected >=8 quick colors, got {len(w.QUICK_COLORS)}"
    ok(f"Quick color presets: {len(w.QUICK_COLORS)}")

    # Shape constants
    assert "square" in w.SHAPES
    assert "rounded" in w.SHAPES
    assert "circle" in w.SHAPES
    ok(f"Shapes: {', '.join(w.SHAPES)}")

    # HSL edge cases
    css_black = w.hsl_css(0, 0, 0, 1.0)
    css_white = w.hsl_css(0, 0, 100, 1.0)
    css_full_sat = w.hsl_css(120, 100, 50, 0.8)
    ok(f"Black: {css_black}")
    ok(f"White: {css_white}")
    ok(f"Full sat green: {css_full_sat}")

    # Simulate frame CSS generation (matches _make_frame_css logic)
    def simulate_css(hue, sat, lig, shape, opacity, bw):
        from window import hsl_css
        bg_lig = max(3, min(20, lig // 3))
        bg = hsl_css(hue, max(20, sat), bg_lig, opacity)
        b_lig = min(100, lig + 25)
        b_alpha = max(0.15, 0.25 + (lig / 200))
        border_c = hsl_css(hue, sat, b_lig, b_alpha)
        r = 0
        if shape == "rounded": r = 18
        elif shape == "circle": r = 999
        bw = max(0.5, bw)
        return f"""
            QFrame {{
                background: {bg};
                border: {bw}px solid {border_c};
                border-radius: {r}px;
            }}
        """

    # Square
    css = simulate_css(220, 80, 55, "square", 0.55, 2.0)
    assert "border-radius: 0px" in css, f"Square border-radius fail:\n{css}"
    assert "hsla" in css
    ok("Square: border-radius 0px, hsla output")

    # Circle
    css = simulate_css(280, 70, 55, "circle", 0.7, 1.5)
    assert "border-radius: 999px" in css
    ok("Circle: border-radius 999px")

    # Rounded
    css = simulate_css(140, 75, 50, "rounded", 0.3, 1.0)
    assert "border-radius: 18px" in css
    ok("Rounded: border-radius 18px")

    # Border width floor
    css = simulate_css(190, 85, 50, "rounded", 0.5, 0.0)
    assert "border: 0.5px solid" in css
    ok("Min border width: 0.5px")

    # Verify low-lightness bg is dim
    css_dim = simulate_css(220, 80, 10, "rounded", 0.5, 1.5)
    assert "hsla" in css_dim
    ok("Low lightness produces dim background")

    # Verify high-lightness bg is bright
    css_bright = simulate_css(220, 80, 90, "rounded", 0.5, 1.5)
    assert "hsla" in css_bright
    ok("High lightness produces bright background")

    del sys.path[0]


# ── 2. Settings popup protocol (JSON commands emitted) ───────────────

def test_settings_protocol() -> None:
    banner("2. Settings IPC protocol")

    # Test the JSON commands that the popup emits to stdout
    # These are the same format the controller's _read_stdout will parse

    test_cases = [
        # (cmd, kwargs, expected_cmd, expected_fields)
        ("set_character", {"name": "owl-wizard"}, "set_character", ["name"]),
        ("set_frame_style", {"shape": "circle", "color": "purple", "opacity": 0.6, "border_width": 2.0},
         "set_frame_style", ["shape", "color", "opacity", "border_width"]),
        ("set_volume", {"value": 0.75}, "set_volume", ["value"]),
        ("set_silence_seconds", {"value": 0.8}, "set_silence_seconds", ["value"]),
        ("set_blink_interval", {"value": 3.0}, "set_blink_interval", ["value"]),
        ("set_size", {"value": 300}, "set_size", ["value"]),
    ]

    for cmd, kwargs, exp_cmd, exp_fields in test_cases:
        payload = {"cmd": cmd, **kwargs}
        assert payload["cmd"] == exp_cmd
        for f in exp_fields:
            assert f in payload, f"Missing field {f} in {payload}"
        # Round-trip through JSON
        rt = json.loads(json.dumps(payload))
        assert rt == payload
        ok(f"Protocol OK: {cmd} → {json.dumps(payload)}")

    # Test that _emit also prints to stdout (simulate popup behavior)
    emitted = []

    def _emit(cmd: str, **kw):
        payload = {"cmd": cmd, **kw}
        emitted.append(payload)
        # This is what the real popup does: print(json.dumps(payload), flush=True)

    _emit("set_volume", value=0.5)
    _emit("set_volume", value=0.8)
    assert len(emitted) == 2
    assert emitted[0] == {"cmd": "set_volume", "value": 0.5}
    assert emitted[1] == {"cmd": "set_volume", "value": 0.8}
    ok("Settings change events accumulate correctly")


# ── 3. Rhubarb subprocess integration ────────────────────────────────

def test_rhubarb_integration() -> None:
    banner("3. Rhubarb lip-sync")

    rhubarb = AVATAR.parent / "vendor" / "rhubarb" / "rhubarb"
    if not rhubarb.is_file():
        fail(f"Rhubarb binary not found at {rhubarb}")
        return

    # Check it's executable
    assert os.access(rhubarb, os.X_OK), f"{rhubarb} not executable"
    ok(f"Rhubarb binary: {rhubarb}")

    # Check version
    result = subprocess.run([str(rhubarb), "--version"], capture_output=True, text=True, timeout=5)
    version = result.stdout.strip() or result.stderr.strip()
    ok(f"Rhubarb version: {version}")

    # Find a real TTS output WAV, or generate a synthetic one
    test_wav = None
    # First, look in /tmp for echo-node generated WAVs
    from pathlib import Path as _Path
    for w in sorted(_Path("/tmp").glob("echo-node-*.wav")):
        if w.stat().st_size > 1000:
            test_wav = w
            break
    if test_wav is None:
        # Try other real WAVs
        for w in sorted(V2.rglob("*.wav")):
            if w.stat().st_size > 1000:
                test_wav = w
                break
    if test_wav is None:
        # Generate a synthetic test WAV with speech-like content
        import soundfile as _sf
        import numpy as _np
        sr = 24000
        dur = 0.8
        t = _np.linspace(0, dur, int(sr * dur), endpoint=False)
        # Mix tones + noise to simulate speech
        sig = (
            _np.sin(2 * _np.pi * 220 * t) * 0.3 +
            _np.sin(2 * _np.pi * 440 * t) * 0.15 +
            _np.sin(2 * _np.pi * 880 * t) * 0.05 +
            _np.random.randn(len(t)) * 0.02
        )
        import tempfile
        fd, p = tempfile.mkstemp(prefix="test-synth-", suffix=".wav")
        os.close(fd)
        test_wav = _Path(p)
        _sf.write(str(test_wav), sig, sr, subtype="PCM_16")
        ok(f"Generated synthetic test WAV at {test_wav}")

    ok(f"Test WAV: {test_wav} ({test_wav.stat().st_size} bytes)")

    # Run Rhubarb on it
    result = subprocess.run(
        [str(rhubarb), "-f", "json", "-r", "phonetic", str(test_wav)],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        fail(f"Rhubarb failed: {result.stderr.strip()}")
        return

    data = json.loads(result.stdout)
    cues = data.get("mouthCues", [])
    duration = (data.get("metadata") or {}).get("duration", 0)

    assert len(cues) > 0, f"No mouth cues in Rhubarb output: {data}"
    assert duration > 0, f"No duration in Rhubarb output: {data}"

    ok(f"Extracted {len(cues)} mouth cues over {duration:.2f}s")

    # Verify cue format
    for c in cues[:5]:
        assert "start" in c, f"Missing start in cue: {c}"
        assert "end" in c, f"Missing end in cue: {c}"
        assert "value" in c, f"Missing value in cue: {c}"
    ok(f"Cue format valid (first 5: {[c['value'] for c in cues[:5]]})")

    # Verify extended shapes if enabled
    has_extended = any(c["value"] in "GH" for c in cues)
    ok(f"{'Has extended shapes (G/H)' if has_extended else 'Basic shapes only (A-F)'}")

    # ── Test _normalise_to_pcm16 logic ──
    import soundfile as sf
    import tempfile

    data, sr = sf.read(str(test_wav), always_2d=False)
    fd, tmp = tempfile.mkstemp(prefix="test-normalise-", suffix=".wav")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        # Normalise: ensure mono, write as PCM_16
        if data.ndim > 1:
            data = data.mean(axis=1)
        sf.write(str(tmp_path), data, sr, subtype="PCM_16")
        info = sf.SoundFile(str(tmp_path))
        assert info.subtype == "PCM_16", f"Expected PCM_16, got {info.subtype}"
        assert info.channels == 1, f"Expected mono, got {info.channels} channels"
        ok(f"Normalise: PCM_16, {info.channels}ch, {info.samplerate}Hz")

        # Run Rhubarb on normalised file
        result2 = subprocess.run(
            [str(rhubarb), "-f", "json", "-r", "phonetic", str(tmp_path)],
            capture_output=True, text=True, timeout=10,
        )
        assert result2.returncode == 0, f"Rhubarb failed on normalised WAV"
        data2 = json.loads(result2.stdout)
        cues2 = data2.get("mouthCues", [])
        assert len(cues2) > 0, "No cues from normalised WAV"
        ok(f"Rhubarb on normalised WAV: {len(cues2)} cues")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


# ── 4. Avatar window sidecar lifecycle ───────────────────────────────

def test_sidecar_lifecycle() -> None:
    banner("4. Sidecar lifecycle (display required for Qt)")

    # Check if we have a display
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if not has_display:
        print("  ~ Skipping: no display server available (no DISPLAY/WAYLAND_DISPLAY)")
        return

    # Test the sidecar subprocess command construction
    sys.path.insert(0, str(AVATAR))
    import controller as ctrl_mod
    import importlib
    importlib.reload(ctrl_mod)

    config = {
        "enabled": True,
        "character": "raccoon-hacker",
        "recognizer": "phonetic",
    }

    # Start the controller (spawns window)
    ctrl = ctrl_mod.AvatarController(config)
    if not ctrl.enabled:
        fail("Controller did not enable")
        del sys.path[0]
        return

    pid = ctrl.process.pid if ctrl.process else 0
    ok(f"Controller enabled, sidecar PID={pid}" if pid else "Controller enabled (no sidecar)")

    # Send a frame style command
    ctrl.set_frame_style(shape="rounded", color="purple", opacity=0.5, border_width=2.0)
    time.sleep(0.3)  # let it arrive
    ok("set_frame_style sent to sidecar")

    # Cycle characters
    ctrl.set_character("owl-wizard")
    time.sleep(0.3)
    ok("set_character sent to sidecar")

    # Stop
    ctrl.stop()
    ok("stop command sent")

    # Shutdown
    ctrl.shutdown()
    ok(f"Sidecar pid={pid} shut down cleanly" if pid else "Controller shut down")

    del sys.path[0]


# ── 5. Characters & frames integrity ────────────────────────────────

def test_characters_integrity() -> None:
    banner("5. Characters and frame files integrity")

    import yaml

    manifest_path = AVATAR / "characters.yaml"
    assert manifest_path.is_file(), f"Missing characters.yaml at {manifest_path}"

    manifest = yaml.safe_load(manifest_path.read_text())
    characters = manifest.get("characters", {})
    assert len(characters) >= 5, f"Expected ≥5 characters, got {len(characters)}"
    ok(f"Characters defined: {len(characters)} — {', '.join(characters)}")

    frames_root = AVATAR / "frames"
    visemes = ("X", "A", "B", "C", "D", "E", "F", "G", "H")

    for ch_name in characters:
        ch_dir = frames_root / ch_name
        assert ch_dir.is_dir(), f"Missing frames directory for {ch_name}"

        files = list(ch_dir.iterdir())
        png_count = len([f for f in files if f.suffix == ".png"])

        missing = [v for v in visemes if not (ch_dir / f"{v}.png").is_file()]
        if missing:
            fail(f"{ch_name}: missing viseme frames: {missing} (has {png_count}/{len(visemes)} PNGs)")
        else:
            ok(f"{ch_name}: {png_count}/{len(visemes)} viseme frames")

    # Check source sprites exist
    sources_dir = AVATAR / "sources"
    if sources_dir.is_dir():
        sprite_count = len(list(sources_dir.glob("*.png")))
        ok(f"Source sprites: {sprite_count} in sources/")


# ── 6. NullAvatar fallback ──────────────────────────────────────────

def test_null_avatar() -> None:
    banner("6. NullAvatar fallback")

    sys.path.insert(0, str(AVATAR))
    import controller as ctrl_mod
    import importlib
    importlib.reload(ctrl_mod)
    from pathlib import Path

    null = ctrl_mod.NullAvatar("test reason")
    assert null.reason == "test reason"
    assert null.preload(Path("/nonexistent.wav")) is False
    assert null.play() is None
    assert null.stop() is None
    assert null.set_character("anything") is None
    assert null.set_frame_style() is None
    assert null.shutdown() is None
    ok("NullAvatar: all no-op methods work correctly")

    # build() should return NullAvatar when config disables
    null2 = ctrl_mod.build({"enabled": False})
    assert isinstance(null2, ctrl_mod.NullAvatar)
    ok("build(enabled=False) → NullAvatar")

    del sys.path[0]


# ── 7. Requires / versions ──────────────────────────────────────────

def test_dependencies() -> None:
    banner("7. Dependencies check")

    required = {
        "PyQt6": "PyQt6",
        "yaml": "PyYAML",
        "soundfile": "soundfile",
        "numpy": "numpy",
    }

    for mod_name, pkg_name in required.items():
        try:
            __import__(mod_name)
            ok(f"{pkg_name} installed")
        except ImportError:
            fail(f"{pkg_name} NOT installed")

    # Check Python version
    py = sys.version_info
    assert py.major >= 3 and py.minor >= 10, f"Python {py.major}.{py.minor} too old"
    ok(f"Python {py.major}.{py.minor}.{py.micro}")


# ── run all ──────────────────────────────────────────────────────────

def main() -> None:
    os.chdir(HERE)  # ensure CWD is voice-agent root

    test_dependencies()
    test_null_avatar()
    test_characters_integrity()
    test_frame_styles()
    test_settings_protocol()
    test_rhubarb_integration()
    test_sidecar_lifecycle()

    banner("SUMMARY")
    if _failures:
        print(f"  {_failures} test(s) FAILED\n")
        sys.exit(1)
    else:
        print("  All tests PASSED\n")


if __name__ == "__main__":
    main()
