```text
  ______     __              _   __          __
 / ____/____/ /_  ____      / | / /___  ____/ /__
/ __/ / ___/ __ \/ __ \    /  |/ / __ \/ __  / _ \
/ /___/ /__/ / / / /_/ /   / /|  / /_/ / /_/ /  __/
/_____/\___/_/ /_/\____/   /_/ |_/\____/\__,_/\___/
```

# Echo-Node Local Voice Assistant

Hands-free local voice assistant. Use `v2/` for the current best build.

Current v2 stack:

- Wake-word activation through OpenWakeWord `hey_jarvis`
- Local STT through Parakeet TDT v2 ONNX (`onnx-asr`)
- Silero VAD silence detection and barge-in
- Local TTS through Kokoro ONNX, with espeak-ng fallback
- Backend routing to Ollama, OpenAI-compatible servers, Hermes, or Odysseus
- WSL2, native Windows, and Fedora install scripts
- Terminal configuration/deployment wizard
- GNOME and Windows launch hotkey installers

The root `local_voice_assistant.py` remains as the smaller v1 MVP:

- Wake-word activation through OpenWakeWord
- Local STT through Parakeet TDT v2 ONNX (`onnx-asr`)
- RMS silence detection for end-of-speech
- Local TTS through `espeak-ng` + `aplay`
- Optional Ollama response generation

The original split-stack `worker/`, `gateway/`, and `frontend/` plan in `specs/`
was not present on disk.

## Current v2 Setup

Wizard:

```bash
cd v2
./wizard
```

Manual setup:

```bash
cd v2
./setup.sh
./test.sh
./run.sh
```

WSL2:

```bash
cd v2
./install-wsl2
```

Fedora 43 / GNOME / PipeWire:

```bash
cd v2
./install-fedora
```

Native Windows:

```powershell
cd v2
.\install-windows.ps1
```

See [v2/README.md](v2/README.md) and
[v2/docs/configuration.md](v2/docs/configuration.md).

Deployment notes live in [DEPLOYMENT.md](DEPLOYMENT.md).

## License

MIT. See [LICENSE](LICENSE).

## v1 Setup

```bash
./setup.sh
```

Setup creates `.venv`, installs Python dependencies, downloads OpenWakeWord
shared feature models, and creates `config.yaml` from `config.example.yaml`.

## v1 Test

```bash
./test.sh
```

The test validates scripts, imports, local wake-word files, and basic tool
availability.

## v1 Run

```bash
./run.sh
```

Default flow:

1. Say the configured wake phrase
2. Wait for the spoken prompt: `Yes?`
3. Speak your request
4. Stop speaking; silence detection submits the audio
5. Parakeet v2 transcribes it
6. The assistant speaks the response

To use a different wake word in v1, put real OpenWakeWord `.onnx` models on
disk and update `wake_word.model_paths` in root `config.yaml`.

## v1 Ollama

Ollama is optional. Built-in responses work for `time`, `date`, and `repeat ...`.
For generative answers, pull a local model and set it in `config.yaml`:

```bash
ollama pull llama3.2:3b
```

```yaml
llm:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: llama3.2:3b
```

If `llm.model` is blank, the assistant uses the first installed Ollama model.
If Ollama has no installed model, it speaks back what it heard.

## v1 Configuration

Important knobs in `config.yaml`:

- `audio.silence_rms_threshold`: raise if background noise triggers recording
- `audio.silence_seconds`: silence duration before submitting speech
- `audio.max_record_seconds`: hard cap per utterance
- `wake_word.sensitivity`: lower is easier to trigger
- `stt.model_name`: defaults to `nemo-parakeet-tdt-0.6b-v2`
- `tts.voice`, `tts.speed`, `tts.pitch`: espeak-ng voice settings

## Verified

- `v2/test.sh` passes.
- Parakeet v2 ONNX transcribed the local sample WAV:
  `Ask not what your country can do for you. Ask what you can do for your country.`
- OpenWakeWord detector initializes successfully with the official `hey_jarvis`
  model in v2.
