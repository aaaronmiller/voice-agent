---
name: echo-node-voice-assistant
description: ALWAYS invoke when the user asks to install, configure, tune, troubleshoot, choose voices, set wake words, train wake words, route backend providers, or adjust silence detection for Echo-Node voice assistant.
---

# Echo-Node Voice Assistant

Use this skill to install and configure the local Echo-Node voice assistant in
this repository. Prefer v2 unless the user explicitly asks for the root v1 MVP.

## Operating Rules

- State the terminal target before commands: WSL/bash, PowerShell, or PowerShell
  Admin.
- Do not invent file paths, model names, voices, device names, or command output.
- Read the existing `config.yaml` before changing it.
- Ask before deleting files or replacing user-edited configs.
- After meaningful changes, update `CHANGELOG.md`.

## Install

For WSL2 with WSLg audio:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
./install-wsl2
```

For native Windows:

```powershell
cd path\to\voice-agent\v2
.\install-windows.ps1
```

If Python 3.11 is missing on Windows and the user agrees:

```powershell
.\install-windows.ps1 -InstallPython
```

Validate with:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
./test.sh
```

## Configure Backend

Edit `v2/config.yaml`.

Ollama:

```yaml
llm:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: qwen3:4b
```

OpenAI-compatible:

```yaml
llm:
  provider: openai-compatible
  base_url: http://127.0.0.1:8080/v1
  api_key: sk-local
  model: local-model-name
```

Hermes Agent:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
HERMES_API_KEY=sk-local-hermes ./integrate-hermes
```

Odysseus:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
ODYSSEUS_API_TOKEN=ody_real_chat_scoped_token ./integrate-odysseus
```

If `llm.model` is empty, Echo-Node still runs wake word, STT, local commands,
and TTS without calling a backend model.

## Choose TTS Voices

List installed Kokoro voices:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
.venv/bin/python tools/choose_voice.py --list
```

Play three voices and ask the user to choose:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
.venv/bin/python tools/choose_voice.py --voices af_heart af_bella am_puck
```

If the user dislikes all three, repeat with three different names from
`--list`. Set a known voice directly with:

```bash
.venv/bin/python tools/choose_voice.py --set af_bella
```

On Windows, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`.

To obtain newer voices, use the current Kokoro ONNX model release or Kokoro
voices list. Place the real downloaded voice bundle under `v2/models/kokoro/`,
update `tts.voices_path` if the filename changed, and run `--list` before
auditioning names.

## Wake Word

Default:

```yaml
wake_word:
  enabled: true
  sensitivity: 0.55
  pretrained:
    - hey_jarvis
  model_paths: []
```

Custom ONNX model:

```yaml
wake_word:
  enabled: true
  sensitivity: 0.55
  pretrained: []
  model_paths:
    - models/wakewords/hey-codex.onnx
```

Record real positive samples:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
.venv/bin/python tools/record_wakeword_samples.py "hey codex" --count 20 --seconds 2
```

Then use OpenWakeWord's official training workflow to produce an ONNX model.
Copy the resulting model into `v2/models/wakewords/` and update
`wake_word.model_paths`.

## Silence And Interruption Tuning

Tune VAD in `v2/config.yaml`:

```yaml
vad:
  speech_threshold: 0.55
  silence_seconds: 0.85
  max_record_seconds: 16
  min_record_seconds: 0.35
  rms_floor: 140
```

Rules:

- Increase `vad.silence_seconds` if turns end too early.
- Decrease `vad.silence_seconds` if responses start too late.
- Increase `vad.speech_threshold` or `vad.rms_floor` if noise triggers speech.
- Decrease `vad.speech_threshold` if quiet speech is missed.

Barge-in:

```yaml
barge_in:
  enabled: true
  min_speech_seconds: 0.28
  min_playback_age_seconds: 0.35
```

Increase `barge_in.min_speech_seconds` for fewer accidental interruptions.
Decrease it for faster interruption.

## Hotkeys

Manual terminal trigger:

```yaml
hotkeys:
  enabled: true
  terminal_enter: true
```

Run with:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
./run.sh
```

Press Enter in the terminal to start a turn without saying the wake phrase.
