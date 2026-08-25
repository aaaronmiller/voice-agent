# The temporal problem: state of the project

**Phase:** 0 — Audit | **Status:** Active | **Owner:** Cheta

## Entry criteria

None. This is the starting point.

## Current state (as of 2026-07-17 — after full reconstruction)

### What exists and works

- ✅ **Gateway layer** — Bun+Hono server on port 3000. WebSocket hub, REST API, session management, metrics aggregation. Running and verified.
- ✅ **6 provider implementations** — stub (qualification), gemini-live (WebSocket protocol), openai-realtime (WebSocket protocol), hermes (text bridge), pi-agent (text bridge), python-worker (legacy bridge).
- ✅ **Python provider CLIs** — `v2/providers/gemini_live.py` (full Gemini Multimodal Live API), `v2/providers/openai_realtime.py` (full OpenAI Realtime API).
- ✅ **TUI frontend** (Textual) — `tui/echo_tui/` with gateway client, transcript widget, latency widget, status widget, push-to-talk.
- ✅ **Monitoring dashboard** (Rich/Textual) — `tui/echo_monitor/` with rolling metrics, per-provider breakdowns, p50/p95/p99 percentiles.
- ✅ **Web frontend** (Svelte 5) — `frontend/src/App.svelte` with provider select, push-to-talk, transcript, latency sidebar, WebSocket client.
- ✅ **Unified CLI** — `echo-node --web`, `--tui`, `--voice-mode`, `--monitor`, `--gemini-live`, `--openai-realtime`, `--gateway-only`.
- ✅ **Single-command setup** — `setup.sh` installs everything, creates desktop entry, installs CLI.
- ✅ **Desktop entry** — `echo-node.desktop` registered in applications menu.
- ✅ **Pre-commit gate** — `.githooks/pre-commit` checks constitution integrity before commits.
- ✅ **Constitution** — 10 principles at `echo-node.livingdoc/constitution.md`, wired into `AGENTS.md`.

### What's implemented but requires API keys to test

- ⚠️ **Gemini Live** — provider code exists and is syntactically valid. Requires `GEMINI_API_KEY` for end-to-end testing.
- ⚠️ **OpenAI Realtime** — provider code exists and is syntactically valid. Requires `OPENAI_API_KEY` for end-to-end testing.

### What's still pending

- ⚠️ **Modular pipeline (Phase 4)** — spec exists at `06-modular-pipeline.md`. Code extraction from `assistant_v2.py` into `components/` and `pipeline/` not yet done.
- ⚠️ **LiveKit incarnation (lk_google)** — exists but not wired through the new gateway. Can be added as another provider.

### Latency baseline (measured from gateway)

| Stage | Time | Notes |
|---|---|---|
| Gateway WS handshake | <5ms | Local |
| Provider dispatch | <1ms | In-process |
| Stub provider (echo) | <10ms | No external calls |
| Legacy pipeline (STT→LLM→TTS) | 2.0–5.0s | Local ML |
| Gemini Live (target) | <800ms | Requires API key |
| OpenAI Realtime (target) | <600ms | Requires API key |

## Living Documeniving Document UX Decisions

The living document review tool (`echo-node.livingdoc/`) has its own UX that evolved through user feedback. Key decisions:

| Decision | Status | Notes |
|---|---|---|
| **Toolbar placement** | *implemented* | Action buttons (Edit, Annotate, Export) now at bottom of each section, distinct from top navigation bar |
| **Quick Edit** | *keep* | Inline markdown editing of sections. No AI needed — local save only. Confirmed useful for small fixes |
| **Add Note** | *removed* | Redundant with Annotate Selection. Both created hidden marginalia that sat in the change ledger. Single annotation flow now covers all marginalia needs |
| **Annotate Selection** | *keep* | Primary input path for AI-processed feedback. User highlights text → writes comment → AI reads annotation → edits the .md section file |
| **Annotation popup sizing** | *implemented* | Textarea now auto-sizes to match selected text, grows on user input, capped at max height |
| **Change ledger** | *user-only* | Scratchpad for personal notes during review. Not a destination for AI output. AI processes annotations into document edits directly |
| **Tags** | *made clickable* | Clicking a tag in any section activates the tag filter on the Dashboard (filtered view of tagged sections) |
| **Tables in markdown** | *fixed* | Markdown tables now render as proper HTML `<table>` elements instead of raw pipe-delimited text |
| **Section annotation counter** | *fixed* | Right-rail inspector now live-updates annotation count when an annotation is added |

**Rule going forward:** When the user exports annotations as a change request JSON, the AI must process each annotation by editing the relevant section `.md` file (not by adding content to the change ledger or annotations.json). The change ledger is for human notes only.

## Exit criteria\n\n- [x] Full inventory of existing code\n- [x] Latency baseline measured\n- [x] Gap analysis documented\n- [x] All missing components now built (gateway, web, TUI, providers, CLI, monitoring, constitution)"}]
