"""Avatar lip-sync subsystem for Echo-Node v2.

Modules
-------
preprocess  -- strips the baked checker background from source sheets and
               writes one PNG per viseme into frames/<character>/<VISEME>.png
window      -- PyQt6 sidecar process: frameless, transparent, always-on-top
               floating window in the bottom-right of the primary screen,
               driven by a line-delimited JSON protocol on stdin
controller  -- in-process driver: spawns the sidecar, runs Rhubarb on each
               TTS WAV, and ships viseme timings to the sidecar to swap
               frames in sync with playback
"""

"""Avatar lip-sync subsystem for Echo-Node v2.

Modules
-------
preprocess  -- strips the baked checker background from source sheets and
               writes one PNG per viseme into frames/<character>/<VISEME>.png
window      -- PyQt6 sidecar process: frameless, transparent, always-on-top
               floating window in the bottom-right of the primary screen,
               driven by a line-delimited JSON protocol on stdin
controller  -- in-process driver: spawns the sidecar, runs Rhubarb on each
               TTS WAV, and ships viseme timings to the sidecar to swap
               frames in sync with playback
"""

from .controller import AvatarController, NullAvatar, build  # noqa: F401


def build_controller(config: dict) -> AvatarController | NullAvatar:
    """Shorthand for `avatar.build()` — returns a configured controller."""
    return build(config)


def window_main() -> int:
    """Run the avatar window as a standalone app."""
    from . import window
    return window.main()


def preprocess_main() -> None:
    """Run preprocessing from the command line."""
    from . import preprocess
    preprocess.main()


__all__ = [
    "AvatarController", "NullAvatar", "build", "build_controller",
    "controller", "preprocess", "window",
    "window_main", "preprocess_main",
]

