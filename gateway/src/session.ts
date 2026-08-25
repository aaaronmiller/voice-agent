/**
 * Session manager and WebSocket hub.
 * Each frontend connection gets a Session that manages state,
 * provider routing, and metrics collection.
 */

import { type ServerWebSocket } from "bun";
import {
  type SessionState,
  type ClientMessage,
  type ServerMessage,
  type TurnMetrics,
  type VoiceProvider,
  type GatewayConfig,
  type ProviderInfo,
} from "./types";
import { MetricsAggregator } from "./metrics";
import { CostTracker } from "./cost-tracker";
import { listAvailableProviders } from "./config";

export class Session {
  readonly id: string;
  ws: ServerWebSocket<Session> | null = null;
  state: SessionState = "idle";
  provider: string;
  private providerImpl: VoiceProvider | null = null;
  metrics: MetricsAggregator;
  private config: GatewayConfig;
  private turnIdCounter: number = 0;
  private currentTurn: Partial<TurnMetrics> = {};
  private _audioCallback: ((data: ArrayBuffer) => void) | null = null;
  private _stateChangeCallback: ((state: SessionState) => void) | null = null;
  private costTracker: CostTracker = new CostTracker();

  constructor(id: string, provider: string, config: GatewayConfig) {
    this.id = id;
    this.provider = provider;
    this.config = config;
    this.metrics = new MetricsAggregator(config.metricsWindow);
  }

  /** Set the WebSocket for this session */
  setWebSocket(ws: ServerWebSocket<Session>) {
    this.ws = ws;
  }

  /** Set the provider implementation */
  setProviderImpl(impl: VoiceProvider | null) {
    this.providerImpl = impl;
  }

  /** Get the provider implementation */
  getProviderImpl(): VoiceProvider | null {
    return this.providerImpl;
  }

  /** Send a message to the connected frontend */
  send(msg: ServerMessage) {
    if (this.ws && this.ws.readyState === 1) {
      // Audio data is sent as binary
      if (msg.type === "audio_ready") {
        this.ws.send(JSON.stringify(msg));
      } else {
        this.ws.send(JSON.stringify(msg));
      }
    }
  }

  /** Send binary audio data to frontend */
  sendAudio(data: ArrayBuffer) {
    if (this.ws && this.ws.readyState === 1) {
      // Prepend a binary header byte to signal audio data
      this.ws.send(data);
    }
  }

  /** Update session state and notify frontend */
  setState(newState: SessionState) {
    this.state = newState;
    this.send({ type: "state_change", state: newState });
    if (this._stateChangeCallback) {
      this._stateChangeCallback(newState);
    }
  }

  /** Handle incoming messages from the frontend */
  handleMessage(data: string | ArrayBuffer) {
    if (typeof data === "string") {
      this.handleJSON(data);
    } else {
      this.handleAudio(data);
    }
  }

  private handleJSON(raw: string) {
    try {
      const msg: ClientMessage = JSON.parse(raw);

      switch (msg.type) {
        case "set_provider":
          this.switchProvider(msg.provider);
          break;

        case "set_config":
          this.handleSetConfig(msg.key, msg.value);
          break;

        case "interrupt":
          this.handleInterrupt();
          break;

        case "push_to_talk":
          this.handlePushToTalk(msg.active);
          break;

        case "ping":
          this.send({ type: "pong" });
          break;
      }
    } catch (err) {
      this.send({
        type: "error",
        message: `Invalid JSON: ${(err as Error).message}`,
      });
    }
  }

  private handleAudio(data: ArrayBuffer) {
    if (this.providerImpl) {
      this.providerImpl.sendAudio(data);
    }
  }

  /** Switch to a different provider at runtime */
  async switchProvider(name: string) {
    if (name === this.provider) return;

    // Destroy old provider
    if (this.providerImpl) {
      await this.providerImpl.destroy();
    }

    this.provider = name;
    this.providerImpl = null;
    this.setState("idle");

    // Notify frontend of available providers
    this.broadcastProviders();
  }

  /** Handle configuration changes */
  private handleSetConfig(key: string, value: unknown) {
    // Config changes are relayed to the provider if it supports hot-reload
    console.log(`[session ${this.id}] config ${key}=${JSON.stringify(value)}`);
  }

  /** Handle interrupt request */
  private handleInterrupt() {
    if (this.currentTurn) {
      this.currentTurn.tInterruptReq = performance.now();
    }
    if (this.providerImpl) {
      this.providerImpl.interrupt();
    }
    this.setState("interrupted");
  }

  /** Handle push-to-talk state change */
  private handlePushToTalk(active: boolean) {
    if (active) {
      this.startTurn();
    } else {
      this.endUserSpeech();
    }
  }

