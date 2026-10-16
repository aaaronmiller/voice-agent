/**
 * WebSocket connection state store for Echo-Node
 * Uses Svelte 5 $state runes for reactivity
 */

export type WebSocketStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface WebSocketMessage {
  type: string;
  [key: string]: unknown;
}

class WebSocketStore {
  #socket: WebSocket | null = null;
  #reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  #reconnectAttempts = 0;
  #maxReconnectAttempts = 5;
  #reconnectDelay = 1000;

  status = $state<WebSocketStatus>('disconnected');
  error = $state<string | null>(null);
  lastMessage = $state<WebSocketMessage | null>(null);

  #listeners = new Map<string, Set<(data: WebSocketMessage) => void>>();

  constructor() {
    this.#reconnectAttempts = 0;
  }

  /**
   * Subscribe to a specific event type
   */
  on(eventType: string, callback: (data: WebSocketMessage) => void): () => void {
    if (!this.#listeners.has(eventType)) {
      this.#listeners.set(eventType, new Set());
    }
    this.#listeners.get(eventType)!.add(callback);

    // Return unsubscribe function
    return () => {
      this.#listeners.get(eventType)?.delete(callback);
    };
  }

  /**
   * Connect to the WebSocket server
   */
  connect(url: string = 'ws://localhost:3000/ws'): void {
    if (this.#socket?.readyState === WebSocket.OPEN) {
      return;
    }

    this.status = 'connecting';
    this.error = null;

    try {
      this.#socket = new WebSocket(url);

      this.#socket.onopen = () => {
        this.status = 'connected';
        this.#reconnectAttempts = 0;
        console.log('[WebSocket] Connected to gateway');
      };

      this.#socket.onclose = (event) => {
        this.status = 'disconnected';
        this.#socket = null;
        console.log('[WebSocket] Disconnected:', event.code, event.reason);

        // Attempt reconnection
        if (this.#reconnectAttempts < this.#maxReconnectAttempts) {
          this.#scheduleReconnect(url);
        }
      };

      this.#socket.onerror = (event) => {
        this.error = 'WebSocket connection error';
        console.error('[WebSocket] Error:', event);
      };

      this.#socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketMessage;
          this.lastMessage = data;
          this.#emit(data.type, data);
          // Also emit wildcard for generic listeners
          this.#emit('*', data);
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err);
        }
      };
    } catch (err) {
      this.status = 'error';
      this.error = err instanceof Error ? err.message : 'Unknown connection error';
      this.#scheduleReconnect(url);
    }
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect(): void {
    this.#reconnectAttempts = this.#maxReconnectAttempts; // Prevent reconnection

    if (this.#reconnectTimer) {
      clearTimeout(this.#reconnectTimer);
      this.#reconnectTimer = null;
    }

    if (this.#socket) {
      this.#socket.close(1000, 'Client disconnect');
      this.#socket = null;
    }

    this.status = 'disconnected';
  }

  /**
   * Send a message to the WebSocket server
   */
  send(message: WebSocketMessage): boolean {
    if (this.#socket?.readyState === WebSocket.OPEN) {
      this.#socket.send(JSON.stringify(message));
      return true;
    }
    console.warn('[WebSocket] Cannot send - not connected');
    return false;
  }

  /**
   * Check if connected
   */
  get isConnected(): boolean {
    return this.status === 'connected';
  }

  #scheduleReconnect(url: string): void {
    if (this.#reconnectTimer) {
      clearTimeout(this.#reconnectTimer);
    }

    const delay = this.#reconnectDelay * Math.pow(2, this.#reconnectAttempts);
    this.#reconnectAttempts++;

    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.#reconnectAttempts}/${this.#maxReconnectAttempts})`);

    this.#reconnectTimer = setTimeout(() => {
      this.connect(url);
    }, delay);
  }

  #emit(eventType: string, data: WebSocketMessage): void {
    // Emit to specific event listeners
    this.#listeners.get(eventType)?.forEach((callback) => {
      try {
        callback(data);
      } catch (err) {
        console.error(`[WebSocket] Listener error for ${eventType}:`, err);
      }
    });
  }
}

// Singleton instance
export const websocketStore = new WebSocketStore();

// Hook for Svelte 5 components
export function useWebSocket() {
  return websocketStore;
}
