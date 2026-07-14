# Gemini Live API Setup for Echo-Node

**Purpose**: Configure Gemini Flash Live API for cloud-based voice conversations.

---

## Overview

Gemini Flash Live API provides real-time bidirectional audio processing:
- **Server-side STT** - Speech recognition handled by Google
- **Server-side LLM** - Gemini processes your input
- **Server-side TTS** - Audio responses streamed back
- **Native VAD** - Voice activity detection built-in
- **Barge-in Support** - Speak while Gemini responds to interrupt

**Latency**: Sub-300ms (server-side processing)

---

## Prerequisites

1. **Google Cloud Account** - Required for API key
2. **Echo-Node** - Installed and working
3. **Internet Connection** - Required for cloud mode

---

## Step 1: Get Gemini API Key

### Option A: Google AI Studio

1. Go to [https://aistudio.google.com](https://aistudio.google.com)
2. Sign in with Google account
3. Click "Get API Key"
4. Copy the key (starts with `AIza...`)

### Option B: Google Cloud Console

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Enable "Generative Language API"
3. Create API credentials
4. Copy the API key

---

## Step 2: Configure Echo-Node

Edit `config.yaml`:

```yaml
# Switch to cloud pipeline mode
pipeline_mode: cloud

llm:
  provider: openai-compat  # Placeholder - cloud mode bypasses local LLM
  model: "gemini-2.0-flash-exp"
  api_key: "YOUR_GEMINI_API_KEY_HERE"  # Required for cloud mode
  base_url: ""  # Not used in cloud mode
```

---

## Step 3: Run in Cloud Mode

```bash
# Terminal 1: Worker (still runs for wake word detection)
cd worker
source .venv/bin/activate
python main.py

# Terminal 2: Gateway (handles Gemini proxy)
cd gateway
bun run src/index.ts

# Terminal 3: Frontend
cd frontend
bun run dev
```

Open http://localhost:5173 and speak - Gemini handles the rest!

---

## How It Works

```
┌─────────────────┐     WebSocket      ┌─────────────────┐
│   Frontend      │◄──────────────────►│    Gateway      │
│   (Svelte 5)    │   JSON + Audio     │   (Bun + Hono)  │
└─────────────────┘                    └────────┬────────┘
                                                │
                                       WebSocket
                                    (JSON + PCM audio)
                                                │
                                       ┌────────▼────────┐
                                       │   Gemini Live   │
                                       │   Flash API     │
                                       │   (Google)      │
                                       └─────────────────┘
```

### Audio Flow

1. **Frontend** captures 16kHz PCM audio via Web Audio API
2. **Gateway** relays audio to Gemini Live API
3. **Gemini** processes audio (STT → LLM → TTS server-side)
4. **Gemini** streams audio response back
5. **Gateway** relays audio to frontend
6. **Frontend** plays audio response

### Barge-in Flow

1. User speaks while Gemini is responding
2. Frontend detects audio input
3. Gateway sends barge-in signal to Gemini
4. Gemini stops current generation
5. Frontend acknowledges barge-in
6. New conversation turn begins

---

## Available Voices

| Voice Name | Description | Gender |
|------------|-------------|--------|
| `Puck` | Friendly, conversational | Male |
| `Charon` | Professional, clear | Male |
| `Kore` | Warm, engaging | Female |
| `Fenrir` | Deep, authoritative | Male |
| `Aoede` | Natural, expressive | Female |

Configure in `config.yaml`:

```yaml
llm:
  model: "gemini-2.0-flash-exp"
  # Voice is set in gateway config
```

---

## Troubleshooting

### "API key is required for cloud mode"

```yaml
llm:
  api_key: "YOUR_KEY_HERE"  # Must be set
```

### "Failed to connect to Gemini API"

1. Verify API key is correct
2. Check internet connection
3. Verify API key has Generative Language API enabled

### "High latency"

- Cloud mode should be sub-300ms
- Check network speed
- Try different Gemini model variant

---

## Cost Estimation

Gemini Flash Live pricing (as of March 2026):

- **Input Audio**: $0.001 per minute
- **Output Audio**: $0.002 per minute
- **Typical session**: ~$0.01-0.05 per hour

Check [Google AI Pricing](https://ai.google.dev/pricing) for current rates.

---

## Next Steps

- [Setup WSL2](setup-wsl2.md) - Audio configuration
- [Setup Fedora](setup-fedora.md) - Native Linux
- [Setup macOS](setup-macos.md) - macOS setup
- [Quickstart](../quickstart.md) - Get started
