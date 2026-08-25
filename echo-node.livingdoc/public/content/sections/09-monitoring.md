# Live monitoring and observability dashboard

**Phase:** 6 — Observability | **Status:** Pending | **Owner:** Observability team

## Entry criteria

- [x] ConversationLogger exists and collects per-stage timestamps (done)
- [x] Gateway running (Phase 2) — for real-time metrics relay
- [x] At least one provider working (for generating metrics)

## Implementation

### The problem

Currently the `ConversationLogger` collects excellent per-turn data but it's:
- Printed to terminal (`[perf] turn=1 | total=3.2s | stt=0.45s | llm=1.8s | ...`)
- Written to a JSONL file
- Only summarized at session end (`close()` method prints summary)
- **No live visibility during a session**
- **No aggregation across turns**
- **No per-provider breakdowns**

### What we need

A 3-tier observability system:

#### Tier 1: Terminal dashboard (Textual, ship first)

A live-updating terminal dashboard that runs as a sidecar or embedded in the TUI:

```
┌─────────────────────────────────────────────────────────────────┐
│  Echo-Node Live Metrics                    [turns: 47]         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ Current turn ───────────────────────────────────────────┐   │
│  │  ears→mouth   342ms                                       │   │
│  │  first token  180ms  ████████████░░░░░░░░░░░              │   │
│  │  total         1.2s  ██████████████████████████████░░░░   │   │
│  │  provider      Gemini Live                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ Rolling averages (last 20 turns) ───────────────────────┐   │
│  │  p50  ████████████░░░░░░  320ms                          │   │
│  │  p95  ████████████████████████████░░░  890ms             │   │
│  │  p99  ████████████████████████████████████████░  1.4s     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ Latency sparkline ───────────────────────────────────────┐   │
│  │  ╭╮╱╲╱╱╲╱╱╲╱╱╱╲╱╲╱╱╲╱╲╱╲╱╱╲╱╲╱╱╱╲╱╲╱╱╲╱╲╱╲╱╱╲╱╲╱╱╱╲  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ Per-provider ────────────────────────────────────────────┐   │
│  │  Gemini Live    avg 312ms  n=32  ██████████████████████   │   │
│  │  OpenAI Real.   avg 287ms  n=10  ██████████████████░░░   │   │
│  │  Hermes         avg 2.4s   n=5   █░░░░░░░░░░░░░░░░░░░░   │   │
│  │  Local (legacy)  avg 3.1s   n=3   █░░░░░░░░░░░░░░░░░░░░   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### Tier 2: Web dashboard widget (embedded in Svelte frontend)

The same metrics rendered in the web UI as a collapsible panel. Uses Chart.js or D3 for sparklines and bar charts. Communicates with the gateway via the same WebSocket, receiving `{ type: "latency"; metrics: ... }` messages.

#### Tier 3: Historical analytics (session replay)

After a session, the JSONL log files can be loaded into a static analysis tool:
- Compare provider performance across sessions
- Identify latency regression trends
- Export to CSV for external analysis

### Metrics data model

```typescript
// Gateway → Frontend
interface PerTurnMetrics {
  turnId: number;
  provider: string;
  
  // Absolute timestamps (monotonic ms)
  tWake: number;
  tUserDone: number;        // User stopped speaking
  tFirstToken: number;      // First LLM token received
  tResponseDone: number;    // Full response received
  tPlaybackStart: number;
  tPlaybackDone: number;
  
  // Derived (computed by gateway)
  earsToMouth: number;      // tPlaybackStart - tUserDone (ms)
  llmFirstToken: number;    // tFirstToken - tUserDone (ms)
  totalLatency: number;     // tPlaybackDone - tWake (ms)
  interruptLatency?: number; // If interrupted: tInterruptAck - tInterruptReq
}

// Aggregated stats
interface ProviderStats {
  provider: string;
  turnCount: number;
  avgEarsToMouth: number;
  p50EarsToMouth: number;
  p95EarsToMouth: number;
  p99EarsToMouth: number;
  avgTotalLatency: number;
  maxTotalLatency: number;
  minTotalLatency: number;
  interruptCount: number;
  errorCount: number;
}
```

### Gateway metrics aggregation

In `gateway/src/metrics.ts`:

```typescript
class MetricsAggregator {
  private turnMetrics: PerTurnMetrics[] = [];
  private maxWindow: number = 1000;  // Max turns to keep in memory
  
  record(m: PerTurnMetrics): void {
    this.turnMetrics.push(m);
    if (this.turnMetrics.length > this.maxWindow) {
      this.turnMetrics.shift();
    }
    this.broadcastToFrontends(this.getSnapshot());
  }
  
  getSnapshot(): MetricsSnapshot {
    return {
      currentTurn: this.turnMetrics[this.turnMetrics.length - 1],
      rollingAverages: this.computeRollingAverages(20),
      perProvider: this.computePerProvider(),
      percentiles: this.computePercentiles(20, [50, 95, 99]),
      turnCount: this.turnMetrics.length,
    };
  }
  
  private computeRollingAverages(window: number): RollingStats {
    const windowed = this.turnMetrics.slice(-window);
    return {
      avgEarsToMouth: mean(windowed.map(m => m.earsToMouth)),
      avgTotal: mean(windowed.map(m => m.totalLatency)),
      // ...
    };
  }
}
```

### ConversationLogger upgrade

The existing `ConversationLogger` needs:

1. **Real-time emission**: Instead of just writing to JSONL, emit a callback/event when a turn completes
2. **Hook into gateway**: If gateway is running, send metrics via WebSocket
3. **Standalone mode**: If no gateway, print to terminal as before

```python
# In conversation_logger.py, add:
class ObservableConversationLogger(ConversationLogger):
    def __init__(self, config, on_turn_complete: Callable[[TurnRecord], None] = None):
        super().__init__(config)
        self._on_turn_complete = on_turn_complete
        
    def end_turn(self, rec: TurnRecord) -> None:
        super().end_turn(rec)
        if self._on_turn_complete:
            self._on_turn_complete(rec)
```

### What metrics to collect (comprehensive)

| Metric | Unit | Source | Importance |
|---|---|---|---|
| Ears-to-mouth latency | ms | User done → playback start | **Critical** |
| LLM first token latency | ms | User done → first token | **Critical** |
| Total turn latency | ms | Wake → playback done | High |
| STT latency (legacy) | ms | STT start → done | High (legacy) |
| TTS latency (legacy) | ms | TTS start → done | High (legacy) |
| Interrupt response | ms | Interrupt request → audio stop | High |
| Audio capture jitter | ms | Variation in chunk arrival | Medium |
| Provider availability | bool | Health check success | Medium |
| Provider error rate | % | Errors / total turns | Medium |
| Turn count | count | Turns per session | Low |
| User speech duration | ms | VAD start → end | Low |

## Exit criteria

- [ ] Terminal latency dashboard shows live metrics during session
- [ ] Gateway emits `{ type: "latency" }` messages after each turn
- [ ] Rolling averages (p50, p95, p99) displayed and updated in real-time
- [ ] Per-provider breakdown visible
- [ ] Interrupt latency tracked and displayed
- [ ] Web dashboard panel shows same metrics (when web frontend connected)
- [ ] Historical JSONL logs can be replayed into the dashboard
- [ ] Metrics exportable as JSON/CSV
