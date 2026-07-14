/**
 * Gemini Live API Adapter for Echo-Node Gateway
 * 
 * Proxies bidirectional audio WebSocket to Google's Gemini Flash Live API.
 * Handles 16kHz PCM audio, VAD (server-side), and barge-in.
 */

import { WebSocket } from 'bun';

interface GeminiLiveConfig {
  apiKey: string;
  model: string;
  voiceName: string;
}

interface ClientInfo {
  id: string;
  frontendWs: WebSocket;
  geminiWs: WebSocket | null;
  connectedAt: number;
  isSpeaking: boolean;
}

/**
 * Gemini Live API Adapter
 * 
 * Manages WebSocket connections between frontend and Gemini Live API.
 * Handles:
 * - Audio streaming (16kHz PCM)
 * - Server-side VAD
 * - Barge-in detection (interrupted: true)
 * - Session management
 */
export class GeminiLiveAdapter {
  private clients: Map<string, ClientInfo> = new Map();
  private config: GeminiLiveConfig;
  private readonly GEMINI_WS_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent';

  constructor(config: GeminiLiveConfig) {
    this.config = config;
  }

  /**
   * Validate API key is present
   */
  static validateConfig(apiKey: string): { valid: boolean; error?: string } {
    if (!apiKey || apiKey.trim() === '') {
      return {
        valid: false,
        error: 'Gemini API key is required for cloud mode. Set llm.api_key in config.yaml.',
      };
    }
    return { valid: true };
  }

  /**
   * Handle new frontend client connection
   */
  handleClientConnect(ws: WebSocket, clientId: string): void {
    const client: ClientInfo = {
      id: clientId,
      frontendWs: ws,
      geminiWs: null,
      connectedAt: Date.now(),
      isSpeaking: false,
    };

    this.clients.set(clientId, client);
    console.log(`[GeminiLive] Client connected: ${clientId}`);

    // Send connected message
    ws.send(JSON.stringify({
      type: 'gemini_connected',
      client_id: clientId,
    }));
  }

  /**
   * Handle client disconnection
   */
  handleClientDisconnect(clientId: string): void {
    const client = this.clients.get(clientId);
    if (client?.geminiWs) {
      client.geminiWs.close();
    }
    this.clients.delete(clientId);
    console.log(`[GeminiLive] Client disconnected: ${clientId}`);
  }

  /**
   * Handle message from frontend client
   */
  async handleClientMessage(clientId: string, message: string): Promise<void> {
    const client = this.clients.get(clientId);
    if (!client) return;

    try {
      const data = JSON.parse(message);

      switch (data.type) {
        case 'start_session':
          await this.startGeminiSession(client);
          break;

        case 'stop_session':
          await this.stopGeminiSession(client);
          break;

        case 'barge_in':
          await this.handleBargeIn(client);
          break;

        case 'audio_chunk':
          // Forward audio chunk to Gemini
          if (client.geminiWs && client.geminiWs.readyState === 1) {
            client.geminiWs.send(JSON.stringify({
              realtime_input: {
                media_chunks: [{
                  mimeType: 'audio/pcm;rate=16000',
                  data: data.audio, // base64 encoded PCM audio
                }],
              },
            }));
          }
          break;

        default:
          console.log(`[GeminiLive] Unknown message type: ${data.type}`);
      }
    } catch (error) {
      console.error(`[GeminiLive] Error handling message from ${clientId}:`, error);
    }
  }

