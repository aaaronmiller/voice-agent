# Target architecture: 3-layer split-stack

**Phase:** 1 — Architecture | **Status:** Drafting | **Owner:** Architecture team

## Entry criteria

- [x] Phase 0 audit complete (section 01)

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   Layer 3: Frontend (your choice)                 │
│                                                                  │
│   ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐ │
│   │   Svelte 5 SPA  │  │  Textual TUI    │  │  Voice-only    │ │
│   │   (web frontend)│  │  (terminal)     │  │  (legacy CLI)  │ │
│   └────────┬────────┘  └────────┬────────┘  └───────┬────────┘ │
└────────────┼─────────────────────┼────────────────────┼──────────┘
             │                     │                     │
       ws:// │               ws:// │               ws:// │
    /ws/web  │            /ws/tui  │           /ws/voice │
             │                     │                     │
┌────────────▼─────────────────────▼─────────────────────▼──────────┐
│                    Layer 2: Gateway (Bun + Hono)                   │
│                                                                   │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│   │ Session Mgr  │  │  REST API    │  │  Provider Router     │  │
│   │ (WS hub)     │  │  /api/*      │  │  (directs to LLM)    │  │
│   └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                   │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │  Live-voice providers (TypeScript, direct Gemini/OpenAI)   │  │
│   │  → WebRTC audio straight to cloud API, no Python middle    │  │
│   └────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬────────────────────────────────────────┘
                           │ ws://localhost:9001 (binary audio + JSON)
                           │ (OR legacy pipe: subprocess stdio)
┌──────────────────────────▼────────────────────────────────────────┐
│                    Layer 1: Audio Worker (Python)                   │
│                                                                   │
│   ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│   │ Mic Capture│  │ Wake Word│  │ VAD      │  │ Local STT    │ │
│   │ (arecord/  │  │ (OpenWake│  │ (Silero) │  │ (whisper/    │ │
│   │ sounddevice)│  │  Word)   │  │          │  │  parakeet)   │ │
│   └────────────┘  └──────────┘  └──────────┘  └──────────────┘ │
│                                                                   │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│   │ Local TTS  │  │ Avatar     │  │ Echo       │                │
│   │ (Kokoro/   │  │ (PyQt6/    │  │ Cancellation│               │
│   │  Dots)     │  │  MuseTalk) │  │            │                │
│   └────────────┘  └────────────┘  └────────────┘                │
└──────────────────────────────────────────────────────────────────┘
```

## Key design decisions

### 1. Gateway is the control plane

The gateway (Bun+Hono) is the single source of truth for:
- Session state
- Provider selection
- Configuration
- Health monitoring
- Audio routing (for live-voice providers)

Frontends connect via WebSocket and receive JSON event streams. The gateway relays audio between frontends and providers. The Python worker connects as a **special audio provider**, not as the main loop.

### 2. Live-voice providers bypass Python entirely

Google Gemini Live and OpenAI Realtime handle their own:
- Speech-in (WebRTC mic → cloud API)
- Speech-out (cloud API → WebRTC speaker)
- VAD (built-in)
- Interruption (built-in)

The gateway simply relays WebRTC SDP offers and manages the session. Python is not in the hot path.

### 3. The legacy pipeline becomes one provider

The existing `assistant_v2.py` code runs as a **subprocess** of the gateway, connected via stdio or a local WebSocket. It handles:
- Wake word detection
- Local STT
- LLM routing (to Ollama, Hermes, etc.)
- Local TTS
- Avatar rendering

It's the **offline/fallback** provider, not the default.

### 4. Unified event protocol

All frontends and the worker speak the same WebSocket JSON protocol:

```typescript
// Frontend → Gateway
type ClientMessage =
  | { type: "audio_data"; audio: ArrayBuffer }  // raw PCM16
  | { type: "set_provider"; provider: string }
  | { type: "set_config"; key: string; value: unknown }
  | { type: "interrupt" }
  | { type: "push_to_talk" }

// Gateway → Frontend
type ServerMessage =
  | { type: "state_change"; state: "idle" | "listening" | "thinking" | "speaking" | "interrupted" }
  | { type: "transcript"; text: string; final: boolean; source: "user" | "assistant" }
  | { type: "latency"; metrics: PerTurnMetrics }
  | { type: "audio_ready"; sessionId: string; format: "pcm16" | "opus" }
  | { type: "error"; message: string }
```

## State machine

```
       ┌──────────────────────────────────────────┐
       │                                          │
       ▼                                          │
    ┌──────┐  wake word   ┌───────────┐  speech   │
    │ IDLE │─────────────►│ LISTENING │────────┐  │
    │      │◄─────────────│           │◄───────┘  │
    └──────┘   stopped    └───────────┘           │
       │                                           │
       │  push-to-talk                             │
       ▼                                           │
    ┌──────┐              ┌───────────┐            │
    │ IDLE │─────────────►│ LISTENING │────────────┘
    └──────┘              └───────────┘
```

For live-voice providers, the state machine simplifies to:
```
IDLE ←→ CONNECTED (streaming)
```

## API routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/config` | Get full config |
| PUT | `/api/config` | Update config |
| GET | `/api/status` | Current state + metrics |
| WS | `/ws` | Frontend WebSocket |
| WS | `/ws/worker` | Python worker WebSocket |
| WS | `/ws/provider/livekit` | LiveKit agent bridge |

## Exit criteria

- [ ] Architecture diagram agreed
- [ ] Event protocol spec finalized
- [ ] State machine spec finalized
- [ ] API route spec finalized
- [ ] Provider interface spec finalized
- [ ] All approved proposals reflected
