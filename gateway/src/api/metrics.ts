/**
 * Prometheus /metrics endpoint for the Echo-Node gateway.
 * Exposes latency, cost, and session metrics for Grafana Alloy to scrape.
 * Endpoint: http://localhost:3000/api/metrics
 */

import { Hono } from "hono";
import { type SessionManager } from "../session";
import {
  Registry,
  collectDefaultMetrics,
  Counter,
  Gauge,
  Histogram,
} from "prom-client";

const register = new Registry();
let initialized = false;
let turnsTotal: Counter<string>;
let activeSessions: Gauge<string>;
let totalCost: Gauge<string>;
let turnLatency: Histogram<string>;
let llmLatency: Histogram<string>;
let providerTurnsTotal: Counter<string>;
let costPerTurn: Gauge<string>;

function initMetrics() {
  if (initialized) return;
  initialized = true;
  collectDefaultMetrics({ register });

  turnsTotal = new Counter({
    name: "echo_node_turns_total",
    help: "Total number of turns processed across all sessions",
    registers: [register],
  });

  activeSessions = new Gauge({
    name: "echo_node_active_sessions",
    help: "Currently active sessions",
    registers: [register],
  });

  totalCost = new Gauge({
    name: "echo_node_total_cost_usd",
    help: "Total cumulative cost in USD",
    registers: [register],
  });

  turnLatency = new Histogram({
    name: "echo_node_turn_latency_ms",
    help: "Per-turn total latency in milliseconds",
    buckets: [100, 200, 400, 600, 800, 1000, 1500, 2000, 3000, 5000],
    registers: [register],
  });

  llmLatency = new Histogram({
    name: "echo_node_llm_first_token_ms",
    help: "Time to first LLM token in milliseconds",
    buckets: [50, 100, 200, 400, 600, 800, 1000, 2000, 4000],
    registers: [register],
  });

  providerTurnsTotal = new Counter({
    name: "echo_node_provider_turns_total",
    help: "Total turns per provider",
    labelNames: ["provider"],
    registers: [register],
  });

  costPerTurn = new Gauge({
    name: "echo_node_cost_per_turn_usd",
    help: "Cost of the most recent turn in USD",
    labelNames: ["provider"],
    registers: [register],
  });
}

export function metricsRoutes(sessions: SessionManager) {
  const app = new Hono();
  initMetrics();

  app.get("/", async (c) => {
    const allSessions = sessions.getAll();

    // Active sessions
    activeSessions.set(
      allSessions.filter((s) =>
        ["connected", "listening", "thinking", "speaking"].includes(s.state)
      ).length
    );

    // Aggregate metrics across all sessions
    let totalTurns = 0;
    let totalCostUsd = 0;
    const providerStats = new Map<
      string,
      { turns: number; cost: number }
    >();

    for (const session of allSessions) {
      const turns = session.metrics.recent(1000);
      totalTurns += turns.length;

      for (const turn of turns) {
        if (turn.costUsd !== undefined) totalCostUsd += turn.costUsd;

        const provider = turn.provider || session.provider || "unknown";
        if (!providerStats.has(provider)) {
          providerStats.set(provider, { turns: 0, cost: 0 });
        }
        const ps = providerStats.get(provider)!;
        ps.turns++;
        if (turn.costUsd !== undefined) ps.cost += turn.costUsd;
        if (turn.totalLatency !== undefined) {
          turnLatency.observe(turn.totalLatency);
        }
        if (turn.llmFirstToken !== undefined) {
          llmLatency.observe(turn.llmFirstToken);
        }
      }
    }

    // Counters need to be reset and re-incremented since we re-aggregate each scrape
    for (const [provider, stats] of providerStats) {
      providerTurnsTotal.inc({ provider }, stats.turns);
      const avgCost = stats.turns > 0 ? stats.cost / stats.turns : 0;
      costPerTurn.set({ provider }, avgCost);
    }

    const metrics = await register.metrics();
    return c.text(metrics, 200, {
      "Content-Type": register.contentType,
    });
  });

  return app;
}