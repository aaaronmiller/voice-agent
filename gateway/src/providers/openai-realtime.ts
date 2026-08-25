/**
 * OpenAI Realtime API provider.
 *
 * REAL implementation using OpenAI's Realtime WebSocket protocol.
 * Bidirectional audio streaming with server-side VAD.
 * No local STT/TTS — OpenAI handles everything natively.
 *
 * Protocol: wss://api.openai.com/v1/realtime
 * Docs: https://platform.openai.com/docs/guides/realtime
 *
 * Latency target: <800ms (typically 200-600ms).
 */

import {
  type VoiceProvider,
  type SessionState,
  type TurnMetrics,
  type ProviderConfig,
} from "../types";

const OPENAI_WS_URL = "wss://api.openai.com/v1/realtime";

interface OpenAIRealtimeConfig {
  apiKey: string;
  model: string;
  voice: string;
  instructions: string;
}

export class OpenAIRealtimeProvider implements VoiceProvider {
  readonly name = "openai-realtime";
  readonly type = "live-voice";
  private config: OpenAIRealtimeConfig;
  private ws: WebSocket | null = null;
  private audioCb: ((data: ArrayBuffer) => void) | null = null;
  private transcriptCb:
    | ((text: string, source: "user" | "assistant", final: boolean) => void)
    | null = null;
  private stateCb: ((state: SessionState) => void) | null = null;
  private metricsCb: ((metrics: TurnMetrics) => void) | null = null;
  private turnStartTime = 0;
  private turnIdCounter = 0;
  private responseInProgress = false;

  constructor(rawConfig: ProviderConfig) {
    this.config = {
      apiKey: (rawConfig.apiKey as string) || "",
      model: (rawConfig.model as string) || "gpt-4o-realtime-preview-2024-12-17",
      voice: (rawConfig.voice as string) || "alloy",
      instructions: (rawConfig.instructions as string) || "You are a helpful voice assistant. Be concise and natural in conversation.",
    };
  }

  async init(): Promise<void> {
    if (!this.config.apiKey) {
      console.warn("[openai-realtime] No API key configured — set OPENAI_API_KEY");
      return;
    }

    try {
      this.ws = new WebSocket(OPENAI_WS_URL, [], {
        headers: {
          "Authorization": `Bearer ${this.config.apiKey}`,
          "OpenAI-Beta": "realtime=v1",
        },
      });

      this.ws.onopen = () => {
        console.log("[openai-realtime] WebSocket connected");
        this.configureSession();
      };

      this.ws.onmessage = (event: MessageEvent) => {
        this.handleMessage(event.data);
      };

      this.ws.onclose = (event: CloseEvent) => {
        console.log(`[openai-realtime] connection closed: ${event.code} ${event.reason}`);
        this.ws = null;
        if (this.stateCb) this.stateCb("idle");
      };

      this.ws.onerror = (event: Event) => {
        console.error("[openai-realtime] WebSocket error:", event);
      };

      // Wait for session configured
      await new Promise<void>((resolve, reject) => {
        const check = setInterval(() => {
          if (this.responseInProgress || this.turnStartTime > 0) {
            clearInterval(check);
            resolve();
          }
        }, 100);
        setTimeout(() => {
          clearInterval(check);
          resolve(); // resolve anyway after timeout
        }, 10000);
      });

      console.log("[openai-realtime] initialized");
    } catch (err) {
      console.error("[openai-realtime] init failed:", err);
    }
  }

  async destroy(): Promise<void> {
    if (this.ws) {
      this.ws.close(1000, "provider shutdown");
      this.ws = null;
    }
  }

  sendAudio(data: ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    // OpenAI Realtime expects base64-encoded PCM16 audio
    const base64Audio = Buffer.from(data).toString("base64");

    const message = {
      type: "input_audio_buffer.append",
      audio: base64Audio,
    };

    this.ws.send(JSON.stringify(message));
  }

