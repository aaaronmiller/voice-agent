# Bun+Hono WebSocket relay

**Phase:** 2 — Gateway | **Status:** Pending | **Owner:** Backend team

## Entry criteria

- [x] Architecture spec finalized (section 02)
- [x] Event protocol spec finalized (section 02)
- [x] Bun installed (check: `which bun`)
- [x] Existing `v2/echo_node/` code available for reference

## Implementation

### File structure under `~/code/voice-agent/gateway/`

```
gateway/
├── package.json
├── tsconfig.json
├── .env.example
├── src/
│   ├── index.ts              # Hono server entry
│   ├── config.ts             # Config loader (reads config.yaml)
│   ├── session.ts            # Session manager + WS hub
│   ├── providers/
│   │   ├── registry.ts       # Provider registry
│   │   ├── gemini-live.ts    # Gemini WebRTC relay
│   │   ├── openai-realtime.ts # OpenAI WebRTC relay
│   │   └── python-worker.ts  # Legacy Python worker bridge
│   ├── api/
│   │   ├── health.ts
│   │   ├── config.ts
│   │   └── status.ts
│   ├── metrics.ts            # Latency aggregation
│   └── types.ts              # Shared types
```

### Core: WebSocket hub (`session.ts`)

```typescript
// Key abstractions
class Session {
  id: string;
  state: SessionState;
  frontend: WebSocket | null;   // Connected frontend
  worker: WebSocket | null;     // Connected Python worker (if legacy mode)
  provider: string;             // Current provider key
  metrics: TurnMetrics[];       // Rolling window of turn metrics
  
  broadcast(msg: ServerMessage): void;
  setProvider(key: string): void;
  handleAudio(data: ArrayBuffer): void;
  handleInterrupt(): void;
}

class SessionManager {
  private sessions: Map<string, Session>;
  
  create(frontend: WebSocket): Session;
  get(id: string): Session | undefined;
  remove(id: string): void;
}
```

### Config loader (`config.ts`)

Reads the existing `config.yaml` from `~/code/voice-agent/v2/config.yaml` and extends it with gateway-specific sections:

```yaml
gateway:
  port: 3000
  host: "127.0.0.1"
  session_timeout_seconds: 300
  metrics_window: 100  # turns to keep in rolling window
  providers:
    default: "gemini-live"
    available: ["gemini-live", "openai-realtime", "hermes", "local"]
```

### Provider registry (`providers/registry.ts`)

```typescript
interface VoiceProvider {
  name: string;
  type: "live-voice" | "legacy";
  
  // Lifecycle
  init(session: Session): Promise<void>;
  destroy(): Promise<void>;
  
  // Audio
  sendAudio(data: ArrayBuffer): void;
  receiveAudio(callback: (data: ArrayBuffer) => void): void;
  
  // Controls
  interrupt(): void;
  setConfig(key: string, value: unknown): void;
  
  // Health
  isAvailable(): boolean;
  healthCheck(): Promise<HealthStatus>;
}
```

### Python worker bridge (`providers/python-worker.ts`)

Connects to the existing `assistant_v2.py` via WebSocket (Python connects to gateway):

```typescript
class PythonWorkerProvider implements VoiceProvider {
  // Spawns or connects to the Python process
  // Relays audio frames bidirectionally
  // Translates between WS JSON protocol and stdin/stdout
}
```

### Metrics aggregation (`metrics.ts`)

```typescript
interface TurnMetrics {
  turnId: number;
  provider: string;
  timestamps: {
    wake: number;
    userDone: number;
    firstToken: number;
    responseDone: number;
    playbackStart: number;
    playbackDone: number;
  };
  derived: {
    earsToMouth: number;      // userDone → playbackStart
    llmFirstToken: number;    // userDone → firstToken
    total: number;            // wake → playbackDone
  };
}

class MetricsAggregator {
  private turns: TurnMetrics[] = [];
  
  record(turn: TurnMetrics): void;
  
  // Rolling window stats
  averageLatency(window?: number): ProviderStats;
  percentile(p: number, window?: number): ProviderStats;
  perProvider(): Map<string, ProviderStats>;
  
  // Export for dashboard
  snapshot(): MetricsSnapshot;
}
```

## Provider-specific notes

### Live-voice providers (Gemini, OpenAI)

For these, the gateway is a **thin relay**:
1. Frontend sends WebRTC SDP offer to gateway
2. Gateway forwards to Gemini/OpenAI API
3. Gateway relays SDP answer back to frontend
4. Audio flows directly frontend ↔ cloud API (via gateway or directly)
5. Gateway receives status events and metrics from the provider

### Legacy provider (Python worker)

The gateway manages:
1. Spawning/killing the Python process
2. Stdio-based JSON protocol (legacy)
3. Or WebSocket connection from Python (preferred, lower latency)

## Exit criteria

- [x] `bun run dev` starts the gateway on port 3000
- [ ] WebSocket handshake works (`ws://localhost:3000/ws`)
- [ ] Frontend receives state change events
- [ ] Frontend can send audio data
- [x] Provider registry lists available providers
- [ ] Python worker connects and relays audio
- [ ] Metrics are collected and queryable via REST
- [ ] Health endpoint returns 200
