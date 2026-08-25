/**
 * Python Worker Bridge — connects the gateway to the existing
 * assistant_v2.py process via WebSocket or stdio.
 *
 * This is the REAL bridge that lets the legacy pipeline
 * (STT→LLM→TTS) function through the gateway, enabling
 * A/B testing against live-voice providers.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  type VoiceProvider,
  type SessionState,
  type TurnMetrics,
  type ProviderConfig,
} from "../types";

const GATEWAY_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PROJECT_ROOT = resolve(GATEWAY_DIR, "..");

interface WorkerMessage {
  type: string;
  [key: string]: unknown;
}

export class PythonWorkerProvider implements VoiceProvider {
  readonly name = "python-worker";
  readonly type = "legacy";
  private config: ProviderConfig;
  private proc: ChildProcess | null = null;
  private audioCb: ((data: ArrayBuffer) => void) | null = null;
  private transcriptCb:
    | ((text: string, source: "user" | "assistant", final: boolean) => void)
    | null = null;
  private stateCb: ((state: SessionState) => void) | null = null;
  private metricsCb: ((metrics: TurnMetrics) => void) | null = null;
  private buffer = "";

  constructor(config: ProviderConfig) {
    this.config = config;
  }

  async init(): Promise<void> {
    const pythonPath = this.config.pythonPath as string || "python3";
    const workerPath = resolve(PROJECT_ROOT, "v2", "worker_bridge.py");

    console.log(`[python-worker] spawning: ${pythonPath} ${workerPath}`);

    this.proc = spawn(pythonPath, [workerPath, "--gateway-port", "3000"], {
      cwd: resolve(PROJECT_ROOT, "v2"),
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        ECHO_NODE_GATEWAY: "ws://127.0.0.1:3000/ws/worker",
        PYTHONUNBUFFERED: "1",
      },
    });

    this.proc.stdout?.on("data", (data: Buffer) => {
      this.handleWorkerOutput(data.toString());
    });

    this.proc.stderr?.on("data", (data: Buffer) => {
      console.error(`[python-worker/stderr] ${data.toString().trim()}`);
    });

    this.proc.on("exit", (code) => {
      console.log(`[python-worker] exited with code ${code}`);
      this.proc = null;
    });

    console.log("[python-worker] initialized");
  }

  async destroy(): Promise<void> {
    if (this.proc) {
      this.proc.kill("SIGTERM");
      setTimeout(() => {
        if (this.proc) this.proc.kill("SIGKILL");
      }, 5000);
    }
  }

  sendAudio(data: ArrayBuffer): void {
    if (this.proc?.stdin?.writable) {
      // Forward raw PCM16 audio to the Python worker
      // Format: 4-byte length prefix + PCM16 data
      const header = Buffer.alloc(4);
      header.writeUInt32BE(data.byteLength);
      this.proc.stdin.write(Buffer.concat([header, Buffer.from(data)]));
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
    if (this.proc?.stdin?.writable) {
      const msg = JSON.stringify({ type: "interrupt" }) + "\n";
      this.proc.stdin.write(msg);
    }
  }

  isAvailable(): boolean {
    // Python worker is available if Python3 exists
    try {
      const result = Bun.spawnSync(["python3", "--version"]);
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  async healthCheck(): Promise<boolean> {
    return this.proc !== null && this.proc.exitCode === null;
  }

  private handleWorkerOutput(line: string): void {
    // The worker sends JSON-Lines over stdout
    this.buffer += line;
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() || "";

    for (const raw of lines) {
      if (!raw.trim()) continue;
      try {
        const msg: WorkerMessage = JSON.parse(raw);
        this.handleWorkerMessage(msg);
      } catch {
        // Skip non-JSON lines (debug output)
        console.log(`[python-worker] ${raw}`);
      }
    }
  }

  private handleWorkerMessage(msg: WorkerMessage): void {
    switch (msg.type) {
      case "state_change":
        if (this.stateCb) this.stateCb(msg.state as SessionState);
        break;

      case "transcript":
        if (this.transcriptCb) {
          this.transcriptCb(
            msg.text as string,
            msg.source as "user" | "assistant",
            msg.final as boolean
          );
        }
        break;

      case "audio":
        if (this.audioCb && msg.data) {
          const audio = Buffer.from(msg.data as string, "base64");
          this.audioCb(audio.buffer);
        }
        break;

      case "metrics":
        if (this.metricsCb) {
          this.metricsCb(msg.metrics as unknown as TurnMetrics);
        }
        break;

      case "error":
        console.error(`[python-worker] error: ${msg.message}`);
        break;

      default:
        console.log(`[python-worker] unknown message: ${msg.type}`);
    }
  }
}
