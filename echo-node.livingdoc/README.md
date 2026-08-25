# Echo-Node Voice Agent — Living Build Plan

This is the **living document** for the complete Echo-Node voice agent reconstruction.

## Quick start

```bash
# View in browser
node serve.mjs
open http://localhost:8080

# Validate structure
node scripts/validate.mjs
```

## The plan

The reconstruction is organized into **12 phases** across 3 tiers:

### Tier 1: Foundation (Phases 0–3)
| Phase | What | Status |
|---|---|---|
| 0 | Project audit & latency baseline | ✅ Complete |
| 1 | Target 3-layer architecture specification | ✅ Drafting |
| 2 | Bun+Hono WebSocket gateway | ⏳ Pending |
| 3 | Svelte 5 web frontend | ⏳ Pending |
| 3b | Textual TUI frontend | ⏳ Pending |

### Tier 2: Pipeline & providers (Phases 4–5)
| Phase | What | Status |
|---|---|---|
| 4 | Modular component pipeline | ⏳ Pending |
| 5 | Google Gemini Multimodal Live API | ⏳ Pending |
| 5b | OpenAI Realtime API | ⏳ Pending |

### Tier 3: Polish (Phases 6–9)
| Phase | What | Status |
|---|---|---|
| 6 | Live monitoring & observability dashboard | ⏳ Pending |
| 7 | Unified provider abstraction | ⏳ Pending |
| 8 | Unified installer & launcher | ⏳ Pending |
| 9 | Stretch goals & evolution boundary | ⏳ Pending |

## Project structure

```
echo-node.livingdoc/
├── RAISON_DETRE.md              # Why this exists
├── MODEL_START_HERE.md          # Agent entry point
├── README.md                    # This file
├── package.json                 # Living doc server
├── serve.mjs                    # HTTP server for review
├── scripts/
│   └── validate.mjs             # Structure validator
├── public/
│   ├── index.html               # Browser review surface
│   ├── app.js                   # App logic
│   ├── styles.css               # Themes & layout
│   ├── manifest.webmanifest
│   ├── content/
│   │   ├── index.json           # Full manifest
│   │   └── sections/            # 12 phase specs (*.md)
│   └── data/
│       └── annotations.json     # Human annotations
└── worklogs/                    # Agent run logs (append-only)
```

## Key documents

- `public/content/index.json` — The complete manifest with all phases, proposals, history, and worklogs
- `public/content/sections/01-temporal-problem.md` — Project audit & latency baseline
- `public/content/sections/02-architecture-overview.md` — Target architecture
- `public/content/sections/07-google-gemini-live.md` — Gemini Live implementation
- `public/content/sections/09-monitoring.md` — Observability spec

## Proposals

See the **Proposals** view in the browser, or read from `public/content/index.json` → `proposals[]`.

Key decisions already made:
- ✅ **P-001**: Replace monolithic architecture with gateway
- ✅ **P-002**: Implement Gemini Live first (standalone CLI, then gateway)
- ✅ **P-003**: Build terminal latency dashboard before web frontend
- ✅ **P-004**: Keep legacy local pipeline as fallback
- ❓ **P-005**: Use Bun as primary runtime (pending)

## Contributing

This is a living document — edit the sections, update the manifest, and append worklogs. Never delete content without inbound-reference checks. Read `RAISON_DETRE.md` before operating.
