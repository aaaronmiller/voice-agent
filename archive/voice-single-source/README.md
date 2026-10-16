# Voice harness status

This directory holds the Hermes voice configuration and records the verified OMP and Muse states. The harnesses do not all use one common voice engine or config format.

## Conversational voice

### OMP

OMP has the best native terminal voice path on this machine.

1. Start `omp`.
2. Enter `/live` or press `Ctrl+L`.
3. Speak normally. You can interrupt a reply by speaking.
4. Press `Space` to mute. Press `Esc` to end the voice session.

This is the Codex-authenticated GPT-Live interface. It is different from hold-Space dictation. `Alt+V` is the Windows-safe image-paste fallback, not voice.

Verified on WSL2 on 2026-08-15:

- `/live` reached the listening state through WSLg.
- The native microphone capture opened without an error.
- Local Parakeet STT and Kokoro TTS passed a closed-loop test.
- Normal-turn `speech`, `speechgen`, and `stt` are disabled, so OMP does not
  speak every response. This does not disable the separate `/live` engine.

OMP uses its live config at `/home/cheta/.omp/agent/config.yml`. `omp-config.ini` is a reference snapshot and is not the live OMP config.

### Hermes

Hermes has native continuous voice, streaming spoken replies, full-duplex barge-in, and a local wake word.

1. Start `hermes` or `hermes --tui`.
2. Say `Hey Hermes`.
3. Speak the request after the wake trigger. Recording restarts after each reply.
4. Say `stop` by itself to end the voice conversation.

You can also enter `/voice on` and press `Ctrl+B` once to start the same continuous loop without the wake word. Enter `/wake status` to inspect the listener.

Verified on WSL2 on 2026-08-15:

- Local faster-whisper STT is enabled with the `small` model.
- Edge TTS is enabled with `en-US-AriaNeural`.
- `voice.auto_tts` and `voice.barge_in` are enabled.
- Voice turns allow 120 seconds and end after 1.2 seconds of silence.
- The local openWakeWord model loaded, opened the default WSL2 microphone, remained armed, and stopped cleanly.

The live Hermes config is the symlink `/home/cheta/.hermes/config.yaml` to `/home/cheta/code/voice-single-source/hermes-config.yaml`.

## Push-to-talk and dictation

Muse `0.1.0-R708.1` exposes tap-to-talk with `Alt+V`, but its current static Linux binary cannot initialize a microphone backend on this WSL2 installation. The failure occurs before audio capture: `initialize microphone backend failed: no backend`. The internal duplex ASR is healthy when Muse receives synthetic or WAV input, so the blocked layer is native microphone capture, not authentication or ASR.

The `voice` object previously stored in `/home/cheta/.config/muse/settings.json` was removed because this Muse build does not recognize the proposed `sttProvider` or `ttsProvider` keys. `muse-wrapper.sh` now pins the WSLg Pulse server only. It no longer applies an ineffective `LD_PRELOAD` WSL shim.

Muse remains dictation-only even on a supported microphone backend. It does not provide spoken replies, continuous listening, wake-word activation, or barge-in. Use OMP `/live` or Hermes for those modes. A custom WSLg-to-WAV bridge is possible through Muse's supported test input lane, but it is intentionally not installed as a native fix.

Claude Code, Qwen Code, Gemini CLI, Kilo, and GitHub Copilot offer dictation or transcription features. These are not enabled here because the existing Windows-wide OpenWhisper setup already supplies that capability.

See `/home/cheta/code/voice-single-source/harness-voice-audit.md` for the full matrix and `/home/cheta/code/voice-single-source/research-sources.md` for the research record.

## Audio ownership

Do not keep OMP `/live` and the Hermes wake listener active at the same time. Both need the WSLg microphone. End one voice surface before starting the other.
