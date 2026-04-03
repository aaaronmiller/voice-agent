/**
 * WebSocket Hub for Echo-Node Gateway
 * 
 * Relays messages between frontend clients and Python worker.
 * Handles session management and event broadcasting.
 * Supports ESP32 binary protocol for embedded devices.
 */

import { createSessionManager, SessionManager } from './sessions/session-manager';
import type { PipelineState } from './utils/types';

interface ClientInfo {
  id: string;
  ws: WebSocket;
  connectedAt: number;
  lastActivity: number;
}

interface ESP32Frame {
  type: number;
  sequence: number;
  length: number;
  payload: Uint8Array;
}

const ESP32_PROTOCOL = {
  AUDIO_IN: 0x01,
  AUDIO_OUT: 0x02,
  COMMAND: 0x03,
  STATUS: 0x04,
  PING: 0x05,
  PONG: 0x06,
  HEADER_SIZE: 4,
};

function parseESP32Frame(data: Uint8Array): ESP32Frame | null {
  if (data.length < ESP32_PROTOCOL.HEADER_SIZE) {
    return null;
  }

  const type = data[0];
  const sequence = data[1];
  const length = (data[2] << 8) | data[3];
  
  if (data.length < ESP32_PROTOCOL.HEADER_SIZE + length) {
    return null;
  }

  const payload = data.slice(ESP32_PROTOCOL.HEADER_SIZE, ESP32_PROTOCOL.HEADER_SIZE + length);
  
  return { type, sequence, length, payload };
}

function createESP32Frame(type: number, sequence: number, payload: Uint8Array): Uint8Array {
  const frame = new Uint8Array(ESP32_PROTOCOL.HEADER_SIZE + payload.length);
  frame[0] = type;
  frame[1] = sequence;
  frame[2] = (payload.length >> 8) & 0xFF;
  frame[3] = payload.length & 0xFF;
  frame.set(payload, ESP32_PROTOCOL.HEADER_SIZE);
  return frame;
}

/**
 * WebSocket Hub - manages connections between frontend and worker
 */
export class WebSocketHub {
  private clients: Map<string, ClientInfo> = new Map();
  private esp32Clients: Map<string, { ws: WebSocket; lastPing: number; sequence: number }> = new Map();
  private workerConnection: WebSocket | null = null;
  private workerUrl: string;
  private sessionManager: SessionManager;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;  // ms

  constructor(workerUrl: string) {
    this.workerUrl = workerUrl;
    this.sessionManager = createSessionManager(15, 30000);
  }

  /**
   * Connect to Python worker
   */
  async connectToWorker(): Promise<void> {
    try {
      // Use Bun's WebSocket via upgrade (client connection not directly supported)
      // For now, mark as connected - worker will initiate
      console.log('[WebSocketHub] Worker connection deferred (Bun limitation)');
      this.workerConnection = null;
      this.reconnectAttempts = 0;
    } catch (error) {
      console.error('[WebSocketHub] Failed to connect to worker:', error);
      this.attemptReconnect();
    }
  }

  /**
   * Handle message from worker (relay to all clients)
   */
  handleWorkerMessage(message: string): void {
    try {
      const event = JSON.parse(message);
      
      // Update session state based on event type
      if (event.type === 'state_change') {
        this.sessionManager.updateState(event.to as PipelineState);
      } else if (event.type === 'transcript_final') {
        // Will be paired with llm_complete to add full turn
        this.sessionManager.getInfo(); // Just tracking for now
      } else if (event.type === 'llm_complete') {
        // Add turn to history (would need transcript stored)
        // For now, just update activity
        const session = this.sessionManager.getSession();
        if (session) {
          session.lastActivity = Date.now();
        }
      } else if (event.type === 'ready') {
        console.log('[WebSocketHub] Worker ready');
      }
      
      // Broadcast to all clients
      this.broadcastToClients(event);
    } catch (error) {
      console.error('[WebSocketHub] Error handling worker message:', error);
    }
  }

  /**
   * Attempt to reconnect to worker with exponential backoff
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WebSocketHub] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`[WebSocketHub] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => this.connectToWorker(), delay);
  }

  /**
   * Handle new client connection
   */
  handleClientConnect(ws: WebSocket, clientId: string): void {
    const clientInfo: ClientInfo = {
      id: clientId,
      ws,
      connectedAt: Date.now(),
      lastActivity: Date.now(),
    };

    this.clients.set(clientId, clientInfo);
    console.log(`[WebSocketHub] Client connected: ${clientId} (${this.clients.size} total)`);

    // Send current state to new client
    if (this.workerConnection) {
      this.sendToClient(ws, { type: 'worker_connected' });
    }
  }

