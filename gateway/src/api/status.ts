import { Hono } from "hono";
import { type SessionManager } from "../session";

export function statusRoutes(sessions: SessionManager) {
  const app = new Hono();

  app.get("/", (c) => {
    const global = sessions.getGlobalSnapshot();
    const allSessions = sessions.getAll().map((s) => ({
      id: s.id.slice(0, 8),
      state: s.state,
      provider: s.provider,
      turnCount: s.metrics.recent(1000).length,
    }));

    return c.json({
      sessions: allSessions,
      global,
      config: {
        provider: sessions.getAll()[0]?.provider || "none",
      },
    });
  });

  return app;
}
