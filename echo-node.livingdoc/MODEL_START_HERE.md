# MODEL START HERE — Echo-Node Living Document

Read in this order:

1. `RAISON_DETRE.md` — Why this document exists
2. `public/content/index.json` — The full manifest: phases, dependencies, statuses
3. `public/content/sections/` — Phase-specific implementation specs, in order:
   - `01-temporal-problem.md` — Current state audit and why rebuild
   - `02-architecture-overview.md` — Target 3-layer split-stack
   - `03-gateway.md` — Bun+Hono WebSocket relay
   - `04-web-frontend.md` — Svelte SPA
   - `05-tui-frontend.md` — Textual TUI
   - `06-modular-pipeline.md` — Interchangeable components
   - `07-google-gemini-live.md` — Gemini Multimodal Live API
   - `08-openai-realtime.md` — OpenAI Realtime API
   - `09-monitoring.md` — Live observability dashboard
   - `10-provider-system.md` — Backend abstraction
   - `11-deployment.md` — Install, launch, hotkeys
   - `12-evolution-boundary.md` — Long-term stretch goals

## How to operate on this document

1. Read `RAISON_DETRE.md` and this file first
2. Read `public/content/index.json` for the full dependency graph
3. Edit only the section(s) relevant to your current phase
4. Append worklogs after every agent run
5. Never delete a section, proposal, or annotation — use status changes
6. Update `"updated"` timestamps and backlinks when relationships change
7. Validate JSON with `node scripts/validate.mjs` before reporting done
8. Serve locally with `node serve.mjs` for browser review

## Phase execution policy

- Each phase has explicit **entry criteria** — check them before starting
- Each phase has **exit criteria** — verify all before marking complete
- No phase depends on unbuilt infrastructure from a later phase
- A phase may be partially implemented if exit criteria are met for a subset
- When a phase completes, append a worklog entry and update the manifest
