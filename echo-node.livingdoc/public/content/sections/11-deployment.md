# Unified installer and launcher

**Phase:** 8 — Deployment | **Status:** Pending | **Owner:** DevOps team

## Entry criteria

- [x] Gateway running (Phase 2)
- [x] At least one frontend working (Phase 3 or 3b)
- [x] At least one live-voice provider working (Phase 5)
- [x] Modular pipeline working (Phase 4)

## Implementation

### Unified CLI: `echo-node`

A single entry point that dispatches to the right mode:

```bash
echo-node --web          # Launch web frontend (opens browser)
echo-node --tui          # Launch TUI frontend
echo-node --voice        # Legacy voice-only mode (no frontend)
echo-node --dashboard    # Launch only the latency dashboard
echo-node --help         # Show all options
```

```bash
# Global install via pip
pip install -e ~/code/voice-agent

# Or via bun for the gateway
cd ~/code/voice-agent/gateway && bun link
```

### Implementation (Python CLI entry point)

```python
# ~/code/voice-agent/echo_node/cli.py

import argparse
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description="Echo-Node voice agent")
    parser.add_argument("--web", action="store_true", help="Launch web frontend")
    parser.add_argument("--tui", action="store_true", help="Launch TUI frontend")
    parser.add_argument("--voice", action="store_true", help="Legacy voice-only mode")
    parser.add_argument("--dashboard", action="store_true", help="Latency dashboard only")
    parser.add_argument("--provider", default=None, help="Provider to use")
    parser.add_argument("--config", default=None, help="Config file path")
    parser.add_argument("--gateway-only", action="store_true", help="Start only the gateway")
    args = parser.parse_args()
    
    if args.web:
        # Start gateway + web frontend
        start_gateway()
        subprocess.run(["bun", "run", "dev"], cwd=FRONTEND_DIR)
    elif args.tui:
        # Start gateway + TUI frontend
        start_gateway()
        subprocess.run(["python", "-m", "echo_tui"], cwd=TUI_DIR)
    elif args.voice:
        # Legacy voice-only mode (no gateway needed)
        from echo_node.assistant import main as voice_main
        voice_main()
    elif args.dashboard:
        # Start gateway + launch browser to dashboard URL
        start_gateway()
        webbrowser.open("http://127.0.0.1:3000/dashboard")
    else:
        parser.print_help()
```

### Setup script

```bash
# ~/code/voice-agent/setup.sh — updated from existing

#!/bin/bash
set -euo pipefail

echo "=== Echo-Node Setup ==="

# 1. Python venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Python deps
pip install -e .          # Core echo_node package
pip install -r tui/requirements.txt  # TUI deps (Textual, etc.)

# 3. Bun deps (gateway + web frontend)
cd gateway && bun install && cd ..
cd frontend && bun install && cd ..

# 4. Download models (existing)
./v2/setup.sh --models-only

# 5. Create config
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo "Edit config.yaml with your API keys"
fi

echo "Done! Run: echo-node --help"
```

### Platform-specific launchers

**Linux / GNOME:**
- `echo-node --web` → starts gateway, opens browser
- Desktop file: `~/.local/share/applications/echo-node.desktop`
- Hotkey: `Ctrl+Alt+V` (GNOME custom shortcut)

```desktop
[Desktop Entry]
Name=Echo-Node Voice Agent
Exec=echo-node --web
Icon=echo-node
Terminal=false
Type=Application
Categories=Utility;
```

**macOS:**
- `echo-node --web` → same behavior
- macOS app bundle via `platypus` or Automator
- Hotkey: `Option+Space` via Hammerspoon

**Windows:**
- `echo-node --web` → same behavior
- Windows shortcut in Start Menu
- Hotkey: `Ctrl+Alt+V`

### Docker support (optional)

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ...
COPY . /app
RUN pip install -e /app
CMD ["echo-node", "--web"]
```

### CI/CD

```yaml
# .github/workflows/test.yml
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e .
      - run: python -m pytest
      - run: cd gateway && bun install && bun run test
      - run: cd frontend && bun install && bun run test
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `ECHO_LLM_PROVIDER` | LLM provider | `hermes` |
| `ECHO_LLM_MODEL` | Model name | — |
| `ECHO_STT_PROVIDER` | STT provider | `faster-whisper` |
| `ECHO_TTS_PROVIDER` | TTS provider | `kokoro` |
| `GEMINI_API_KEY` | Gemini Live API key | — |
| `OPENAI_API_KEY` | OpenAI Realtime API key | — |
| `ECHO_NODE_CONFIG` | Config path | `config.yaml` |

## Exit criteria

- [x] `echo-node --web` launches gateway + opens browser with working frontend
- [x] `echo-node --tui` launches gateway + TUI
- [ ] `echo-node --voice` launches legacy voice mode
- [ ] `echo-node --dashboard` launches latency dashboard
- [x] Setup script installs everything with one command
- [x] Desktop icon launches web mode
- [ ] Hotkey works on Linux (GNOME)
- [x] All environment variables override config
