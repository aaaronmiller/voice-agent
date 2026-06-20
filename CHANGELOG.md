# Changelog

## [Unreleased]

### Added
- Added speech formatting module (`echo_node/speech_format.py`) — tables become summaries, code blocks become descriptions, replies capped at configurable sentence limit (default 4).
- Added keyboard hotkey system with Escape key toggle (Linux /dev/input, macOS pynput) and terminal Enter trigger, all non-blocking threaded.
- Added native Hermes integration — direct API calls to `:8642` with `"ask hermes ..."` voice command bypasses the router.
- Added native Pi agent integration — subprocess execution with `"ask pi ..."` voice command.
- Added `.env` file support for API keys — no more hardcoded keys in config.yaml.
- Added `.env.example` template with all supported key variables.
- Added `echo_node/__init__.py` package marker.
- Added `speech_format` config section with `max_sentences` and `verbose` settings.
- Added `hermes` and `pi_agent` config sections for native integrations.
- Added voice commands: `"be verbose"` / `"be concise"` to toggle reply length at runtime.
- Added a lean local voice assistant MVP (v1, now archived).
- Added Echo-Node v2 with Kokoro ONNX TTS, Silero VAD barge-in, OpenWakeWord `hey_rhasspy`, and WSL2/Windows install scripts.
- Added v2 configuration docs, Kokoro voice audition tooling, custom wake-word sample recording, terminal Enter hotkey triggering, and an Echo-Node installation/configuration skill.
- Added Fedora 43/PipeWire install support, Hermes API-server integration, Odysseus `/api/v1/chat` integration, and a grounded council review document.
- Added Fedora/GNOME and Windows hotkey launch installers for Echo-Node v2.
- Added MIT license, deployment guide, ASCII project title, and a terminal configuration/deployment wizard.
- Added optional ONNX Runtime GPU setup for Parakeet STT and timing logs for local latency profiling.
- Added wake-word chooser tooling for official OpenWakeWord models and custom ONNX wake-word files.
- Added startup prewarm for STT/TTS plus optional backend warmup and Ollama keep-alive support.
- Added an animated avatar subsystem (`v2/avatar/`) with a PyQt6 sidecar window, Rhubarb Lip Sync (vendored 1.14.0), and 5 preprocessed characters.
- Added `v2/tools/avatar_smoke.py` for end-to-end avatar pipeline verification.
- Added `v2/docs/avatar.md` covering enable/disable, character selection, and viseme mapping.

### Changed
- Removed bundled Electron/compiled JS files from repo root (index-CAI0ttRM.js, ipcHandlers.js, etc.).
- Removed abandoned `gateway/` directory, `.agent/`, `.specify/`, `.checkpoints/`, `.ruff_cache/`.
- Moved v1 code to `archive/v1/`, design docs to `docs/`.
- Deduplicated and renamed sprite images in `sprites/`.
- Rewrote root `README.md` to be concise and accurate.
- Fixed SmartRouter cost tracking — persistent across calls instead of new tracker per route.
- Fixed API key exposure — removed hardcoded OpenRouter key from config.yaml.
- Updated `test.sh` to match current stack (faster-whisper + dots.tts) with 22 checks.
- Avatar preload runs asynchronously — speech starts immediately while Rhubarb analyzes in background.
- Removed `llm_agent` config section in favor of `hermes` and `pi_agent` native sections.
- Changed Parakeet STT provider default back to CPU after local RTX 4050 benchmarking.
- Updated v2 setup to accept any Python 3.11+ interpreter.
- Replaced stale Hermes WebSocket integration notes with Hermes OpenAI-compatible API-server routing.

### Fixed
- Fixed code block regex in speech formatter (was failing on ``` delimiters).
- Fixed SmartRouter creating new CostTracker per call — session cost now accumulates correctly.