  /** Start a new interaction turn */
  startTurn() {
    this.turnIdCounter++;
    this.currentTurn = {
      turnId: this.turnIdCounter,
      provider: this.provider,
      tWake: performance.now(),
      interrupted: false,
      error: "",
    };
    this.setState("listening");
  }

  /** Mark the end of user speech */
  endUserSpeech() {
    this.currentTurn.tUserDone = performance.now();
    this.setState("streaming");
  }

  /** Record first token from provider */
  recordFirstToken() {
    this.currentTurn.tFirstToken = performance.now();
  }

  /** Record response complete */
  recordResponseDone() {
    this.currentTurn.tResponseDone = performance.now();
  }

  /** Record playback start */
  recordPlaybackStart() {
    this.currentTurn.tPlaybackStart = performance.now();
  }

  /** Record playback complete and finalize turn */
  endTurn(audioInputMs: number = 0, audioOutputMs: number = 0, textInputChars: number = 0, textOutputChars: number = 0) {
    this.currentTurn.tPlaybackDone = performance.now();

    // Estimate cost for this turn
    const cost = this.costTracker.estimateTurn(
      this.provider,
      audioInputMs,
      audioOutputMs,
      textInputChars,
      textOutputChars
    );
    this.currentTurn.costUsd = cost.costUsd;
    this.currentTurn.cumulativeUsd = cost.cumulativeUsd;
    this.currentTurn.pricingLabel = cost.pricingLabel;
    this.currentTurn.audioInputMs = cost.audioInputMs;
    this.currentTurn.audioOutputMs = cost.audioOutputMs;
    this.currentTurn.textInputChars = cost.textInputChars;
    this.currentTurn.textOutputChars = cost.textOutputChars;

    // Finalize and record
    const final = this.currentTurn as TurnMetrics;
    this.metrics.record(final);

    // Broadcast metrics to frontend
    this.send({ type: "latency", metrics: final });
    this.send({
      type: "latency_snapshot",
      snapshot: this.metrics.getSnapshot(20),
    });

    this.currentTurn = {};
    this.setState("idle");
  }

  /** Interrupt ack from provider — audio actually stopped */
  recordInterruptAck() {
    if (this.currentTurn) {
      this.currentTurn.tInterruptAck = performance.now();
      this.currentTurn.interrupted = true;
    }
  }

  /** An error occurred during the turn */
  recordError(error: string) {
    if (this.currentTurn) {
      this.currentTurn.error = error;
    }
    this.send({ type: "error", message: error });
  }

  /** Send list of available providers to frontend with pricing info */
  broadcastProviders() {
    const available = listAvailableProviders(this.config);
    const list: ProviderInfo[] = available.map((name) => ({
      name,
      type: name === "hermes" || name === "pi-agent" ? "legacy" : "live-voice",
      available: true,
      pricing: CostTracker.getProviderPricingInfo(name),
    }));
    this.send({ type: "providers", list });
  }

  /** Cleanup on disconnect */
  cleanup() {
    if (this.providerImpl) {
      this.providerImpl.destroy();
      this.providerImpl = null;
    }
  }
}

/** Manages all active sessions */
export class SessionManager {
  private sessions = new Map<string, Session>();
  private config: GatewayConfig;

  constructor(config: GatewayConfig) {
    this.config = config;
  }

  /** Create a new session */
  create(ws: ServerWebSocket<Session>): Session {
    const id = crypto.randomUUID();
    const session = new Session(id, this.config.provider, this.config);
    session.setWebSocket(ws);
    this.sessions.set(id, session);

    // Send initial state
    session.send({ type: "state_change", state: "idle" });
    session.broadcastProviders();

    return session;
  }

  /** Get session by ID */
  get(id: string): Session | undefined {
    return this.sessions.get(id);
  }

  /** Remove a session */
  remove(id: string) {
    const session = this.sessions.get(id);
    if (session) {
      session.cleanup();
      this.sessions.delete(id);
    }
  }

  /** Get all sessions */
  getAll(): Session[] {
    return Array.from(this.sessions.values());
  }

  /** Get aggregated metrics across all sessions */
  getGlobalSnapshot() {
    if (this.sessions.size === 0) return null;

    // Merge all metrics
    const allTurns: TurnMetrics[] = [];
    for (const session of this.sessions.values()) {
      allTurns.push(...session.metrics.recent(1000));
    }

    // Sort by turnId and take recent 100
    allTurns.sort((a, b) => b.turnId - a.turnId);
    const recent = allTurns.slice(0, 100);

    const earsValues = recent
      .map((t) => t.earsToMouth)
      .filter((v): v is number => v !== undefined);

    return {
      totalTurns: recent.length,
      activeSessions: this.sessions.size,
      avgEarsToMouth:
        earsValues.length > 0
          ? earsValues.reduce((a, b) => a + b, 0) / earsValues.length
          : 0,
    };
  }
}
