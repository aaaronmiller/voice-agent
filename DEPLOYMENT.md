# Deployment

Echo-Node v2 is the deployable stack. It keeps runtime state local and ignores
large model files, generated configs, venvs, and recorded audio samples in Git.

## Fast Path

```bash
cd v2
./wizard
```

The wizard can:

- Run platform setup for Fedora, WSL2, or Windows
- Configure the backend provider
- Configure wake-word mode and sensitivity
- Configure Kokoro voice, VAD, barge-in, and hotkeys
- Install launch hotkeys
- Run the test suite
- Launch the assistant

## Platform Installers

Fedora 43 / GNOME / PipeWire:

```bash
cd v2
./install-fedora
```

WSL2 Ubuntu with WSLg audio:

```bash
cd v2
./install-wsl2
```

Native Windows:

```powershell
cd v2
.\install-windows.ps1
```

## Launch Hotkeys

GNOME/Fedora:

```bash
cd v2
./install-hotkey-fedora
```

Default binding: `Ctrl+Alt+V`.

Windows:

```powershell
cd v2
.\install-hotkey-windows.ps1
```

Default binding: `Ctrl+Alt+V`.

## Backend Routing

Ollama:

```yaml
llm:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: qwen3:4b
```

Hermes:

```bash
cd v2
HERMES_API_KEY=sk-local-hermes ./integrate-hermes
```

Odysseus:

```bash
cd v2
ODYSSEUS_API_TOKEN=ody_real_chat_scoped_token ./integrate-odysseus
```

OpenAI-compatible:

```yaml
llm:
  provider: openai-compatible
  base_url: http://127.0.0.1:8080/v1
  api_key: sk-local
  model: local-model-name
```

## Release Hygiene

Before pushing:

```bash
cd v2
./test.sh
```

Git ignores:

- `config.yaml` and `v2/config.yaml`
- `.venv/` and `v2/.venv/`
- model binaries under `models/` and `v2/models/`
- wake-word recordings
- audio outputs and caches
- env files and logs
