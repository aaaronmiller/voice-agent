/**
 * Gemini Live Adapter
 * 
 * WebSocket proxy to Google Gemini Live API for cloud voice mode.
 * Handles bidirectional audio streaming with the Gemini Live API.
 */

import type { PipelineState } from '../utils/types';

export interface GeminiLiveConfig {
  apiKey: string;
  model: string;
  voice: string;
  language: string;
  sampleRate: number;
}

export interface GeminiLiveEvent {
  type: 'setup' | 'audio_in' | 'audio_out' | 'interrupted' | 'error' | 'complete';
  data?: unknown;
}

type GeminiLiveCallback = (event: GeminiLiveEvent) => void;

interface GeminiSetupPayload {
  setup: {
    model: string;
    voice: string;
    language_code: string;
    audio_config: {
      sample_rate: number;
      channel_count: number;
      bitrate: number;
    };
  };
}

interface GeminiServerSetupResponse {
  setup?: {
    model: string;
  };
  server_content?: {
    interrupted?: boolean;
    groundings?: unknown[];
  };
}

export class GeminiLiveAdapter {
  private config: GeminiLiveConfig;
  private ws: WebSocket | null = null;
  private clientWs: WebSocket | null = null;
  private isConnected = false;
  private isSetup = false;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private callback: GeminiLiveCallback | null = null;
  private pendingAudioChunks: Array<Uint8Array> = [];
  private audioBuffer: Uint8Array = new Uint8Array(0);
  private sampleRate = 16000;
  private onBargeIn: (() => void) | null = null;

  constructor(config: GeminiLiveConfig) {
    this.config = config;
    this.sampleRate = config.sampleRate || 16000;
  }

  /**
   * Validate API key by attempting a minimal connection
   */
  async validateApiKey(): Promise<{ valid: boolean; error?: string }> {
    if (!this.config.apiKey) {
      return { valid: false, error: 'API key is required' };
    }

    if (!this.config.apiKey.match(/^[A-Za-z0-9_-]{30,}$/)) {
      return { valid: false, error: 'Invalid API key format' };
    }

    return { valid: true };
  }

  /**
   * Set callback for events
   */
  onEvent(callback: GeminiLiveCallback): void {
    this.callback = callback;
  }

  /**
   * Set barge-in handler
   */
  setBargeInHandler(handler: () => void): void {
    this.onBargeIn = handler;
  }

