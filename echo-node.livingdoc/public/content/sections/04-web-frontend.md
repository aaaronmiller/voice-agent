# Svelte 5 SPA

**Phase:** 3 — Web Frontend | **Status:** Pending | **Owner:** Frontend team

## Entry criteria

- [x] Gateway is running (Phase 2 complete)
- [x] WebSocket protocol finalized (Phase 1)
- [x] Bun available

## Implementation

### File structure under `~/code/voice-agent/frontend/`

```
frontend/
├── package.json
├── svelte.config.js
├── vite.config.ts
├── src/
│   ├── main.ts
│   ├── App.svelte
│   ├── lib/
│   │   ├── websocket.ts      # WS connection to gateway
│   │   ├── state.ts          # Reactive state store
│   │   ├── audio.ts          # Web Audio API capture/playback
│   │   ├── types.ts          # Shared types
│   │   ├── metrics.ts        # Latency display helpers
│   │   └── settings.ts       # Settings panel logic
│   ├── components/
│   │   ├── Avatar.svelte     # Talking head avatar (canvas)
│   │   ├── Waveform.svelte   # Audio waveform viz
│   │   ├── Transcript.svelte # Conversation transcript
│   │   ├── LatencyPanel.svelte # Live latency dashboard
│   │   ├── SettingsPanel.svelte # Config UI
│   │   ├── ProviderSelect.svelte # Provider dropdown
│   │   ├── PushToTalk.svelte # PTT button
│   │   └── StatusIndicator.svelte # State badge
│   └── views/
│       ├── Dashboard.svelte  # Main conversation view
│       └── Settings.svelte   # Full settings page
```

### WebSocket connection (`websocket.ts`)

```typescript
class VoiceGateway {
  private ws: WebSocket;
  private audioContext: AudioContext;
  
  connect(url: string): Promise<void>;
  sendAudio(data: Float32Array): void;
  setProvider(name: string): void;
  interrupt(): void;
  
  // Reactive state
  onStateChange(cb: (state: string) => void): void;
  onTranscript(cb: (text: string, source: string) => void): void;
  onMetrics(cb: (m: PerTurnMetrics) => void): void;
  onAudio(cb: (data: Float32Array) => void): void;
}
```

### Audio pipeline (`audio.ts`)

Uses Web Audio API for:
- Microphone capture via `getUserMedia`
- Playback via `AudioContext` + `AudioWorklet`
- VAD visualization (optional, for debugging)
- Echo cancellation hints (browser handles this natively)

### Key views

**Dashboard view** — main conversation interface:
- Avatar display (canvas-based talking head or video)
- Live waveform during listening/speaking
- Transcript panel (scrollable history)
- Push-to-talk button + keyboard shortcut
- Latency panel (collapsible, shows current turn metrics)
- Status badge (idle/listening/thinking/speaking)

**Settings view** — configuration panel:
- Provider selector (Gemini Live, OpenAI Realtime, Hermes, Local)
- API key management (stored in session, not localStorage)
- TTS voice selection (for legacy mode)
- VAD threshold slider
- Theme toggle (dark/light)
- Latency dashboard toggle

### Responsive layout

- Desktop: side-by-side transcript + avatar/waveform
- Mobile: stacked, avatar collapsed to small badge
- Collapsible panels for settings and latency

## Exit criteria

- [ ] Svelte app starts with `bun run dev`
- [x] Connects to gateway WebSocket
- [x] Push-to-talk sends audio to gateway
- [ ] Assistant audio plays through browser
- [ ] Transcript shows user and assistant messages
- [ ] Provider selector switches active provider
- [ ] Latency panel shows live metrics
- [ ] Settings are editable and persist to gateway
- [ ] Avatar renders (even if simple canvas face)
- [ ] Works in Chrome and Firefox
