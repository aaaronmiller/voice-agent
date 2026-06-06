# Echo-Node Council Review

Date: 2026-06-06

## Grounding

Round inputs were bounded by local source inspection plus web checks:

- Fedora 43 `pipewire-alsa` package exists and provides ALSA PipeWire modules:
  <https://packages.fedoraproject.org/pkgs/pipewire/pipewire-alsa/fedora-43.html>
- Odysseus README documents a self-hosted workspace with Ollama, llama.cpp,
  vLLM, OpenRouter, OpenAI, MCP, memory, and skills:
  <https://github.com/pewdiepie-archdaemon/odysseus/blob/main/README.md>
- Hermes API-server docs and local source expose an OpenAI-compatible API at
  `/v1/chat/completions`, usually under `http://127.0.0.1:8642/v1`.
- Local WSL2 setup already passed real `arecord` and `aplay` probes.
- Local v2 tests passed Wake+VAD, Parakeet sample transcription, and Kokoro WAV
  synthesis before this review.

## Personas

1. Audio Linux operator
2. WSL2 compatibility operator
3. Windows native operator
4. Fedora/GNOME operator
5. Backend routing engineer
6. Wake-word/VAD engineer
7. STT/TTS performance engineer
8. Hermes integration engineer
9. Odysseus integration engineer
10. Security/configuration reviewer

## Round 1 Findings

- Fedora native install was missing. Confidence: high. Action: add
  `v2/install-fedora`.
- `v2/setup.sh` required `python3.11` exactly. Fedora can have newer `python3`.
  Confidence: high. Action: accept any Python 3.11+.
- Hermes integration doc was stale and referred to a gateway/worker WebSocket
  architecture not present in v2. Confidence: high. Action: replace with
  Hermes API-server integration.
- Odysseus has a real `/api/v1/chat` route that is not OpenAI-compatible.
  Confidence: high. Action: add a dedicated `odysseus` provider.
- Odysseus outbound webhooks block private/internal URLs, so using Odysseus to
  call a loopback Echo-Node webhook is a poor fit. Confidence: high. Action:
  make Echo-Node call Odysseus instead.

## Round 2 Findings

- Current `llm.provider` values were too generic for agent platforms. Confidence:
  high. Action: add named `hermes` and `odysseus` providers.
- Fedora/GNOME/PipeWire should use ALSA defaults through `pipewire-alsa` for the
  current `arecord`/`aplay` implementation. Confidence: high. Action:
  `install-fedora` installs `pipewire-alsa`, `pipewire-pulseaudio`, and
  `wireplumber`.
- WSL2 remains best served by the existing WSLg PulseAudio socket bridge.
  Confidence: high. Action: no code change; keep `install-wsl2`.
- Native Windows remains best served by `sounddevice`/WASAPI. Confidence: high.
  Action: no code change; keep `install-windows.ps1`.
- Custom wake-word training is still an external OpenWakeWord workflow.
  Confidence: medium. Action: no local trainer added until a real training
  pipeline is selected and tested.

## Round 3 Decisions

Implemented:

- `v2/install-fedora`
- `v2/integrate-hermes`
- `v2/integrate-odysseus`
- `llm.provider: hermes`
- `llm.provider: odysseus`
- Python 3.11+ interpreter detection in `v2/setup.sh`
- Replaced Hermes docs
- Added Odysseus docs

Deferred:

- A local wake-word trainer. The recorder exists, but training needs the
  OpenWakeWord notebook/trainer path selected and verified on the target
  machine.
- Full-duplex speech-to-speech. Current v2 is cascaded wake/VAD/STT/LLM/TTS with
  barge-in, which is the right fit for Parakeet v2 plus Kokoro on these machines.
- Direct Odysseus UI injection. The token chat route is cleaner and tested by
  local source.

## Residual Risks

- Hermes API-server must be enabled in Hermes config or env before
  `llm.provider: hermes` can answer.
- Odysseus requires a chat-scoped `ody_...` API token.
- Fedora audio depends on PipeWire user services being healthy and the selected
  GNOME microphone being available to ALSA through PipeWire.
- WSL2 audio depends on WSLg exposing `/mnt/wslg/PulseServer`.