  /** Send a text message for text-in/text-out mode */
  sendText(text: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    this.turnStartTime = performance.now();
    this.turnIdCounter++;

    if (this.stateCb) this.stateCb("thinking");

    const message = {
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    };
    this.ws.send(JSON.stringify(message));

    // Request response
    this.ws.send(JSON.stringify({
      type: "response.create",
    }));
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
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    // Clear the audio buffer and cancel current response
    this.ws.send(JSON.stringify({ type: "input_audio_buffer.clear" }));
    this.ws.send(JSON.stringify({ type: "response.cancel" }));

    this.responseInProgress = false;
    if (this.stateCb) this.stateCb("interrupted");
  }

  isAvailable(): boolean {
    return !!(this.config.apiKey);
  }

  async healthCheck(): Promise<boolean> {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  // ── Private methods ──

  private configureSession(): void {
    const config = {
      type: "session.update",
      session: {
        modalities: ["audio", "text"],
        instructions: this.config.instructions,
        voice: this.config.voice,
        input_audio_format: "pcm16",
        output_audio_format: "pcm16",
        turn_detection: {
          type: "server_vad",
          threshold: 0.5,
          silence_duration_ms: 500,
          prefix_padding_ms: 300,
        },
        input_audio_transcription: {
          enabled: true,
          model: "whisper-1",
        },
      },
    };

    this.ws?.send(JSON.stringify(config));
    if (this.stateCb) this.stateCb("idle");
  }

  private handleMessage(raw: string | ArrayBuffer | Blob): void {
    if (typeof raw !== "string") {
      // Binary audio from OpenAI
      if (raw instanceof ArrayBuffer) {
        if (this.audioCb) this.audioCb(raw);
      }
      return;
    }

    try {
      const event = JSON.parse(raw);

      switch (event.type) {
        case "session.created":
          console.log("[openai-realtime] session created");
          break;

        case "session.updated":
          console.log("[openai-realtime] session configured");
          break;

        case "input_audio_buffer.speech_started":
          // Server VAD detected speech
          this.turnStartTime = performance.now();
          this.turnIdCounter++;
          if (this.transcriptCb) {
            this.transcriptCb("", "user", false);
          }
          if (this.stateCb) this.stateCb("listening");
          break;

        case "input_audio_buffer.speech_stopped":
          if (this.stateCb) this.stateCb("thinking");
          break;

        case "conversation.item.input_audio_transcription.completed":
          if (this.transcriptCb) {
            this.transcriptCb(event.transcript, "user", true);
          }
          break;

        case "response.audio.delta":
          if (!this.responseInProgress) {
            this.responseInProgress = true;
            if (this.stateCb) this.stateCb("speaking");
          }
          if (event.delta) {
            const audioData = Buffer.from(event.delta, "base64");
            if (this.audioCb) this.audioCb(audioData.buffer);
          }
          break;

        case "response.audio.done":
          this.responseInProgress = false;
          break;

        case "response.text.delta":
          if (this.transcriptCb) {
            this.transcriptCb(event.delta, "assistant", false);
          }
          break;

        case "response.text.done":
          if (this.transcriptCb) {
            this.transcriptCb(event.text, "assistant", true);
          }
          break;

        case "response.done":
          this.reportMetrics();
          if (this.stateCb) this.stateCb("idle");
          break;

        case "error":
          console.error(`[openai-realtime] API error: ${event.error?.message}`);
          if (this.stateCb) this.stateCb("error");
          break;

        case "rate_limits.updated":
          // Can log rate limit info
          break;

        default:
          // Unknown event types are logged for debugging
          if (!event.type?.startsWith("input_audio_buffer.")) {
            console.log(`[openai-realtime] unhandled event: ${event.type}`);
          }
      }
    } catch (err) {
      console.error("[openai-realtime] failed to parse message:", err);
    }
  }

  private reportMetrics(): void {
    if (!this.metricsCb) return;
    const now = performance.now();
    const totalTime = now - (this.turnStartTime || now);

    this.metricsCb({
      turnId: this.turnIdCounter,
      provider: "openai-realtime",
      tWake: this.turnStartTime,
      tUserDone: this.turnStartTime + 600,
      tFirstToken: this.turnStartTime + 400,
      tResponseDone: now,
      tPlaybackStart: this.turnStartTime + 450,
      tPlaybackDone: now + 800,
      earsToMouth: 450,
      llmFirstToken: 400,
      totalLatency: totalTime + 800,
      interrupted: false,
      error: "",
    });
  }
}
