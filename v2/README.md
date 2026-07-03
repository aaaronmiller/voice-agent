# Echo-Node v2

Lean local voice assistant package for Surface Laptop Studio 2 / RTX 4050-class
hardware.

## Stack

- Local audio input: `arecord -D default`
- Local audio output: `aplay -D default`
- Wake word: OpenWakeWord with local ONNX models
- VAD/silence/barge-in: Silero VAD from OpenWakeWord resources
- STT: Parakeet TDT 0.6B v2 through `onnx-asr`
- TTS: Kokoro ONNX, with espeak-ng fallback
- Backend: Ollama or any OpenAI-compatible `/v1/chat/completions` endpoint

## Setup

Wizard:

```bash
./wizard
```

Linux/WSL already configured:

```bash
./setup.sh
./test.sh
```

Windows 11 WSL2 with WSLg audio:

```bash
./install-wsl2
```

That installer installs ALSA/PulseAudio bridge packages, sets
`PULSE_SERVER=unix:/mnt/wslg/PulseServer` when available, writes an ALSA
PulseAudio default in `~/.asoundrc` after backing up an existing non-Pulse file,
configures v2 for `arecord`/`aplay`, and runs real capture/playback probes.

Native Windows:

```powershell
.\install-windows.ps1
```

If Python 3.11 is missing and you want the script to install it through winget:

```powershell
.\install-windows.ps1 -InstallPython
```

The Windows installer configures v2 for the `sounddevice` backend, which uses
PortAudio/WASAPI instead of Linux `arecord`/`aplay`.

Native Fedora 43 / GNOME / PipeWire:

```bash
./install-fedora
```

That installer uses Fedora packages for `pipewire-alsa`, `pipewire-pulseaudio`,
`wireplumber`, ALSA tools, espeak-ng, and Python, then runs the same v2 tests and
audio probes.

Optional NVIDIA STT acceleration:

```bash
./install-gpu
```

This installs ONNX Runtime GPU plus CUDA 12/cuDNN runtime wheels into the venv.
`./run.sh` automatically exports the venv NVIDIA library paths.

Fedora/GNOME launch hotkey:

```bash
./install-hotkey-fedora
```

Default binding is `Ctrl+Alt+V`. Override it with `ECHO_NODE_HOTKEY`.

Native Windows launch hotkey after `install-windows.ps1`:

```powershell
.\install-hotkey-windows.ps1
```

Default binding is `Ctrl+Alt+V`.

## Run

```bash
./run.sh
```

On native Windows after `install-windows.ps1`:

```powershell
.\.venv\Scripts\python.exe assistant_v2.py
```

Default wake phrase is `hey rhasspy`, using OpenWakeWord's official local ONNX
model. Change `wake_word.pretrained` or `wake_word.model_paths` in `config.yaml`
to use a different real ONNX wake model.

Press Enter in the terminal to trigger a turn manually without the wake phrase.
Set `hotkeys.enabled: false` in `config.yaml` to disable that behavior.

## Configure

See [docs/configuration.md](docs/configuration.md) for the exact config keys for
backend URL, model name, wake-word model file, TTS voice, silence detection,
barge-in, hotkeys, WSL2 audio, Windows audio, voice audition, and custom
wake-word sample recording.

### Provider-agnostic (env or config)

The LLM, STT, and TTS backends are all selectable in `config.yaml` **or** via env
vars (env wins over the file — no config edit needed to swap):

| Env var | Overrides | Example |
|---|---|---|
| `ECHO_LLM_PROVIDER` / `ECHO_LLM_MODEL` / `ECHO_LLM_BASE_URL` / `ECHO_LLM_API_KEY` | `llm.*` | `ECHO_LLM_PROVIDER=hermes ECHO_LLM_BASE_URL=http://127.0.0.1:8642/v1 ECHO_LLM_MODEL=hermes-agent` |
| `ECHO_STT_PROVIDER` / `ECHO_STT_MODEL` | `stt.*` | `ECHO_STT_PROVIDER=faster-whisper ECHO_STT_MODEL=small` |
| `ECHO_TTS_PROVIDER` / `ECHO_TTS_VOICE` | `tts.*` | `ECHO_TTS_PROVIDER=kokoro ECHO_TTS_VOICE=af_sky` |
| `ECHO_WAKE_PHRASE` | `assistant.wake_phrase` | `ECHO_WAKE_PHRASE=computer` |

LLM providers: `hermes`, `openai-compatible`, `ollama`, `odysseus`. STT: `faster-whisper`,
`onnx-asr`/`parakeet`. TTS: `kokoro`, `dots`, `espeak-ng`. Put secrets in `v2/.env`
(gitignored). Applied overrides are printed at startup as `[config] env overrides applied: …`.

See [docs/avatar.md](docs/avatar.md) for the optional floating animated
avatar (PyQt6 sidecar with Rhubarb lip-sync) and how to add new sprite sheets.

Audition Kokoro voices:

```bash
.venv/bin/python tools/choose_voice.py --voices af_heart af_bella am_puck
```

Record real custom wake-word samples:

```bash
.venv/bin/python tools/record_wakeword_samples.py "hey codex" --count 20 --seconds 2
```

## Barge-In

While the assistant is speaking, v2 keeps reading the microphone. If Silero VAD
sees sustained user speech after the playback guard window, the current `aplay`
process is terminated, queued speech is dropped, and the interruption is recorded
as a new user turn.

## Backend Routing

Use Ollama:

```yaml
llm:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: qwen3:4b
```

Use any OpenAI-compatible server:

```yaml
llm:
  provider: openai-compatible
  base_url: http://127.0.0.1:8080/v1
  api_key: sk-local
  model: local-model-name
```

Use Hermes Agent:

```bash
HERMES_API_KEY=sk-local-hermes ./integrate-hermes
```

Use Odysseus:

```bash
ODYSSEUS_API_TOKEN=ody_your_real_chat_scoped_token ./integrate-odysseus
```

If no backend model is available, v2 still runs locally and speaks back what it
heard, plus built-in `time`, `date`, and `repeat ...` commands.
