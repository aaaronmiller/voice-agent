---
title: Harness voice capability audit
date: 2026-08-15
environment: WSL2, zsh, WezTerm, WSLg audio
---

# Harness voice capability audit

## Decision

Use OMP `/live` for a direct terminal conversation with the active coding agent. Use Hermes for `Hey Hermes`, continuous voice, local wake detection, and full-duplex interruption. Do not add dictation-only features because Windows OpenWhisper already provides them.

## Verified installed harnesses

| Harness | Installed state | Native voice state | Action |
|---|---:|---|---|
| OMP 17.3.3 | Installed | Full duplex GPT-Live, spoken replies, interruption, active-agent task routing | Repaired and verified |
| Hermes 0.20.0 | Installed | Continuous voice, streaming TTS, barge-in, local `Hey Hermes` wake word | Enabled and verified |
| Muse 0.1.0-R708.1 | Installed | Tap-to-talk UI is present, but the static Linux build cannot initialize a microphone backend on WSL2 | Blocked in the product binary; false local provider config removed |
| Claude Code 2.1.220 | Installed | Server-side voice dictation only | Left unchanged |
| Qwen Code 0.14.5 | Installed | Voice dictation only; requires a configured voice model | Left unchanged |
| Gemini CLI 0.38.2 | Installed | Experimental dictation only; Gemini Live or local Whisper transcription backend | Left unchanged |
| Codex CLI 0.146.0 | Installed | No native CLI voice command in current CLI docs or local command surface | Left unchanged |
| Kilo 7.2.25 | Installed | Kilo Gateway voice transcription only | Left unchanged |
| OpenCode 1.3.17 | Installed | No native conversational voice in current command surface or official docs | Left unchanged |
| Cline 2.17.0 | Installed | No native conversational voice in the installed CLI surface | Left unchanged |

`Alt+V` in OMP is image paste on Windows terminals. It is not a second voice engine. OMP realtime voice is `/live` or `Ctrl+L`. Claude Code uses `/voice` for dictation. Hermes uses `/voice on` for its continuous loop and `/wake on` for the wake listener.

## Listed harnesses not available as local CLI commands

The source registry also lists OpenClaw, GitHub Copilot, Continue, Zed, Windsurf, Cursor, Letta Code, Goose, Roo Code, Trae, Augment Code, and a universal shared-agent directory. Some config directories exist, but no matching executable was available in this WSL2 shell during the audit. No runtime change was made to them.

Current public documentation shows GitHub Copilot CLI and the Copilot app have local voice dictation. It is still transcription, not a spoken full-duplex agent conversation. The other missing IDE harnesses can continue to use Windows OpenWhisper.

## Separate useful surface

ChatGPT desktop Voice is not Codex CLI voice. It is a GPT-Live conversation in the desktop app. It supports interruption and can start, inspect, and steer Codex tasks. This is useful when the terminal is not required, but it does not add `/voice` to the `codex` CLI.

## Verification evidence

- WSLg default source: `RDPSource`; default sink: `RDPSink`.
- OMP microphone test: 73 frames and 58,400 samples captured without error.
- OMP local audio loop: Kokoro audio transcribed by Parakeet as `Open my project files.`
- OMP playback: user confirmed the spoken playback test.
- OMP live mode: reached `listening`, accepted mute/end controls, and exited cleanly.
- OMP normal-turn `speech`, `speechgen`, and `stt` are disabled; no TTS worker
  remains active outside `/live`.
- Hermes requirement check: audio capture, local STT, and WSL PulseAudio/PipeWire all available.
- Hermes wake test: local model dependencies loaded; listener opened the default ALSA/Pulse bridge input with 32 input channels, remained running for eight seconds, then released cleanly.
- Hermes focused tests: 62 passed, 3 skipped, 1 failed. The one failure expects WSL to be unavailable when `PULSE_SERVER` is unset, but this machine has the reachable standard `/mnt/wslg/PulseServer` socket. The live microphone probe is the decisive environment check.
- Muse direct microphone test: `Alt+V` fails immediately with `initialize microphone backend failed: no backend`; retained session events record `failure_class=engine` after 0 to 19 ms.
- Muse ASR isolation test: the built-in synthetic lane produced `Add tests for the voice dictation flow.` and the supported WAV-input lane sent audio to duplex ASR. This isolates the defect to native capture.
- Muse build check: `0.1.0-R708.1` is the current stable release. Its Linux executable is statically linked and maps no ALSA, PulseAudio, JACK, or sndio library. The earlier `LD_PRELOAD` shim cannot modify it.

## Low-priority extension path

Do not build one adapter per harness. If a common wrapper becomes useful later, make one voice front end and route text turns to ACP-capable agents. OMP and Hermes both expose ACP servers. ACP carries agent sessions and text/tool updates; the voice front end must own audio, VAD, interruption, echo control, and wake detection.

Gemini Live is the strongest optional research path for affective audio and native interruption. OpenAI Realtime is the strongest direct alternative for server or semantic VAD. Emotion output must be advisory only because speech-emotion classification is uncertain and context-dependent.
