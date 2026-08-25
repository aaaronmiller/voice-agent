/**
 * Stub provider — for testing the gateway without any real provider.
 * Echoes back a canned response.
 */

import {
  type VoiceProvider,
  type SessionState,
  type TurnMetrics,
  type ProviderConfig,
} from "../types";

export class StubProvider implements VoiceProvider {
  readonly name = "stub";
  readonly type = "live-voice";
  private audioCb: ((data: ArrayBuffer) => void) | null = null;
  private transcriptCb:
    | ((text: string, source: "user" | "assistant", final: boolean) => void)
    | null = null;
  private stateCb: ((state: SessionState) => void) | null = null;
  private metricsCb: ((metrics: TurnMetrics) => void) | null = null;

  async init(): Promise<void> {
    console.log("[stub] initialized");
  }

  async destroy(): Promise<void> {
    console.log("[stub] destroyed");
  }

  sendAudio(data: ArrayBuffer): void {
    // Stub: simulate a response after receiving audio
    if (this.stateCb) this.stateCb("thinking");
    if (this.transcriptCb) {
      this.transcriptCb("I heard audio. This is a stub response.", "assistant", true);
    }
    if (this.stateCb) this.stateCb("speaking");
    if (this.stateCb) this.stateCb("idle");

    // Report fake metrics
    if (this.metricsCb) {
      this.metricsCb({
        turnId: Date.now(),
        provider: "stub",
        tWake: performance.now() - 2000,
        tUserDone: performance.now() - 1500,
        tFirstToken: performance.now() - 1000,
        tResponseDone: performance.now() - 500,
        tPlaybackStart: performance.now() - 400,
        tPlaybackDone: performance.now(),
        earsToMouth: 1100,
        llmFirstToken: 500,
        totalLatency: 2000,
        interrupted: false,
        error: "",
      });
    }
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
    console.log("[stub] interrupt received");
  }

  isAvailable(): boolean {
    return true;
  }

  async healthCheck(): Promise<boolean> {
    return true;
  }
}
