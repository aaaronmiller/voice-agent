/**
 * Session Manager for Echo-Node Gateway
 * 
 * Manages active sessions with connected clients.
 * Supports remote terminal (thin-client) mode for LAN access.
 */

import { v4 as uuidv4 } from 'uuid';
import type { PipelineState, Turn, Session } from '../utils/types';

/**
 * Session state
 */
interface SessionState {
  id: string;
  clientId: string;
  startedAt: number;
  personality: string;
  conversationHistory: Turn[];
  currentState: PipelineState;
  lastActivity: number;
}

/**
 * Remote terminal client info
 */
interface RemoteClient {
  id: string;
  address: string;
  connectedAt: number;
  lastActivity: number;
  authenticated: boolean;
  mode: 'web' | 'terminal';
}

/**
 * Session Manager - manages active voice sessions
 * 
 * MVP Implementation:
 * - Single active session at a time
 * - Conversation history (up to 15 turns)
 * - No cross-session persistence
 * - Remote terminal thin-client support
 */
export class SessionManager {
  private activeSession: SessionState | null = null;
  private maxTurns: number = 15;
  private timeoutMs: number = 30000; // 30 second inactivity timeout
  private remoteClients: Map<string, RemoteClient> = new Map();
  private apiKey: string = '';

  constructor(maxTurns: number = 15, timeoutMs: number = 30000) {
    this.maxTurns = maxTurns;
    this.timeoutMs = timeoutMs;
  }

  /**
   * Set API key for remote terminal authentication
   */
  setApiKey(key: string): void {
    this.apiKey = key;
  }

  /**
   * Authenticate remote terminal client
   */
  authenticateRemoteClient(clientId: string, address: string, apiKey: string): boolean {
    if (this.apiKey && apiKey !== this.apiKey) {
      console.log(`[SessionManager] Remote auth failed from ${address}`);
      return false;
    }

    const client: RemoteClient = {
      id: clientId,
      address,
      connectedAt: Date.now(),
      lastActivity: Date.now(),
      authenticated: !this.apiKey || apiKey === this.apiKey,
      mode: 'terminal',
    };

    this.remoteClients.set(clientId, client);
    console.log(`[SessionManager] Remote terminal authenticated: ${address}`);
    return true;
  }

  /**
   * Register remote terminal (without API key - requires auth later)
   */
  registerRemoteClient(clientId: string, address: string): RemoteClient {
    const client: RemoteClient = {
      id: clientId,
      address,
      connectedAt: Date.now(),
      lastActivity: Date.now(),
      authenticated: !this.apiKey, // Auto-auth if no key set
      mode: 'terminal',
    };

    this.remoteClients.set(clientId, client);
    console.log(`[SessionManager] Remote terminal registered: ${address}`);
    return client;
  }

  /**
   * Get remote client
   */
  getRemoteClient(clientId: string): RemoteClient | undefined {
    return this.remoteClients.get(clientId);
  }

  /**
   * Check if client is authenticated
   */
  isClientAuthenticated(clientId: string): boolean {
    const client = this.remoteClients.get(clientId);
    return client?.authenticated || false;
  }

  /**
   * Get all remote clients
   */
  getRemoteClients(): RemoteClient[] {
    return Array.from(this.remoteClients.values());
  }

  /**
   * Disconnect remote client
   */
  disconnectRemoteClient(clientId: string): void {
    this.remoteClients.delete(clientId);
    console.log(`[SessionManager] Remote terminal disconnected: ${clientId}`);
  }

  /**
   * Update remote client activity
   */
  updateRemoteClientActivity(clientId: string): void {
    const client = this.remoteClients.get(clientId);
    if (client) {
      client.lastActivity = Date.now();
    }
  }

