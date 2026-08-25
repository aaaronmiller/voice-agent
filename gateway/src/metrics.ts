/**
 * Latency metrics aggregation.
 * Collects per-turn metrics and provides rolling-window statistics.
 */

import { type TurnMetrics, type MetricsSnapshot, type ProviderStats } from "./types";

export class MetricsAggregator {
  private totalCostUsd: number = 0;
  private turns: TurnMetrics[] = [];
  private maxWindow: number;

  constructor(maxWindow: number = 1000) {
    this.maxWindow = maxWindow;
  }

  /** Record a completed turn and compute derived latencies + cost. */
  record(t: TurnMetrics): TurnMetrics {
    // Compute derived latencies
    t.earsToMouth = t.tPlaybackStart && t.tUserDone
      ? t.tPlaybackStart - t.tUserDone
      : undefined;
    t.llmFirstToken = t.tFirstToken && t.tUserDone
      ? t.tFirstToken - t.tUserDone
      : undefined;
    t.totalLatency = t.tPlaybackDone && t.tWake
      ? t.tPlaybackDone - t.tWake
      : undefined;
    t.interruptLatency = t.tInterruptAck && t.tInterruptReq
      ? t.tInterruptAck - t.tInterruptReq
      : undefined;

    // Track cost
    if (t.costUsd !== undefined) {
      this.totalCostUsd += t.costUsd;
    }

    this.turns.push(t);
    if (this.turns.length > this.maxWindow) {
      this.turns.shift();
    }
    return t;
  }

  /** Get the most recent n turns */
  recent(n: number): TurnMetrics[] {
    return this.turns.slice(-n);
  }

  /** Get the latest turn */
  latest(): TurnMetrics | undefined {
    return this.turns[this.turns.length - 1];
  }

  /** Compute per-provider stats */
  perProvider(window: number = 50): ProviderStats[] {
    const recent = this.recent(window);
    const byProvider = new Map<string, TurnMetrics[]>();

    for (const t of recent) {
      const list = byProvider.get(t.provider) || [];
      list.push(t);
      byProvider.set(t.provider, list);
    }

    const stats: ProviderStats[] = [];
    for (const [provider, turns] of byProvider) {
      const earsValues = turns
        .map((t) => t.earsToMouth)
        .filter((v): v is number => v !== undefined);

      const costs = turns
        .map((t) => t.costUsd)
        .filter((v): v is number => v !== undefined);
      const totalCost = costs.reduce((a, b) => a + b, 0);

      stats.push({
        provider,
        turnCount: turns.length,
        avgEarsToMouth: average(earsValues),
        p50EarsToMouth: percentile(earsValues, 50),
        p95EarsToMouth: percentile(earsValues, 95),
        p99EarsToMouth: percentile(earsValues, 99),
        minEarsToMouth: earsValues.length ? Math.min(...earsValues) : 0,
        maxEarsToMouth: earsValues.length ? Math.max(...earsValues) : 0,
        avgTotalLatency: average(
          turns.map((t) => t.totalLatency).filter((v): v is number => v !== undefined)
        ),
        avgLlmFirstToken: average(
          turns.map((t) => t.llmFirstToken).filter((v): v is number => v !== undefined)
        ),
        interruptCount: turns.filter((t) => t.interrupted).length,
        errorCount: turns.filter((t) => t.error).length,
        totalCostUsd: totalCost,
        avgCostPerTurn: turns.length > 0 ? totalCost / turns.length : 0,
      });
    }

    return stats.sort((a, b) => b.turnCount - a.turnCount);
  }

  /** Get a full metrics snapshot for UI broadcasting */
  getSnapshot(window: number = 20): MetricsSnapshot {
    const recent = this.recent(window);
    const earsValues = recent
      .map((t) => t.earsToMouth)
      .filter((v): v is number => v !== undefined);

    return {
      currentTurn: this.latest(),
      rollingWindow: window,
      totalTurns: this.turns.length,
      totalCostUsd: this.totalCostUsd,
      perProvider: this.perProvider(window),
      percentiles: {
        p50: percentile(earsValues, 50),
        p95: percentile(earsValues, 95),
        p99: percentile(earsValues, 99),
      },
    };
  }

  /** Clear all metrics */
  reset(): void {
    this.turns = [];
  }
}

// ── Utility functions ──

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function percentile(sortedValues: number[], p: number): number {
  if (sortedValues.length === 0) return 0;
  const sorted = [...sortedValues].sort((a, b) => a - b);
  const index = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
}