  /**
   * Start Gemini Live session for a client
   */
  private async startGeminiSession(client: ClientInfo): Promise<void> {
    if (client.geminiWs) {
      console.log(`[GeminiLive] Session already active for ${client.id}`);
      return;
    }

    const wsUrl = `${this.GEMINI_WS_URL}?key=${this.config.apiKey}`;

    try {
      const geminiWs = new WebSocket(wsUrl);

      geminiWs.onopen = () => {
        console.log(`[GeminiLive] Gemini connected for ${client.id}`);

        // Send setup payload
        geminiWs.send(JSON.stringify({
          setup: {
            model: `models/${this.config.model || 'gemini-2.0-flash-exp'}`,
            generationConfig: {
              responseModalities: ['AUDIO'],
              speechConfig: {
                voiceConfig: {
                  prebuiltVoiceConfig: {
                    voiceName: this.config.voiceName || 'Puck',
                  },
                },
              },
            },
          },
        }));

        client.geminiWs = geminiWs;

        // Notify frontend
        client.frontendWs.send(JSON.stringify({
          type: 'gemini_session_started',
          client_id: client.id,
        }));
      };

      geminiWs.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(typeof event.data === 'string' ? event.data : '');

          // Handle server content (audio response)
          if (data.serverContent) {
            // Check for barge-in/interruption
            if (data.serverContent.interrupted) {
              console.log(`[GeminiLive] Barge-in detected for ${client.id}`);
              client.isSpeaking = false;
              client.frontendWs.send(JSON.stringify({
                type: 'barge_in_ack',
              }));
              return;
            }

            // Check for model turn (audio response)
            if (data.serverContent.modelTurn) {
              const parts = data.serverContent.modelTurn.parts;
              for (const part of parts) {
                if (part.inlineData && part.inlineData.data) {
                  // Forward audio to frontend
                  client.frontendWs.send(JSON.stringify({
                    type: 'gemini_audio',
                    audio: part.inlineData.data,
                    mimeType: 'audio/pcm',
                  }));
                  client.isSpeaking = true;
                }
              }
            }

            // Turn complete
            if (data.serverContent.turnComplete) {
              client.isSpeaking = false;
              client.frontendWs.send(JSON.stringify({
                type: 'gemini_turn_complete',
              }));
            }
          }
        } catch (error) {
          console.error(`[GeminiLive] Error parsing Gemini response:`, error);
        }
      };

      geminiWs.onclose = () => {
        console.log(`[GeminiLive] Gemini disconnected for ${client.id}`);
        client.geminiWs = null;
        client.isSpeaking = false;

        client.frontendWs.send(JSON.stringify({
          type: 'gemini_disconnected',
          client_id: client.id,
        }));
      };

      geminiWs.onerror = (error) => {
        console.error(`[GeminiLive] Gemini error for ${client.id}:`, error);
        client.frontendWs.send(JSON.stringify({
          type: 'error',
          message: 'Gemini connection failed',
          code: 'GEMINI_CONNECTION_ERROR',
        }));
      };
    } catch (error) {
      console.error(`[GeminiLive] Failed to start Gemini session for ${client.id}:`, error);
      client.frontendWs.send(JSON.stringify({
        type: 'error',
        message: 'Failed to connect to Gemini API',
        code: 'GEMINI_CONNECTION_ERROR',
      }));
    }
  }

  /**
   * Stop Gemini Live session for a client
   */
  private async stopGeminiSession(client: ClientInfo): Promise<void> {
    if (client.geminiWs) {
      client.geminiWs.close();
      client.geminiWs = null;
      client.isSpeaking = false;

      client.frontendWs.send(JSON.stringify({
        type: 'gemini_session_stopped',
        client_id: client.id,
      }));

      console.log(`[GeminiLive] Session stopped for ${client.id}`);
    }
  }

  /**
   * Handle barge-in (user speaks while Gemini is responding)
   */
  private async handleBargeIn(client: ClientInfo): Promise<void> {
    if (!client.isSpeaking) return;

    console.log(`[GeminiLive] Barge-in triggered for ${client.id}`);

    // Send stop signal to Gemini (interrupts current generation)
    if (client.geminiWs && client.geminiWs.readyState === 1) {
      client.geminiWs.send(JSON.stringify({
        clientContent: {
          turns: [{
            role: 'user',
            parts: [{ text: '' }],
          }],
          turnComplete: true,
        },
      }));
    }

    client.isSpeaking = false;

    client.frontendWs.send(JSON.stringify({
      type: 'barge_in_ack',
    }));
  }

  /**
   * Get active client count
   */
  getClientCount(): number {
    return this.clients.size;
  }

  /**
   * Cleanup - close all connections
   */
  shutdown(): void {
    for (const client of this.clients.values()) {
      if (client.geminiWs) {
        client.geminiWs.close();
      }
      client.frontendWs.close();
    }
    this.clients.clear();
    console.log('[GeminiLive] All connections closed');
  }
}

/**
 * Create Gemini Live adapter instance
 */
export function createGeminiLiveAdapter(config: {
  apiKey: string;
  model?: string;
  voiceName?: string;
}): GeminiLiveAdapter {
  return new GeminiLiveAdapter({
    apiKey: config.apiKey,
    model: config.model || 'gemini-2.0-flash-exp',
    voiceName: config.voiceName || 'Puck',
  });
}
