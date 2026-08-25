import { Hono } from "hono";
import { type SessionManager } from "../session";

export function healthRoutes(sessions: SessionManager) {
  const app = new Hono();

  app.get("/", (c) => {
    return c.json({
      status: "ok",
      uptime: process.uptime(),
      sessions: sessions.getAll().length,
      timestamp: new Date().toISOString(),
    });
  });

  return app;
}
