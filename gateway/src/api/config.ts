import { Hono } from "hono";
import { loadConfig, listAvailableProviders } from "../config";
import { type SessionManager } from "../session";

export function configRoutes(sessions: SessionManager) {
  const app = new Hono();

  // GET /api/config — return current config (redact secrets)
  app.get("/", (c) => {
    const config = loadConfig();
    // Redact API keys
    const safe = JSON.parse(JSON.stringify(config));
    for (const key of Object.keys(safe.providers)) {
      if (safe.providers[key].apiKey) {
        safe.providers[key].apiKey = "***";
      }
    }
    safe.availableProviders = listAvailableProviders(config);
    return c.json(safe);
  });

  // GET /api/config/providers — list available providers
  app.get("/providers", (c) => {
    const config = loadConfig();
    return c.json({
      providers: listAvailableProviders(config),
      current: sessions.getAll()[0]?.provider || config.provider,
    });
  });

  return app;
}
