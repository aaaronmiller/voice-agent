# Hermes Agent Integration Guide

**Purpose**: Connect Echo-Node as a voice channel for Hermes Agent.

---

## Overview

Hermes Agent integration allows you to:
- Use Echo-Node as voice input/output for Hermes Agent
- Control Echo-Node via Hermes commands
- Receive transcriptions in Hermes workflows

---

## Prerequisites

1. **Hermes Agent**: Installed and running
2. **Echo-Node**: Configured and running
3. **WebSocket**: Both must be able to connect to the same network

---

## Configuration

### Step 1: Enable Hermes in config.yaml

```yaml
integrations:
  hermes:
    enabled: true
    url: "ws://localhost:8765"  # Hermes WebSocket URL
    channel_name: "echo-node-voice"
```

### Step 2: Start Hermes Agent

```bash
hermes agent start
```

### Step 3: Start Echo-Node

```bash
# Start gateway
cd gateway && bun run src/index.ts

# Start worker (separate terminal)
cd worker && python main.py
```

---

## Usage

### Voice Commands to Hermes

When Hermes integration is enabled:
1. Speak to Echo-Node (wake word or hotkey)
2. Your speech is transcribed
3. Transcription is sent to Hermes Agent
4. Hermes processes and responds
5. Response is spoken by Echo-Node

### Commands from Hermes

Hermes can send these commands to Echo-Node:
- `speak`: Make Echo-Node speak text
- `change_personality`: Switch personality
- `get_status`: Query current state

Example Hermes workflow:
```yaml
workflows:
  voice_query:
    steps:
      - await: voice_input
        channel: echo-node-voice
      - call: llm.chat
        prompt: "{{voice_input}}"
      - speak: "{{llm.response}}"
```

---

## Channel Registration

Echo-Node registers a bidirectional voice channel with Hermes:

| Property | Value |
|----------|-------|
| Channel name | `echo-node-voice` (configurable) |
| Direction | Bidirectional |
| Sample rate | 16000 Hz |
| Channels | 1 (mono) |
| Encoding | PCM 16-bit |

---

## Events

Echo-Node sends these events to Hermes:

| Event | Payload |
|-------|---------|
| `transcript` | `{text, is_final, channel}` |
| `state_change` | `{from, to, channel}` |
| `error` | `{message, code, channel}` |

---

## Troubleshooting

### "Failed to connect to Hermes"

- Check Hermes is running: `hermes agent status`
- Verify URL in config matches Hermes WebSocket port
- Check firewall allows localhost connections

### "Channel registration failed"

- Ensure Hermes is accepting new channel registrations
- Check Hermes logs for errors

### "No audio in Hermes"

- Verify microphone permissions
- Check audio device settings in config.yaml

---

## Disabling Integration

To disable Hermes integration:

```yaml
integrations:
  hermes:
    enabled: false
```

Then restart Echo-Node.
