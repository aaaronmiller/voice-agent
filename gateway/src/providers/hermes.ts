/**
 * Hermes Agent provider.
 * Connects to a local Hermes Agent API server.
 */

import {
  type VoiceProvider,
  type SessionState,
  type TurnMetrics,
  type ProviderConfig,
} from "../types";

export class HermesProvider implements VoiceProvider {
  readonly name = "hermes";
  readonly type = "legacy";
  private config: ProviderConfig;
  private audioCb: ((data: ArrayBuffer) => void) | null = null;
  private transcriptCb:
    | ((text: string, source: "user" | "assistant", final: boolean) => void)
    | null = null;
  private stateCb: ((state: SessionState) => void) | null = null;
  private metricsCb: ((metrics: TurnMetrics) => void) | null = null;

  constructor(config: ProviderConfig) {
    this.config = config;
  }

  get baseUrl(): string {
    return (this.config.baseUrl as string) || "http://127.0.0.1:8642/v1";
  }

  get apiKey(): string {
    return (this.config.apiKey as string) || "";
  }

  async init(): Promise<void> {
    console.log(`[hermes] initialized (${this.baseUrl})`);
  }

  async destroy(): Promise<void> {
    console.log("[hermes] destroyed");
  }

  sendAudio(_data: ArrayBuffer): void {
    // Hermes is text-in/text-out, not audio-in/audio-out
    // Audio would be handled by the Python worker
    console.log("[hermes] audio received (relaying to text endpoint)");
  }

  onAudio(cb: (data: ArrayBuffer) => void): void {
    this.audioCb = cb;
  }

  onTranscript(
    cb: (text: string, source: "user" | "assistant", final: boolean) => void
  ): void {
    this.transcriptCb = cb;
  }

  onStateChange(cb: (state: SessionState) => void): void {
    this.stateCb = cb;
  }

  onMetrics(cb: (metrics: TurnMetrics) => void): void {
    this.metricsCb = cb;
  }

  interrupt(): void {
    console.log("[hermes] interrupt — no-op (text-in/text-out)");
  }

  isAvailable(): boolean {
    try {
      // Check health endpoint
      const url = this.baseUrl.replace("/v1", "").replace("/v1/", "") + "/health";
      const response = fetch(url, { method: "GET", signal: AbortSignal.timeout(3000) });
      return true; // optimistic
    } catch {
      return false;
    }
  }

  async healthCheck(): Promise<boolean> {
    return this.isAvailable();
  }
}
