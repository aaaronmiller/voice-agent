# Changelog

## [Unreleased]

### Added
- Added a lean local voice assistant MVP using Parakeet STT, OpenWakeWord wake detection, RMS silence detection, Ollama responses, and espeak-ng TTS.
- Added Echo-Node v2 with Kokoro ONNX TTS, Silero VAD barge-in, OpenWakeWord `hey_jarvis`, and WSL2/Windows install scripts.
- Added v2 configuration docs, Kokoro voice audition tooling, custom wake-word sample recording, terminal Enter hotkey triggering, and an Echo-Node installation/configuration skill.
- Added Fedora 43/PipeWire install support, Hermes API-server integration, Odysseus `/api/v1/chat` integration, and a grounded council review document.
- Added Fedora/GNOME and Windows hotkey launch installers for Echo-Node v2.
- Added MIT license, deployment guide, ASCII project title, and a terminal configuration/deployment wizard.
- Added optional ONNX Runtime GPU setup for Parakeet STT and timing logs for local latency profiling.
- Added wake-word chooser tooling for official OpenWakeWord models and custom ONNX wake-word files.
- Added startup prewarm for STT/TTS plus optional backend warmup and Ollama keep-alive support.
- Added an animated avatar subsystem (`v2/avatar/`) with a PyQt6 sidecar window anchored to the bottom-right of the primary screen, Rhubarb Lip Sync (vendored 1.14.0) for viseme extraction, and 5 preprocessed characters (raccoon-hacker, owl-wizard, axolotl-astronaut, axolotl-helmet, raccoon-cyber) sliced from sprite sheets with chroma-keyed backgrounds and a shared per-character bbox so the head stays anchored across viseme swaps.
- Added `v2/tools/avatar_smoke.py` for end-to-end avatar pipeline verification without the mic loop.
- Added `v2/docs/avatar.md` covering enable/disable, character selection, adding new sprite sheets, and the viseme→cell mapping format.

### Changed
- Changed Parakeet STT provider default back to CPU after local RTX 4050 benchmarking showed CUDA was slower for the current ONNX graph.
- Updated v2 setup to accept any Python 3.11+ interpreter instead of requiring the exact `python3.11` command.
- Replaced stale Hermes WebSocket integration notes with Hermes OpenAI-compatible API-server routing.
