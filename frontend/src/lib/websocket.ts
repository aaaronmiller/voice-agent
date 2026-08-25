/**
 * WebSocket client for the Echo-Node gateway.
 */

import type { SessionState, ProviderInfo, TurnMetrics, MetricsSnapshot } from './types';

type MessageCallback = (data: any) => void;

export class VoiceGateway {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<MessageCallback>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private url = '';

  onStateChange(cb: (state: SessionState) => void): void { this._on('state_change', cb); }
  onTranscript(cb: (text: string, source: string, final: boolean) => void): void { this._on('transcript', cb); }
  onMetrics(cb: (m: TurnMetrics) => void): void { this._on('latency', cb); }
  onSnapshot(cb: (s: MetricsSnapshot) => void): void { this._on('latency_snapshot', cb); }
  onProviders(cb: (p: ProviderInfo[]) => void): void { this._on('providers', cb); }
  onError(cb: (msg: string) => void): void { this._on('error', cb); }
  onDisconnect(cb: () => void): void { this._on('disconnect', cb); }

  private _on(event: string, cb: MessageCallback): void {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set());
    this.handlers.get(event)!.add(cb);
  }

  connect(url: string): void {
    this.url = url;
    this._connect();
  }

  private _connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('[gateway] connected');
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.ws.onmessage = (event) => {
      if (typeof event.data !== 'string') return;
      try {
        const msg = JSON.parse(event.data);
        this._emit(msg.type, msg);
      } catch { /* ignore binary messages */ }
    };

    this.ws.onclose = () => {
      console.log('[gateway] disconnected, reconnecting in 3s...');
      this._emit('disconnect', {});
      this.reconnectTimer = setTimeout(() => this._connect(), 3000);
    };

    this.ws.onerror = () => {
      console.error('[gateway] connection error');
    };
  }

  send(msg: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  sendAudio(data: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  private _emit(event: string, data: any): void {
    const handlers = this.handlers.get(event);
    if (!handlers) return;
    for (const cb of handlers) {
      cb(data);
    }
  }
}
