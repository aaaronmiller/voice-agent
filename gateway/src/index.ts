/**
 * Echo-Node Gateway — main entry point.
 *
 * Bun + Hono WebSocket server that relays audio and JSON events
 * between frontends (web, TUI, CLI) and voice providers.
 *
 * Run: bun run src/index.ts
 * Test: ws://localhost:3000/ws
 */

import { Hono } from "hono";
import { type ServerWebSocket } from "bun";
import { loadConfig } from "./config";
import { SessionManager } from "./session";
import { healthRoutes } from "./api/health";
import { statusRoutes } from "./api/status";
import { configRoutes } from "./api/config";
import { createProvider } from "./providers/registry";
import type { Session } from "./session";

// ── Load config ──
const config = loadConfig();
const sessions = new SessionManager(config);

// ── Create Hono app ──
const app = new Hono();

// Mount API routes
app.route("/api/health", healthRoutes(sessions));
app.route("/api/status", statusRoutes(sessions));
app.route("/api/config", configRoutes(sessions));

// CORS for web frontend
app.use("*", async (c, next) => {
  c.header("Access-Control-Allow-Origin", "*");
  c.header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS");
  c.header("Access-Control-Allow-Headers", "Content-Type");
  if (c.req.method === "OPTIONS") {
    return c.body(null, 204);
  }
  await next();
});

// Health/status at root
app.get("/", (c) => c.json({ status: "echo-node-gateway", version: "1.0.0" }));

// ── WebSocket upgrade ──
// Bun's WebSocket upgrade happens at the server level, not in Hono
// We use Bun.serve directly

console.log(`
  ╭──────────────────────────────────────╮
  │  Echo-Node Gateway                   │
  │  Port: ${String(config.port).padEnd(31)}│
  │  Provider: ${config.provider.padEnd(27)}│
  │  WebSocket: ws://${config.host}:${String(config.port).padEnd(17)}│
  ╰──────────────────────────────────────╯
`);

const server = Bun.serve<Session>({
  port: config.port,
  hostname: config.host,

  async fetch(req, server) {
    const url = new URL(req.url);

    // WebSocket upgrade
    if (url.pathname === "/ws") {
      const upgraded = server.upgrade(req, {
        data: {} as Session, // Will be set in open handler
      });
      if (upgraded) return;
      return new Response("WebSocket upgrade failed", { status: 400 });
    }

    // Route REST requests through Hono
    return app.fetch(req);
  },

  websocket: {
    async open(ws: ServerWebSocket<Session>) {
      const session = sessions.create(ws);
      ws.data = session; // Store session in WebSocket data
      console.log(`[ws] session ${session.id.slice(0, 8)} connected`);

      // Initialize the default provider
      const provider = await createProvider(config.provider, config);
      if (provider) {
        session.setProviderImpl(provider);
        provider.onMetrics((metrics) => {
          session.metrics.record(metrics);
          session.send({ type: "latency", metrics });
        });
        provider.onTranscript((text, source, final) => {
          session.send({ type: "transcript", text, source, final });
        });
        provider.onStateChange((state) => {
          session.setState(state);
        });
        console.log(`[ws] provider ${config.provider} initialized`);
      } else {
        console.log(`[ws] WARNING: provider ${config.provider} not available`);
        session.send({
          type: "error",
          message: `Provider "${config.provider}" is not available. Check your API keys.`,
        });
      }
    },

    message(ws: ServerWebSocket<Session>, message: string | ArrayBuffer) {
      ws.data.handleMessage(message);
    },

    close(ws: ServerWebSocket<Session>) {
      console.log(`[ws] session ${ws.data.id.slice(0, 8)} disconnected`);
      sessions.remove(ws.data.id);
    },

    drain(ws: ServerWebSocket<Session>) {
      // Backpressure — can be handled if needed
    },
  },
});

// ── Graceful shutdown ──
process.on("SIGINT", () => {
  console.log("\n[gateway] shutting down...");
  for (const session of sessions.getAll()) {
    session.cleanup();
  }
  server.stop();
  process.exit(0);
});

process.on("SIGTERM", () => {
  server.stop();
  process.exit(0);
});
