#!/usr/bin/env python3
"""Echo-Node Google video client — runs the lk_echo client with Google config.

The client is the same PyQt6 desktop video viewer:
  - Connects to the LiveKit room
  - Shows avatar video in a frameless window
  - Bridges mic/speaker via sounddevice
  - IPC with the FIFO for state display
"""

import runpy
import sys
from pathlib import Path

# Run the existing lk_echo.client_video module
client_path = Path(__file__).resolve().parent.parent / "lk_echo" / "client_video.py"
sys.argv[0] = str(client_path)
runpy.run_path(str(client_path), run_name="__main__")
