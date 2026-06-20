```text
  ______     __              _   __          __
 / ____/____/ /_  ____      / | / /___  ____/ /__
/ __/ / ___/ __ \/ __ \    /  |/ / __ \/ __  / _ \
/ /___/ /__/ / / / /_/ /   / /|  / /_/ / /_/ /  __/
/_____/\___/_/ /_/\____/   /_/ |_/\____/\__,_/\___/
```

# Echo-Node Local Voice Assistant

Hands-free local voice assistant with wake-word activation, local STT/TTS, and
flexible backend routing. Optimized for Surface Laptop Studio 2 / RTX 4050-class
hardware.

## Stack

- **Wake word**: OpenWakeWord `hey_rhasspy` (ONNX)
- **STT**: Parakeet TDT v2 through `onnx-asr`
- **VAD**: Silero VAD for silence detection and barge-in
- **TTS**: Kokoro ONNX, with espeak-ng fallback
- **Backend**: Ollama, OpenAI-compatible servers, Hermes, or Odysseus

## Quick Start

```bash
cd v2
./wizard
```

Or manually:

```bash
cd v2
./setup.sh
./test.sh
./run.sh
```

## Platform Installers

| Platform | Command |
|---|---|
| Fedora 43 / GNOME / PipeWire | `cd v2 && ./install-fedora` |
| WSL2 Ubuntu with WSLg audio | `cd v2 && ./install-wsl2` |
| Native Windows 11 | `cd v2 && .\install-windows.ps1` |
| macOS ARM | `cd v2 && ./install-macos-arm` |

## Launch Hotkeys

| Platform | Command | Default Binding |
|---|---|---|
| GNOME/Fedora | `./install-hotkey-fedora` | `Ctrl+Alt+V` |
| Windows | `.\install-hotkey-windows.ps1` | `Ctrl+Alt+V` |

## Configuration

See [v2/docs/configuration.md](v2/docs/configuration.md) for backend URL,
model name, wake-word mode, TTS voice, VAD settings, barge-in, and hotkeys.

See [v2/docs/avatar.md](v2/docs/avatar.md) for the optional animated avatar
(PyQt6 sidecar with Rhubarb lip-sync).

## Repository Structure

```
v2/                  # Current best build (active development)
  echo_node/         # Core package (agent profiles, pipeline stubs)
  avatar/            # Animated avatar subsystem
  tools/             # Voice audition, wake-word recording, deploy wizard
  docs/              # Configuration and avatar docs
  assistant_v2.py    # Main entry point
specs/               # Original design specs
docs/                # Setup guides, provider docs, troubleshooting
sprites/             # Avatar sprite sheets (raw source images)
archive/             # Historical v1 code, transcripts, design docs
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md).

## License

MIT. See [LICENSE](LICENSE).