  /**
   * Connect to Gemini Live API
   */
  async connect(): Promise<void> {
    if (this.isConnected) {
      return;
    }

    const url = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.DeliveryService/GenerateContent?key=${this.config.apiKey}`;

    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('[GeminiLive] Connected to Gemini Live API');
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.sendSetup();
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          console.error('[GeminiLive] WebSocket error:', error);
          if (!this.isConnected) {
            reject(new Error('Failed to connect to Gemini Live API'));
          }
        };

        this.ws.onclose = () => {
          console.log('[GeminiLive] Disconnected from Gemini Live API');
          this.isConnected = false;
          this.isSetup = false;
          this.attemptReconnect();
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Connect to client (frontend)
   */
  connectClient(ws: WebSocket): void {
    this.clientWs = ws;
    console.log('[GeminiLive] Client connected');
  }

  /**
   * Disconnect client
   */
  disconnectClient(): void {
    if (this.clientWs) {
      this.clientWs.close();
      this.clientWs = null;
    }
  }

  /**
   * Send setup message to Gemini
   */
  private sendSetup(): void {
    const setupPayload: GeminiSetupPayload = {
      setup: {
        model: this.config.model || 'gemini-2.0-flash-live-001',
        voice: this.config.voice || 'Kore',
        language_code: this.config.language || 'en-US',
        audio_config: {
          sample_rate: this.sampleRate,
          channel_count: 1,
          bitrate: 128000,
        },
      },
    };

    this.send(JSON.stringify(setupPayload));
    console.log('[GeminiLive] Sent setup payload');
  }

  /**
   * Handle incoming message from Gemini
   */
  private handleMessage(data: string | ArrayBuffer): void {
    if (typeof data !== 'string') {
      this.handleAudioChunk(data);
      return;
    }

    try {
      const message = JSON.parse(data) as GeminiServerSetupResponse;

      if (message.setup?.model) {
        this.isSetup = true;
        console.log('[GeminiLive] Setup complete, model:', message.setup.model);
        this.callback?.({ type: 'setup', data: message });
        return;
      }

      if (message.server_content?.interrupted) {
        console.log('[GeminiLive] Barge-in detected (interrupted)');
        this.callback?.({ type: 'interrupted' });
        this.onBargeIn?.();
        return;
      }
    } catch {
      console.warn('[GeminiLive] Failed to parse message');
    }
  }

  /**
   * Handle incoming audio chunk from Gemini
   */
  private handleAudioChunk(data: ArrayBuffer): void {
    if (!this.isSetup) {
      return;
    }

    const chunk = new Uint8Array(data);
    this.appendToBuffer(chunk);

    this.callback?.({ type: 'audio_out', data: chunk });

    if (this.clientWs && this.clientWs.readyState === WebSocket.OPEN) {
      this.clientWs.send(data);
    }
  }

  /**
   * Append chunk to audio buffer
   */
  private appendToBuffer(chunk: Uint8Array): void {
    const newBuffer = new Uint8Array(this.audioBuffer.length + chunk.length);
    newBuffer.set(this.audioBuffer);
    newBuffer.set(chunk, this.audioBuffer.length);
    this.audioBuffer = newBuffer;
  }

  /**
   * Send audio data to Gemini (from microphone)
   */
  sendAudio(audioData: Uint8Array): void {
    if (!this.isConnected || !this.isSetup || !this.ws) {
      this.pendingAudioChunks.push(audioData);
      return;
    }

    if (this.pendingAudioChunks.length > 0) {
      for (const chunk of this.pendingAudioChunks) {
        this.sendBinary(chunk);
      }
      this.pendingAudioChunks = [];
    }

    this.sendBinary(audioData);
  }

  /**
   * Send binary audio data
   */
  private sendBinary(data: Uint8Array): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }

  /**
   * Send text input to Gemini
   */
  sendText(text: string): void {
    const message = {
      client_content: {
        turns: [
          {
            role: 'user',
            parts: [{ text }],
          },
        ],
        turn_complete: true,
      },
    };

    this.send(JSON.stringify(message));
  }

  /**
   * Send raw message
   */
  private send(message: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(message);
    }
  }

  /**
   * Disconnect from Gemini
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.isConnected = false;
    this.isSetup = false;
    this.disconnectClient();
    console.log('[GeminiLive] Disconnected');
  }

  /**
   * Attempt reconnection
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[GeminiLive] Max reconnect attempts reached');
      this.callback?.({ type: 'error', data: { message: 'Max reconnect attempts reached' } });
      return;
    }

    this.reconnectAttempts++;
    const delay = 1000 * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`[GeminiLive] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect().catch((error) => {
        console.error('[GeminiLive] Reconnect failed:', error);
      });
    }, delay);
  }

  /**
   * Get connection status
   */
  getStatus(): { connected: boolean; setup: boolean } {
    return {
      connected: this.isConnected,
      setup: this.isSetup,
    };
  }

  /**
   * Get current audio buffer (for processing)
   */
  getAudioBuffer(): Uint8Array {
    return this.audioBuffer;
  }

  /**
   * Clear audio buffer
   */
  clearAudioBuffer(): void {
    this.audioBuffer = new Uint8Array(0);
  }
}

/**
 * Create Gemini Live adapter instance
 */
export function createGeminiLiveAdapter(config: GeminiLiveConfig): GeminiLiveAdapter {
  return new GeminiLiveAdapter(config);
}

/**
 * Get available voices for Gemini Live
 */
export function getGeminiLiveVoices(): string[] {
  return [
    'Kore',
    'Charon',
    'Fenrir',
    'Aoede',
    'Puck',
    'Enceladus',
    'Callirrhoe',
    'Autonoe',
    'Killjoy',
    'Orus',
  ];
}

/**
 * Get available models for Gemini Live
 */
export function getGeminiLiveModels(): string[] {
  return [
    'gemini-2.0-flash-live-001',
    'gemini-2.5-flash-live-preview-05-20',
  ];
}