  /**
   * Check for remote client timeouts
   */
  checkRemoteClientTimeouts(): string[] {
    const timedOut: string[] = [];
    const now = Date.now();
    const timeout = 60000; // 60 seconds for remote clients

    for (const [clientId, client] of this.remoteClients.entries()) {
      if (now - client.lastActivity > timeout) {
        timedOut.push(clientId);
        this.remoteClients.delete(clientId);
        console.log(`[SessionManager] Remote terminal timed out: ${client.address}`);
      }
    }

    return timedOut;
  }

  /**
   * Get remote client count
   */
  getRemoteClientCount(): number {
    return this.remoteClients.size;
  }

  constructor(maxTurns: number = 15, timeoutMs: number = 30000) {
    this.maxTurns = maxTurns;
    this.timeoutMs = timeoutMs;
  }

  /**
   * Start a new session
   */
  startSession(clientId: string, personality: string = 'hacker'): string {
    // End existing session if any
    if (this.activeSession) {
      this.endSession();
    }

    const session: SessionState = {
      id: uuidv4(),
      clientId,
      startedAt: Date.now(),
      personality,
      conversationHistory: [],
      currentState: 'dormant',
      lastActivity: Date.now(),
    };

    this.activeSession = session;
    console.log(`[SessionManager] New session started: ${session.id}`);
    
    return session.id;
  }

  /**
   * End current session
   */
  endSession(): void {
    if (this.activeSession) {
      console.log(`[SessionManager] Session ended: ${this.activeSession.id}`);
      this.activeSession = null;
    }
  }

  /**
   * Get current session
   */
  getSession(): SessionState | null {
    return this.activeSession;
  }

  /**
   * Check if session is active
   */
  isSessionActive(): boolean {
    return this.activeSession !== null;
  }

  /**
   * Update session state
   */
  updateState(state: PipelineState): void {
    if (this.activeSession) {
      this.activeSession.currentState = state;
      this.activeSession.lastActivity = Date.now();
    }
  }

  /**
   * Add conversation turn
   */
  addTurn(userTranscript: string, assistantResponse: string): void {
    if (!this.activeSession) return;

    const turn: Turn = {
      turn_number: this.activeSession.conversationHistory.length + 1,
      user_transcript: userTranscript,
      assistant_response: assistantResponse,
      timestamp: Date.now(),
    };

    this.activeSession.conversationHistory.push(turn);

    // Evict oldest turns if exceeding limit
    while (this.activeSession.conversationHistory.length > this.maxTurns) {
      this.activeSession.conversationHistory.shift();
    }

    this.activeSession.lastActivity = Date.now();
  }

  /**
   * Update personality
   */
  updatePersonality(personality: string): void {
    if (this.activeSession) {
      this.activeSession.personality = personality;
      this.activeSession.lastActivity = Date.now();
    }
  }

  /**
   * Check for timeout
   */
  checkTimeout(): boolean {
    if (!this.activeSession) return false;

    const elapsed = Date.now() - this.activeSession.lastActivity;
    if (elapsed > this.timeoutMs) {
      console.log(`[SessionManager] Session timeout after ${elapsed}ms`);
      this.endSession();
      return true;
    }

    return false;
  }

  /**
   * Get session info for API
   */
  getInfo() {
    if (!this.activeSession) {
      return {
        active: false,
        state: 'dormant',
        turns: 0,
        personality: null,
      };
    }

    return {
      active: true,
      id: this.activeSession.id,
      state: this.activeSession.currentState,
      turns: this.activeSession.conversationHistory.length,
      personality: this.activeSession.personality,
      uptime: Date.now() - this.activeSession.startedAt,
    };
  }

  /**
   * Get conversation history for LLM context
   */
  getConversationHistory(): Turn[] {
    return this.activeSession?.conversationHistory || [];
  }

  /**
   * Clear conversation history (keep session)
   */
  clearHistory(): void {
    if (this.activeSession) {
      this.activeSession.conversationHistory = [];
    }
  }
}

/**
 * Create session manager instance
 */
export function createSessionManager(maxTurns?: number, timeoutMs?: number): SessionManager {
  return new SessionManager(maxTurns, timeoutMs);
}
