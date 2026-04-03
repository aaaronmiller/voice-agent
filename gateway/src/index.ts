/**
 * Echo-Node Gateway - Main Entry Point
 * 
 * Hono server on port 3000.
 * - WebSocket hub: frontend ↔ worker relay
 * - REST API: /api/health, /api/config, /api/status
 * - Static file serving for Svelte frontend (Phase 2+)
 */

import { Hono } from 'hono';
import { logger as pinoLogger } from './utils/logger';
import { loadConfig, type EchoNodeConfig } from './utils/config-loader';
import { createWebSocketHub } from './websocket';
import { createHealthRoute } from './routes/health';
import { createConfigRoutes } from './routes/config';
import { createStatusRoute } from './routes/status';
import { createPersonalitiesRoute } from './routes/personalities';
import { createAvatarsRoute } from './routes/avatars';
import { createHermesAdapter, type HermesConfig } from './integrations/hermes-adapter';
import { createOpenClawAdapter, type OpenClawConfig } from './integrations/openclaw-adapter';
import { createMCPBridge, type MCPConfig } from './integrations/mcp-bridge';
import type { PipelineState } from './utils/types';

/**
 * Gateway application state
 */
interface GatewayState {
  config: EchoNodeConfig;
  workerConnected: boolean;
  pipelineState: PipelineState;
  uptimeSeconds: number;
  sessionActive: boolean;
  personality: string;
  conversationTurns: number;
}

/**
 * Create and configure gateway application
 */