  /**
   * Handle client disconnection
   */
  handleClientDisconnect(clientId: string): void {
    this.clients.delete(clientId);
    console.log(`[WebSocketHub] Client disconnected: ${clientId} (${this.clients.size} remaining)`);
  }

  /**
   * Handle message from client
   */
  handleClientMessage(clientId: string, message: unknown): void {
    const client = this.clients.get(clientId);
    if (!client) return;

    client.lastActivity = Date.now();

    // Relay client message to worker
    if (this.workerConnection) {
      this.workerConnection.send(JSON.stringify(message));
    } else {
      this.sendToClient(client.ws, {
        type: 'error',
        message: 'Worker not connected',
        code: 'WORKER_UNAVAILABLE',
      });
    }
  }

  /**
   * Send message to specific client
   */
  private sendToClient(ws: WebSocket, message: unknown): void {
    try {
      ws.send(JSON.stringify(message));
    } catch (error) {
      console.error('[WebSocketHub] Failed to send to client:', error);
    }
  }

  /**
   * Broadcast message to all connected clients
   */
  private broadcastToClients(message: unknown): void {
    const messageStr = typeof message === 'string' ? message : JSON.stringify(message);
    
    for (const client of this.clients.values()) {
      this.sendToClient(client.ws, messageStr);
    }
  }

  /**
   * Broadcast system message (not from worker)
   */
  private broadcastSystemMessage(message: unknown): void {
    this.broadcastToClients(message);
  }

  /**
   * Get connected client count
   */
  getClientCount(): number {
    return this.clients.size;
  }

  /**
   * Check if worker is connected
   */
  isWorkerConnected(): boolean {
    return this.workerConnection !== null;
  }

  /**
   * Get worker connection status
   */
  getWorkerStatus(): { connected: boolean; client_count: number } {
    return {
      connected: this.workerConnection !== null,
      client_count: this.getClientCount(),
    };
  }

  /**
   * Get session manager
   */
  getSessionManager(): SessionManager {
    return this.sessionManager;
  }

  /**
   * Register ESP32 client
   */
  registerESP32Client(clientId: string, ws: WebSocket): void {
    this.esp32Clients.set(clientId, {
      ws,
      lastPing: Date.now(),
      sequence: 0,
    });
    console.log(`[WebSocketHub] ESP32 client registered: ${clientId}`);
  }

  /**
   * Handle ESP32 binary message
   */
  handleESP32Message(clientId: string, data: ArrayBuffer): void {
    const client = this.esp32Clients.get(clientId);
    if (!client) return;

    const frame = parseESP32Frame(new Uint8Array(data));
    if (!frame) return;

    switch (frame.type) {
      case ESP32_PROTOCOL.PING:
        client.lastPing = Date.now();
        client.sequence = frame.sequence;
        const pong = createESP32Frame(ESP32_PROTOCOL.PONG, frame.sequence, new Uint8Array(0));
        client.ws.send(pong);
        break;

      case ESP32_PROTOCOL.AUDIO_IN:
        if (this.workerConnection) {
          this.workerConnection.send(data);
        }
        break;

      case ESP32_PROTOCOL.STATUS:
        console.log(`[WebSocketHub] ESP32 status: ${frame.payload.length} bytes`);
        break;

      default:
        console.warn(`[WebSocketHub] Unknown ESP32 frame type: ${frame.type}`);
    }
  }

  /**
   * Send audio to ESP32 client
   */
  sendAudioToESP32(clientId: string, audioData: Uint8Array): void {
    const client = this.esp32Clients.get(clientId);
    if (!client) return;

    const frame = createESP32Frame(ESP32_PROTOCOL.AUDIO_OUT, client.sequence++, audioData);
    try {
      client.ws.send(frame);
    } catch (error) {
      console.error('[WebSocketHub] Failed to send audio to ESP32:', error);
    }
  }

  /**
   * Check ESP32 client health
   */
  private checkESP32Clients(): void {
    const now = Date.now();
    const timeout = 30000;

    for (const [clientId, client] of this.esp32Clients.entries()) {
      if (now - client.lastPing > timeout) {
        console.log(`[WebSocketHub] ESP32 client timed out: ${clientId}`);
        client.ws.close();
        this.esp32Clients.delete(clientId);
      }
    }
  }

  /**
   * Cleanup - close all connections
   */
  shutdown(): void {
    // Close worker connection
    if (this.workerConnection) {
      this.workerConnection.close();
      this.workerConnection = null;
    }

    // Close all client connections
    for (const client of this.clients.values()) {
      client.ws.close();
    }
    this.clients.clear();

    // Close ESP32 connections
    for (const client of this.esp32Clients.values()) {
      client.ws.close();
    }
    this.esp32Clients.clear();
  }
}

/**
 * Create WebSocket hub instance
 */
export function createWebSocketHub(workerUrl: string): WebSocketHub {
  return new WebSocketHub(workerUrl);
}
