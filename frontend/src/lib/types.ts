/** Shared types for the Echo-Node web frontend */

export type SessionState =
  | "idle" | "listening" | "streaming" | "thinking" | "speaking"
  | "interrupted" | "error";

export interface ProviderInfo {
  name: string;
  type: string;
  available: boolean;
  pricing?: { label: string; isFree: boolean };
}

export interface TurnMetrics {
  turnId: number;
  provider: string;
  earsToMouth?: number;
  llmFirstToken?: number;
  totalLatency?: number;
  tWake: number;
  tUserDone: number;
  tFirstToken: number;
  tResponseDone: number;
  tPlaybackStart: number;
  tPlaybackDone: number;
  interrupted: boolean;
  error: string;
  // Cost tracking
  costUsd?: number;
  cumulativeUsd?: number;
  pricingLabel?: string;
  audioInputMs?: number;
  audioOutputMs?: number;
}

export interface ProviderStats {
  provider: string;
  turnCount: number;
  avgEarsToMouth: number;
  p50EarsToMouth: number;
  p95EarsToMouth: number;
  p99EarsToMouth: number;
  totalCostUsd?: number;
  avgCostPerTurn?: number;
}

export interface MetricsSnapshot {
  currentTurn?: TurnMetrics;
  rollingWindow: number;
  totalTurns: number;
  totalCostUsd?: number;
  perProvider: ProviderStats[];
  percentiles: {
    p50: number;
    p95: number;
    p99: number;
  };
}

export interface ServerMessage {
  type: string;
  state?: SessionState;
  text?: string;
  source?: string;
  final?: boolean;
  metrics?: TurnMetrics;
  snapshot?: MetricsSnapshot;
  list?: ProviderInfo[];
  message?: string;
}
