# Echo-Node Configuration

This file maps the user-facing choices to the exact keys in `config.yaml`.

## Echo-Node v2

Edit `v2/config.yaml`.

### Backend Provider URL And Model

For Ollama:

```yaml
llm:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: qwen3:4b
```

For an OpenAI-compatible local or remote server:

```yaml
llm:
  provider: openai-compatible
  base_url: http://127.0.0.1:8080/v1
  api_key: sk-local
  model: local-model-name
```

For Hermes Agent's API server:

```yaml
llm:
  provider: hermes
  base_url: http://127.0.0.1:8642/v1
  api_key: sk-local-hermes
  model: hermes-agent
```

Configure it with:

```bash
cd v2
HERMES_API_KEY=sk-local-hermes ./integrate-hermes
```

For Odysseus:

```yaml
llm:
  provider: odysseus
  base_url: http://127.0.0.1:7000
  api_key: ody_your_real_chat_scoped_token
  model: ""
```

Configure it with:

```bash
cd v2
ODYSSEUS_API_TOKEN=ody_your_real_chat_scoped_token ./integrate-odysseus
```

Set `llm.model` to an empty string to run without an LLM backend. In that mode
the assistant still wakes, records, transcribes, speaks local command responses,
and echoes unhandled text.

### Wake Word File

The default uses OpenWakeWord's installed `hey_rhasspy` ONNX model:

```yaml
wake_word:
  enabled: true
  sensitivity: 0.55
  pretrained:
    - hey_rhasspy
  model_paths: []
```

To use a custom trained ONNX wake-word model, clear `pretrained` and point
`model_paths` at the real model file:

```yaml
wake_word:
  enabled: true
  sensitivity: 0.55
  pretrained: []
  model_paths:
    - models/wakewords/hey-codex.onnx
```

Higher `sensitivity` wakes more easily and can false-trigger more often. Lower
`sensitivity` reduces false wakes but may miss quiet wake phrases.

List the official pretrained models included by OpenWakeWord:

```bash
cd v2
.venv/bin/python tools/choose_wakeword.py --list
```

Set one of the official pretrained models:

```bash
cd v2
.venv/bin/python tools/choose_wakeword.py --set hey_mycroft
```

The official pretrained choices exposed by the installed OpenWakeWord package
are `alexa`, `hey_jarvis`, `hey_mycroft`, `hey_rhasspy`, `timer`, and
`weather`. Other phrases must be recorded and trained into a custom ONNX model
before they can work as wake words.

### TTS Voice

Kokoro voice selection is controlled by `tts.voice`:

```yaml
tts:
  provider: kokoro
  voice: af_heart
  speed: 1.0
  model_path: models/kokoro/kokoro-v1.0.onnx
  voices_path: models/kokoro/voices-v1.0.bin
```

List installed voices:

```bash
cd v2
.venv/bin/python tools/choose_voice.py --list
```

Audition three voices, then choose one interactively:

```bash
cd v2
.venv/bin/python tools/choose_voice.py --voices af_heart af_bella am_puck
```

Set a voice directly:

```bash
cd v2
.venv/bin/python tools/choose_voice.py --set af_bella
```

On native Windows, use:

```powershell
cd v2
.\.venv\Scripts\python.exe tools\choose_voice.py --voices af_heart af_bella am_puck
```

To obtain newer Kokoro voices, download the current Kokoro ONNX voice bundle or
voice files from the Kokoro ONNX model release / Kokoro voices list, replace or
add the voice bundle under `v2/models/kokoro/`, update `tts.voices_path` if the
filename changed, then run `tools/choose_voice.py --list` again. Do not type a
voice name by guesswork; list the voices from the installed bundle first.

### Silence Detection And Barge-In

The VAD section decides when a user turn starts and ends:

```yaml
vad:
  speech_threshold: 0.55
  silence_seconds: 0.85
  max_record_seconds: 16
  min_record_seconds: 0.35
  rms_floor: 140
```

Useful tuning:

- Increase `vad.silence_seconds` if the assistant cuts you off between phrases.
- Decrease `vad.silence_seconds` if it waits too long after you finish.
- Increase `vad.speech_threshold` or `vad.rms_floor` if keyboard noise counts as speech.
- Decrease `vad.speech_threshold` if quiet speech is missed.

Barge-in controls interruption while TTS is playing:

```yaml
barge_in:
  enabled: true
  min_speech_seconds: 0.28
  min_playback_age_seconds: 0.35
```

Increase `barge_in.min_speech_seconds` when short noises interrupt speech.
Decrease it when real interruptions feel sluggish.

### STT CPU/GPU Provider

Parakeet uses `onnx-asr`, which routes through ONNX Runtime. CPU is the default
because the current Parakeet ONNX graph can be slower on CUDA on RTX 4050-class
laptop GPUs due to GPU/CPU copy overhead.

```yaml
stt:
  provider: onnx-asr
  model_name: nemo-parakeet-tdt-0.6b-v2
  quantization: int8
  providers:
    - CPUExecutionProvider
```

Leaving `providers` empty also uses CPU:

```yaml
stt:
  providers: []
```

Try CUDA with CPU fallback after running `./install-gpu`:

```yaml
stt:
  providers:
    - CUDAExecutionProvider
    - CPUExecutionProvider
```

Keep the setting that benchmarks faster on your machine. On the Fedora RTX 4050
test host, CPU transcribed the bundled Parakeet sample in about `1.14s`; CUDA
loaded successfully but took about `1.94s` for the same sample.

### Startup Prewarm

Set these options so `[ready]` means the local speech models are already hot in
memory:

```yaml
performance:
  preload_stt: true
  warm_tts: true
  warm_backend: false
```

`preload_stt` loads Parakeet before the assistant accepts the wake word.
`warm_tts` runs one silent Kokoro synthesis to remove first-speech setup cost.
`warm_backend` sends a one-token warmup request to Ollama or an
OpenAI-compatible backend; leave it off for metered remote APIs unless you want
to spend one tiny request at startup.

For Ollama, keep the model resident between turns:

```yaml
llm:
  keep_alive: 30m
```

### Hotkeys

The terminal Enter key can trigger a manual turn without the wake word:

```yaml
hotkeys:
  enabled: true
  terminal_enter: true
```

Set `hotkeys.enabled: false` to disable manual triggering.

### Custom Wake-Word Recording

Record positive samples:

```bash
cd v2
.venv/bin/python tools/record_wakeword_samples.py "hey codex" --count 20 --seconds 2
```

On native Windows:

```powershell
cd v2
.\.venv\Scripts\python.exe tools\record_wakeword_samples.py "hey codex" --count 20 --seconds 2
```

This records real WAV samples under `v2/wakeword_samples/`. Training is a
separate step: use OpenWakeWord's official training notebook or trainer to
produce an ONNX model, copy it into `v2/models/wakewords/`, then configure
`wake_word.model_paths` as shown above.

## Echo-Node v1

Edit root `config.yaml`.

Backend URL and model:

```yaml
llm:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: llama3.2:3b
```

Wake-word model files:

```yaml
wake_word:
  enabled: true
  sensitivity: 0.5
  model_paths:
    - /path/to/real/wakeword.onnx
```

TTS voice:

```yaml
tts:
  provider: espeak-ng
  voice: en-us
  speed: 165
  pitch: 50
```

Root v1 uses RMS-based silence fields in `audio`:

```yaml
audio:
  silence_rms_threshold: 350
  silence_seconds: 1.0
  max_record_seconds: 14
```

Use v2 for Kokoro voices, Silero VAD, barge-in, WSL2 setup, and Windows native
audio.
