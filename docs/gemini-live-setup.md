# Gemini Live Setup Guide

**Purpose**: Configure Echo-Node to use Google Gemini Live API for cloud-based voice conversation.

---

## Overview

Cloud mode (`pipeline_mode: cloud`) routes all voice processing through Google's Gemini Live API:
- **STT**: Gemini handles speech recognition
- **LLM**: Gemini generates responses  
- **TTS**: Gemini provides audio output

This bypasses local models, enabling voice conversation on devices without GPU.

---

## Prerequisites

1. **Google AI Studio Account**: https://aistudio.google.com/app/apikey
2. **API Key**: Generated from Google AI Studio
3. **Echo-Node**: Installed per setup guide

---

## Setup

### Step 1: Get API Key

1. Go to https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key (starts with `AIza...`)

### Step 2: Configure Cloud Mode

Edit `config.yaml`:

```yaml
# Enable cloud mode
pipeline_mode: cloud

# LLM provider (required for cloud mode)
llm:
  provider: openai-compat
  model: "gemini-2.0-flash-live-001"
  api_key: "your-google-ai-api-key"
  base_url: "https://generativelanguage.googleapis.com/v1"

# Audio settings (must match Gemini Live requirements)
audio:
  sample_rate: 16000
  channels: 1
```

### Step 3: Verify Configuration

```bash
cd worker
python -c "from config import Config; c = Config(); print(f'Pipeline mode: {c.pipeline_mode}')"
```

Expected output: `Pipeline mode: cloud`

---

## Usage

### Start Echo-Node

```bash
# Terminal mode
cd worker && python main.py
```

In cloud mode:
1. Say wake word ("Yo Gimp") or press hotkey
2. Gateway opens WebSocket to Gemini Live API
3. Your voice streams directly to Gemini
4. Gemini responses stream back to your speakers
5. Say wake word again for new interaction

### Cloud Mode Events

The gateway emits these events in cloud mode:
- `cloud_stream_start`: Gemini Live session started
- `cloud_stream_stop`: Gemini Live session ended  
- `interrupted`: User barge-in detected

---

## Troubleshooting

### "API key is required"

Ensure `llm.api_key` is set in config.yaml with your Google AI API key.

### "Invalid API key format"

Your API key must be a valid Google AI Studio key (30+ characters, alphanumeric with dashes/underscores).

### "Failed to connect to Gemini Live API"

- Check internet connectivity
- Verify API key is valid at https://aistudio.google.com/app/apikey
- Check firewall allows WebSocket connections to `generativelanguage.googleapis.com`

### Audio Not Playing

- Check system volume
- Verify `audio.sample_rate` is 16000 (Gemini Live requirement)
- Check gateway logs for audio chunk errors

### Latency Issues

Cloud mode adds network latency. For lower latency:
- Use local mode with local models
- Ensure stable internet connection
- Consider closer GCP region

---

## Available Voices

Gemini Live supports these voices:
- Kore (default)
- Charon
- Fenrir
- Aoede
- Puck
- Enceladus
- Callirrhoe
- Autonoe
- Killjoy
- Orus

To change voice, no current config option - this is set internally in the adapter.

---

## Available Models

- `gemini-2.0-flash-live-001` (default)
- `gemini-2.5-flash-live-preview-05-20`

---

## Cost

Gemini Live pricing (as of 2026):
- Audio input: $0.016/minute
- Audio output: $0.016/minute

Check https://ai.google.dev/pricing for latest pricing.

---

## Comparison: Local vs Cloud

| Feature | Local | Cloud |
|---------|-------|-------|
| GPU Required | Yes | No |
| Latency | ~500ms | ~300ms + network |
| Privacy | All local | Audio to Google |
| Cost | Electricity only | Per-minute API |
| Offline | Yes | No |
| Custom Models | Yes | No |

---

## Disabling Cloud Mode

To switch back to local mode:

```yaml
pipeline_mode: local
```

Then restart Echo-Node.
