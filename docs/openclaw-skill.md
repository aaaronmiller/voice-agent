# OpenClaw Skill Configuration

**Purpose**: Configure Echo-Node as an OpenClaw skill for multi-agent workflows.

---

## Overview

OpenClaw integration creates a skill definition that allows other agents to:
- Invoke Echo-Node voice commands
- Change personality presets
- Query conversation history
- Get status information

---

## Prerequisites

1. **OpenClaw**: Installed at `~/.openclaw/`
2. **Echo-Node**: Configured and running

---

## Configuration

### Step 1: Enable OpenClaw in config.yaml

```yaml
integrations:
  openclaw:
    enabled: true
    skill_dir: "~/.openclaw/skills/echo-node"
```

### Step 2: Start Echo-Node

```bash
cd gateway && bun run src/index.ts
```

On startup, Echo-Node will create:
- `~/.openclaw/skills/echo-node/skill.yaml`
- `~/.openclaw/skills/echo-node/README.md`

---

## Skill Actions

The Echo-Node skill provides these actions:

### speak

Make Echo-Node speak the given text.

```yaml
action: speak
parameters:
  text: "Hello, world!"
  voice: "af_heart"  # Optional
```

### change_personality

Change the active personality preset.

```yaml
action: change_personality
parameters:
  personality: "hacker"  # Options: hacker, seductive, butler, drill-sergeant, stoner-philosopher
```

### get_status

Get current Echo-Node status.

```yaml
action: get_status
parameters: {}
```

Returns:
```json
{
  "state": "dormant",
  "personality": "hacker",
  "conversation_turns": 0,
  "pipeline_mode": "local"
}
```

### get_conversation_history

Get recent conversation turns.

```yaml
action: get_conversation_history
parameters:
  limit: 5  # Optional, default: 15
```

---

## Triggers

The skill responds to these triggers:

| Trigger | Description |
|---------|-------------|
| `voice_command` | Voice input detected |
| `wake_word` | Wake word detected |
| `text_command` | Text command from agent |

---

## Usage in OpenClaw Workflows

Example workflow using Echo-Node:

```yaml
name: voice-assistant
description: Voice-controlled AI assistant

triggers:
  - voice_command

steps:
  - echo_node:
      action: get_status
  - llm:
      prompt: "Respond to: {{voice_command}}"
  - echo_node:
      action: speak
      text: "{{llm.response}}"
```

---

## Troubleshooting

### "Skill directory not created"

- Check that `~/.openclaw/` exists
- Verify OpenClaw integration is enabled in config
- Check Echo-Node startup logs

### "Actions not working"

- Ensure Echo-Node gateway is running
- Check WebSocket connectivity

---

## Disabling Integration

To disable OpenClaw integration:

```yaml
integrations:
  openclaw:
    enabled: false
```

Then restart Echo-Node. The skill directory will be removed on cleanup.

---

## Manual Skill File

If you need to manually create the skill file:

```yaml
# ~/.openclaw/skills/echo-node/skill.yaml
name: echo-node
version: 1.0.0
description: Voice-controlled AI assistant with personality presets

triggers:
  - voice_command
  - wake_word
  - text_command

actions:
  - name: speak
    description: Make Echo-Node speak the given text
    parameters:
      - name: text
        type: string
        description: Text to speak
        required: true
      - name: voice
        type: string
        description: Voice preset to use
        required: false

  - name: change_personality
    description: Change the active personality preset
    parameters:
      - name: personality
        type: string
        description: Personality name
        required: true

  - name: get_status
    description: Get current Echo-Node status
    parameters: []

  - name: get_conversation_history
    description: Get recent conversation turns
    parameters:
      - name: limit
        type: number
        description: Number of turns to retrieve
        required: false
```
