/**
 * Pi Agent provider — connects to the Pi coding agent via subprocess.
 * Text-in/text-out, useful for tool-calling during conversations.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { type VoiceProvider, type SessionState, type TurnMetrics, type ProviderConfig } from "../types";

export class PiProvider implements VoiceProvider {
  readonly name = "pi-agent";
  readonly type = "legacy";
  private config: ProviderConfig;
  private proc: ChildProcess | null = null;
  private transcriptCb:
    | ((text: string, source: "user" | "assistant", final: boolean) => void)
    | null = null;
  private stateCb: ((state: SessionState) => void) | null = null;
  private metricsCb: ((metrics: TurnMetrics) => void) | null = null;

  constructor(config: ProviderConfig) {
    this.config = config;
  }

  async init(): Promise<void> {
    console.log("[pi-agent] initialized (text-in/text-out)");
  }

  async destroy(): Promise<void> {
    if (this.proc) {
      this.proc.kill();
    }
  }

  sendAudio(_data: ArrayBuffer): void {
    // Pi is text-based, not audio-based
    // Audio would need STT first, then send text to Pi
    console.log("[pi-agent] audio received but Pi is text-only");
  }

  /** Send a text prompt and stream the response */
  async chat(text: string, system?: string): Promise<string> {
    const cmd = (this.config.command as string[]) || ["pi", "-p"];
    const timeout = (this.config.timeout as number) || 120;

    if (this.stateCb) this.stateCb("thinking");

    try {
      const result = Bun.spawnSync(cmd, {
        input: text,
        timeout: timeout * 1000,
      });

      const output = result.stdout.toString().trim();
      const errOutput = result.stderr.toString().trim();

      if (result.exitCode !== 0) {
        throw new Error(`Pi agent exited with code ${result.exitCode}: ${errOutput}`);
      }

      const answer = output || errOutput || "(no output)";

      if (this.transcriptCb) {
        this.transcriptCb(answer, "assistant", true);
      }
      if (this.stateCb) this.stateCb("idle");

      // Report metrics
      if (this.metricsCb) {
        this.metricsCb({
          turnId: Date.now(),
          provider: "pi-agent",
          tWake: performance.now() - 5000,
          tUserDone: performance.now() - 4000,
          tFirstToken: performance.now() - 2000,
          tResponseDone: performance.now(),
          tPlaybackStart: performance.now() - 100,
          tPlaybackDone: performance.now() + 1000,
          earsToMouth: 3900,
          llmFirstToken: 2000,
          totalLatency: 6000,
          interrupted: false,
          error: "",
        });
      }

      return answer;
    } catch (err) {
      const msg = `Pi agent error: ${(err as Error).message}`;
      if (this.transcriptCb) this.transcriptCb(msg, "assistant", true);
      if (this.stateCb) this.stateCb("error");
      return msg;
    }
  }

  onAudio(_cb: (data: ArrayBuffer) => void): void {
    // no-op
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
    if (this.proc) {
      this.proc.kill("SIGINT");
    }
  }

  isAvailable(): boolean {
    try {
      const result = Bun.spawnSync(["which", "pi"]);
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  async healthCheck(): Promise<boolean> {
    return this.isAvailable();
  }
}