async function createGateway() {
  // Load configuration
  console.log('[Gateway] Loading configuration...');
  const config = loadConfig();
  console.log(`[Gateway] Config loaded: ${config.echo_node.name} v${config.echo_node.version}`);

  // Initialize state
  const state: GatewayState = {
    config,
    workerConnected: false,
    pipelineState: 'dormant',
    uptimeSeconds: 0,
    sessionActive: false,
    personality: config.personality.active,
    conversationTurns: 0,
  };

  // Start uptime counter
  const startTime = Date.now();
  setInterval(() => {
    state.uptimeSeconds = Math.floor((Date.now() - startTime) / 1000);
  }, 1000);

  // Create Hono app
  const app = new Hono();

  // Logging middleware
  app.use('*', async (c, next) => {
    pinoLogger.info(`${c.req.method} ${c.req.path}`);
    await next();
  });

  // CORS middleware (for local development)
  app.use('*', async (c, next) => {
    c.header('Access-Control-Allow-Origin', '*');
    c.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    c.header('Access-Control-Allow-Headers', 'Content-Type');
    await next();
  });

  // Create WebSocket hub
  const workerUrl = config.gateway.worker_url || 'ws://localhost:9001';
  const wsHub = createWebSocketHub(workerUrl);

  // Initialize integrations
  let hermesAdapter: ReturnType<typeof createHermesAdapter> | null = null;
  let openclawAdapter: ReturnType<typeof createOpenClawAdapter> | null = null;
  let mcpBridge: ReturnType<typeof createMCPBridge> | null = null;

  // Check if running in standalone mode (no integrations)
  const standaloneMode = process.env.STANDALONE === 'true' || config.ui.mode === 'headless';

  if (!standaloneMode) {
    // Initialize Hermes adapter
    if (config.integrations.hermes?.enabled) {
      hermesAdapter = createHermesAdapter(config.integrations.hermes as HermesConfig);
      hermesAdapter.onMessage((msg) => {
        console.log('[Gateway] Hermes message:', msg.type);
        wsHub.broadcastToClients(JSON.stringify(msg));
      });
      await hermesAdapter.connect();
      console.log('[Gateway] Hermes integration enabled');
    }

    // Initialize OpenClaw adapter
    if (config.integrations.openclaw?.enabled) {
      openclawAdapter = createOpenClawAdapter(config.integrations.openclaw as OpenClawConfig);
      await openclawAdapter.initialize();
      console.log('[Gateway] OpenClaw integration enabled');
    }

    // Initialize MCP bridge
    if (config.integrations.mcp?.enabled) {
      mcpBridge = createMCPBridge(config.integrations.mcp as MCPConfig);
      await mcpBridge.connect();
      console.log('[Gateway] MCP integration enabled');
    }
  } else {
    console.log('[Gateway] Running in standalone mode (integrations disabled)');
  }

  // Connect to worker
  console.log(`[Gateway] Connecting to worker at ${workerUrl}...`);
  await wsHub.connectToWorker();

  // Update worker connection status periodically
  setInterval(() => {
    const status = wsHub.getWorkerStatus();
    state.workerConnected = status.connected;
  }, 1000);

  // REST API routes
  const port = config.gateway.port || 3000;

  // GET /api/health
  app.get(
    '/api/health',
    createHealthRoute({
      workerConnected: () => state.workerConnected,
      pipelineState: () => state.pipelineState,
      uptimeSeconds: () => state.uptimeSeconds,
    })
  );

  // GET /api/config, PUT /api/config
  const configRoutes = createConfigRoutes({
    getConfig: () => state.config,
    updateConfig: async (updates) => {
      // Apply config updates with validation
      const restarted: string[] = [];
      const errors: string[] = [];

      // Validate and track provider changes
      if (updates.stt?.provider) {
        const validProviders = ['sherpa-onnx', 'faster-whisper', 'vibevoice-asr'];
        if (!validProviders.includes(updates.stt.provider)) {
          errors.push(`Invalid STT provider: ${updates.stt.provider}. Available: ${validProviders.join(', ')}`);
        } else if (updates.stt.provider !== state.config.stt.provider) {
          restarted.push('stt');
        }
      }

      if (updates.tts?.provider) {
        const validProviders = ['kokoro', 'piper', 'chatterbox', 'orpheus'];
        if (!validProviders.includes(updates.tts.provider)) {
          errors.push(`Invalid TTS provider: ${updates.tts.provider}. Available: ${validProviders.join(', ')}`);
        } else if (updates.tts.provider !== state.config.tts.provider) {
          restarted.push('tts');
        }
      }

      if (updates.llm?.provider) {
        const validProviders = ['ollama', 'openai-compat'];
        if (!validProviders.includes(updates.llm.provider)) {
          errors.push(`Invalid LLM provider: ${updates.llm.provider}. Available: ${validProviders.join(', ')}`);
        } else if (updates.llm.provider !== state.config.llm.provider) {
          restarted.push('llm');
        }
      }

      // Validate API key for cloud providers
      if (updates.llm?.provider === 'openai-compat' && !updates.llm.api_key) {
        // Check if API key is provided
        if (!state.config.llm.api_key && !updates.llm.api_key) {
          errors.push('API key required for openai-compat provider');
        }
      }

      // Validate personality changes
      if (updates.personality?.active) {
        const validPersonalities = ['hacker', 'seductive', 'butler', 'drill-sergeant', 'stoner-philosopher', 'custom'];
        if (!validPersonalities.includes(updates.personality.active)) {
          errors.push(`Invalid personality: ${updates.personality.active}. Available: ${validPersonalities.join(', ')}`);
        } else {
          // Update gateway's active personality state
          state.personality = updates.personality.active;
        }
      }

      // Return errors if any
      if (errors.length > 0) {
        throw new Error(errors.join('; '));
      }

      // Update state
      state.config = { ...state.config, ...updates };

      // Send config update to worker via WebSocket
      if (wsHub.isWorkerConnected()) {
        wsHub.handleWorkerMessage(JSON.stringify({
          type: 'config_update',
          config: updates,
        }));
      }

      return { restarted };
    },
  });
  app.get('/api/config', configRoutes.getConfig);
  app.put('/api/config', configRoutes.updateConfig);

  // GET /api/status
  app.get(
    '/api/status',
    createStatusRoute({
      getState: () => state.pipelineState,
      getSessionActive: () => state.sessionActive,
      getPersonality: () => state.personality,
      getConversationTurns: () => state.conversationTurns,
    })
  );

  // GET /api/personalities
  app.get(
    '/api/personalities',
    createPersonalitiesRoute({
      personalitiesDir: '../worker/personalities',
      getActivePersonality: () => state.personality,
    })
  );

  // GET /api/avatars
  app.get(
    '/api/avatars',
    createAvatarsRoute({
      avatarsDir: '../frontend/static/models/avatars',
    })
  );

  // WebSocket endpoint for frontend
  app.get('/ws', (c) => {
    // Upgrade to WebSocket handled by Bun
    const upgradeResult = c.upgrade({
      data: {
        onOpen: (ws: WebSocket) => {
          const clientId = crypto.randomUUID();
          wsHub.handleClientConnect(ws, clientId);
          console.log(`[Gateway] Frontend client connected: ${clientId}`);
        },
        onMessage: (ws: WebSocket, message: Buffer) => {
          const clientId = 'unknown'; // TODO: track client IDs
          try {
            const parsed = JSON.parse(message.toString());
            wsHub.handleClientMessage(clientId, parsed);
          } catch (error) {
            console.error('[Gateway] Invalid client message:', error);
          }
        },
        onClose: (ws: WebSocket) => {
          const clientId = 'unknown';
          wsHub.handleClientDisconnect(clientId);
          console.log(`[Gateway] Frontend client disconnected`);
        },
      },
    });

    return upgradeResult ? undefined : c.text('WebSocket upgrade failed', 500);
  });

  // Static file serving (Phase 2+ - frontend build)
  // app.use('/*', serveStatic({ root: '../frontend/build' }));

  // Health check for gateway itself
  app.get('/health', (c) => {
    return c.json({
      status: 'ok',
      uptime: state.uptimeSeconds,
      workers: wsHub.getClientCount(),
    });
  });

  // LAN access logging middleware
  app.use('*', async (c, next) => {
    const clientIp = c.req.header('x-forwarded-for') || c.req.header('cf-connecting-ip') || 'unknown';
    const host = c.req.header('host') || '';
    
    // Log LAN access attempts (non-localhost)
    if (state.config.gateway.bind === '0.0.0.0') {
      const isLocalhost = clientIp.startsWith('127.') || clientIp === 'localhost' || clientIp.startsWith('192.168.') || clientIp.startsWith('10.');
      
      if (!isLocalhost && clientIp !== 'unknown') {
        pinoLogger.info({
          type: 'lan_access',
          ip: clientIp,
          method: c.req.method,
          path: c.req.path,
          userAgent: c.req.header('user-agent'),
        }, 'LAN access');
      }
    }
    
    await next();
  });

  // Error handling
  app.onError((err, c) => {
    pinoLogger.error(`Error: ${err.message}`);
    return c.json(
      { error: { code: 'INTERNAL_ERROR', message: err.message } },
      500
    );
  });

  return { app, state, wsHub };
}

/**
 * Main entry point
 */
async function main() {
  console.log('[Gateway] Starting Echo-Node Gateway...');

  try {
    const { app, state, wsHub } = await createGateway();

    const port = state.config.gateway.port || 3000;
    const bind = state.config.gateway.bind || '127.0.0.1';

    console.log(`[Gateway] Server starting on http://${bind}:${port}`);

    // Start server
    const server = {
      port,
      fetch: app.fetch,
    };

    // Bun server
    Bun.serve({
      port,
      hostname: bind,
      fetch: app.fetch,
      websocket: {
        open: (ws) => {
          // Handled in route
        },
        message: (ws, message) => {
          // Handled in route
        },
        close: (ws) => {
          // Handled in route
        },
      },
    });

    console.log(`[Gateway] ✅ Gateway ready on http://${bind}:${port}`);
    console.log(`[Gateway] Worker URL: ${state.config.gateway.worker_url}`);
    console.log(`[Gateway] UI Mode: ${state.config.ui.mode}`);

    // Keep running
    await new Promise(() => {});
  } catch (error) {
    console.error('[Gateway] Fatal error:', error);
    process.exit(1);
  }
}

// Run
main().catch(console.error);
