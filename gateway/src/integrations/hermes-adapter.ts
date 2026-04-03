/**
 * Hermes Agent Adapter
 * 
 * Provides WebSocket channel registration for Hermes Agent integration.
 * Allows Hermes to receive transcribed text and send commands to Echo-Node.
 */

import type { PipelineState } from '../utils/types';

export interface HermesConfig {
  enabled: boolean;
  url: string;
  channel_name: string;
  api_key?: string;
}

export interface HermesMessage {
  type: 'transcript' | 'state_change' | 'command' | 'error';
  payload: unknown;
  timestamp: number;
}

export interface HermesChannelRegistration {
  channel_name: string;
  direction: 'bidirectional' | 'input' | 'output';
  audio_format: {
    sample_rate: number;
    channels: number;
    encoding: 'pcm' | 'opus';
  };
}

type HermesCallback = (message: HermesMessage) => void;

export class HermesAdapter {
  private config: HermesConfig;
  private ws: WebSocket | null = null;
  private isConnected = false;
  private registeredChannels: Set<string> = new Set();
  private callback: HermesCallback | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private maxReconnectAttempts = 5;
  private reconnectAttempts = 0;

  constructor(config: HermesConfig) {
    this.config = config;
  }

  /**
   * Check if Hermes integration is enabled
   */
  isEnabled(): boolean {
    return this.config.enabled;
  }

  /**
   * Set message callback
   */
  onMessage(callback: HermesCallback): void {
    this.callback = callback;
  }

  /**
   * Connect to Hermes Agent
   */
  async connect(): Promise<void> {
    if (!this.config.enabled) {
      console.log('[Hermes] Integration disabled');
      return;
    }

    if (this.isConnected) {
      return;
    }

    return new Promise((resolve, reject) => {
      try {
        const url = this.config.url;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('[Hermes] Connected to Hermes Agent');
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.registerChannels();
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          console.error('[Hermes] WebSocket error:', error);
          if (!this.isConnected) {
            reject(new Error('Failed to connect to Hermes Agent'));
          }
        };

        this.ws.onclose = () => {
          console.log('[Hermes] Disconnected from Hermes Agent');
          this.isConnected = false;
          this.attemptReconnect();
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Register voice channel with Hermes
   */
  private async registerChannels(): Promise<void> {
    if (!this.ws || !this.isConnected) {
      return;
    }

    const registration: HermesChannelRegistration = {
      channel_name: this.config.channel_name,
      direction: 'bidirectional',
      audio_format: {
        sample_rate: 16000,
        channels: 1,
        encoding: 'pcm',
      },
    };

    this.send({
      type: 'register_channel',
      payload: registration,
      timestamp: Date.now(),
    });

    this.registeredChannels.add(this.config.channel_name);
    console.log(`[Hermes] Registered channel: ${this.config.channel_name}`);
  }

  /**
   * Handle incoming message from Hermes
   */
  private handleMessage(data: string | ArrayBuffer): void {
    if (typeof data !== 'string') {
      return;
    }

    try {
      const message = JSON.parse(data) as HermesMessage;
      
      if (message.type === 'command') {
        this.callback?.(message);
      }
    } catch {
      console.warn('[Hermes] Failed to parse message');
    }
  }

  /**
   * Send transcript to Hermes
   */
  sendTranscript(text: string, is_final: boolean = true): void {
    if (!this.isConnected) {
      return;
    }

    this.send({
      type: 'transcript',
      payload: {
        text,
        is_final,
        channel: this.config.channel_name,
      },
      timestamp: Date.now(),
    });
  }

  /**
   * Send state change to Hermes
   */
  sendStateChange(from: string, to: string): void {
    if (!this.isConnected) {
      return;
    }

    this.send({
      type: 'state_change',
      payload: {
        from,
        to,
        channel: this.config.channel_name,
      },
      timestamp: Date.now(),
    });
  }

  /**
   * Send error to Hermes
   */
  sendError(message: string, code: string): void {
    if (!this.isConnected) {
      return;
    }

    this.send({
      type: 'error',
      payload: {
        message,
        code,
        channel: this.config.channel_name,
      },
      timestamp: Date.now(),
    });
  }

  /**
   * Send raw message
   */
  private send(message: HermesMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Disconnect from Hermes
   */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.isConnected = false;
    this.registeredChannels.clear();
    console.log('[Hermes] Disconnected');
  }

  /**
   * Attempt reconnection
   */
  private attemptReconnect(): void {
    if (!this.config.enabled) {
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[Hermes] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = 1000 * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`[Hermes] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.connect().catch((error) => {
        console.error('[Hermes] Reconnect failed:', error);
      });
    }, delay);
  }

  /**
   * Get connection status
   */
  getStatus(): { connected: boolean; registered_channels: string[] } {
    return {
      connected: this.isConnected,
      registered_channels: Array.from(this.registeredChannels),
    };
  }
}

/**
 * Create Hermes adapter instance
 */
export function createHermesAdapter(config: HermesConfig): HermesAdapter {
  return new HermesAdapter(config);
}

/**
 * Get default Hermes configuration
 */
export function getDefaultHermesConfig(): HermesConfig {
  return {
    enabled: false,
    url: 'ws://localhost:8765',
    channel_name: 'echo-node-voice',
  };
}
