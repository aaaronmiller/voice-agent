/**
 * Echo-Node Gateway — shared types and protocol definitions.
 */

// ── Session state machine ──
export type SessionState =
  | "idle"
  | "listening"
  | "streaming"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "error";

// ── Provider types ──
export type ProviderType = "live-voice" | "legacy";

export interface ProviderInfo {
  name: string;
  type: ProviderType;
  available: boolean;
  latency?: number; // current rolling avg in ms
  pricing?: { label: string; isFree: boolean };
}

// ── Frontend → Gateway messages ──
export type ClientMessage =
  | { type: "audio_data"; data: ArrayBuffer }
  | { type: "set_provider"; provider: string }
  | { type: "set_config"; key: string; value: unknown }
  | { type: "interrupt" }
  | { type: "push_to_talk"; active: boolean }
  | { type: "ping" };

// ── Gateway → Frontend messages ──
export type ServerMessage =
  | { type: "state_change"; state: SessionState }
  | { type: "transcript"; text: string; final: boolean; source: "user" | "assistant" }
  | { type: "latency"; metrics: TurnMetrics }
  | { type: "latency_snapshot"; snapshot: MetricsSnapshot }
  | { type: "audio_ready"; format: "pcm16" | "opus" }
  | { type: "providers"; list: ProviderInfo[] }
  | { type: "error"; message: string }
  | { type: "pong" };

// ── Turn metrics — collected per interaction turn ──
export interface TurnMetrics {
  turnId: number;
  provider: string;

  // Absolute timestamps (monotonic ms since epoch or relative)
  tWake: number;
  tUserDone: number;        // User stopped speaking / VAD end
  tFirstToken: number;      // First LLM token received
  tResponseDone: number;    // Full response received
  tPlaybackStart: number;
  tPlaybackDone: number;
  tInterruptReq?: number;   // If interrupted: when interrupt was requested
  tInterruptAck?: number;   // If interrupted: when audio actually stopped

  // Derived latencies (filled by gateway)
  earsToMouth?: number;     // tPlaybackStart - tUserDone (ms)
  llmFirstToken?: number;   // tFirstToken - tUserDone (ms)
  totalLatency?: number;    // tPlaybackDone - tWake (ms)
  interruptLatency?: number; // tInterruptAck - tInterruptReq (ms)

  // Cost tracking
  costUsd?: number;
  cumulativeUsd?: number;
  pricingLabel?: string;
  audioInputMs?: number;
  audioOutputMs?: number;
  textInputChars?: number;
  textOutputChars?: number;

  // Extra
  interrupted: boolean;
  error: string;
}

// ── Aggregated metrics snapshot ──
export interface ProviderStats {
  provider: string;
  turnCount: number;
  avgEarsToMouth: number;
  p50EarsToMouth: number;
  p95EarsToMouth: number;
  p99EarsToMouth: number;
  minEarsToMouth: number;
  maxEarsToMouth: number;
  avgTotalLatency: number;
  avgLlmFirstToken: number;
  interruptCount: number;
  errorCount: number;
  // Cost tracking
  totalCostUsd: number;
  avgCostPerTurn: number;
}

export interface MetricsSnapshot {
  currentTurn?: TurnMetrics;
  rollingWindow: number;
  totalTurns: number;
  totalCostUsd: number;
  perProvider: ProviderStats[];
  percentiles: {
    p50: number;
    p95: number;
    p99: number;
  };
}

// ── Provider interface (implemented by each provider module) ──
export interface VoiceProvider {
  readonly name: string;
  readonly type: ProviderType;

  /** Initialize a session — called once at provider select */
  init(): Promise<void>;

  /** Cleanup — called when provider is swapped or gateway shuts down */
  destroy(): Promise<void>;

  /** Feed audio data to the provider */
  sendAudio(data: ArrayBuffer): void;

  /** Register a callback for outgoing audio (provider → frontend) */
  onAudio(cb: (data: ArrayBuffer) => void): void;

  /** Register a callback for transcript events */
  onTranscript(cb: (text: string, source: "user" | "assistant", final: boolean) => void): void;

  /** Register a callback for state changes */
  onStateChange(cb: (state: SessionState) => void): void;

  /** Register a callback for turn metrics */
  onMetrics(cb: (metrics: TurnMetrics) => void): void;

  /** Interrupt the current response */
  interrupt(): void;

  /** Check if the provider is available */
  isAvailable(): boolean;

  /** Perform a health check */
  healthCheck(): Promise<boolean>;
}

// ── Session config ──
export interface GatewayConfig {
  port: number;
  host: string;
  provider: string;
  metricsWindow: number;
  sessionTimeoutSeconds: number;
  providers: Record<string, ProviderConfig>;
}

export interface ProviderConfig {
  apiKey?: string;
  model?: string;
  voice?: string;
  baseUrl?: string;
  timeout?: number;
  // Provider-specific options
  [key: string]: unknown;
}
