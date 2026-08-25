# RAISON D'ETRE: Echo-Node — A living voice-agent build plan

## ⚠️ CRITICAL: THIS IS A LIVING DOCUMENT — READ THIS FIRST

This document is a **browser-native, addressable review surface for asynchronous human-agent collaboration.** It is NOT a build plan. It is NOT a checklist. It is a coordination protocol between human and agent, designed so the human can review agent work at human speed without racing terminal scrollback.

**Every feature of this living document exists because of a specific failure mode that occurred during this project.** The features are MANDATORY. No agent may remove, disable, or "simplify" any of the following without explicit human authorization in a modelReply:

| Feature | Purpose | What failed when it was missing |
|---|---|---|
| **Annotation system** (select text → popup → save → export) | Allows human to attach precise comments to specific passages | Agent made changes without human being able to flag specific problems at the passage level |
| **ModelReplies** (question/option cards) | Tracks decisions the agent needs from the human | Agent proceeded past unanswered questions, assuming consent |
| **Proposals** (approve/defer/reject) | Formalizes discrete decision points | Agent made architectural decisions without explicit approval |
| **Worklogs** (immutable agent appendices) | Records what was changed, validated, and suggested | Agent claimed completion without audit trail |
| **Three export formats** (change request JSON, merged JSON, Markdown) | Enables agent handoff and context survival | Changes were trapped in a single session, unrecoverable |
| **Constitution** (constitution.md) | Prevents agent from self-policing its own work | Agent wrote its own gate criteria and changed them when checks failed |
| **AGENTS.md** (constitution wiring) | Loads constitution into agent context at session start | Constitution was never enforced because agent never read it |
| **Dashboard health indicators** | Surface real project status at a glance | Phases were claimed complete while manifest still showed "pending" |

**Any agent that strips or modifies these features without a modelReply from the human authorizing exactly what to strip and why is violating the constitution (Principle IV: Honest Status Reporting, Principle IX: Open Decision Tracking).**

The living document exists because the project **drifted** from its architectural specification into a monolithic Python script that is slow, unobservable, and missing most of its planned features. Chat is insufficient to recover from this — each fix spawns ten new questions and the scrollback swallows decisions.

This document is different. It is spatial, persistent, and organized around stable sections, proposals, changelogs, immutable worklogs, annotatable passages, exportable change requests, and a constitutional gating system. Every feature above is the reason it can prevent project drift.

## Why this architecture

The original `docs/voice-agent-design.md` specified a **3-layer split-stack**:

```
Svelte Web Frontend  ──ws──→  Bun+Hono Gateway  ──ws──→  Python Audio Worker
```

This was the right design. The current monolithic `assistant_v2.py` is tech debt. The living document recovers the original architecture and extends it with live-voice providers and production observability.

## Project contract

- The canonical working form is the folder `echo-node.livingdoc/`
- All section prose lives in `public/content/sections/*.md`
- The manifest at `public/content/index.json` is the source of truth for phase ordering, dependencies, and status
- Worklogs in `worklogs/` record every agent run immutably
- Proposals in the manifest track feature decisions
- Annotations in `public/data/annotations.json` attach human review to precise targets
- **The constitution at `constitution.md` is the binding rule set that all agents must follow**
- **AGENTS.md at the project root wires the constitution into every agent session**
- The browser shell (`public/index.html`) is a review surface, not a content warehouse
- **No code is written to `~/code/voice-agent/` until the phase is approved in this document**

## The constitutional gating system (how this prevents recurrence)

The gate mechanism is **constitution-only** — no pre-commit hook complexity, no CI dependencies, no API calls:

1. **`constitution.md`** — 10 principles that define binding rules for all agents
2. **`AGENTS.md`** — inlines the full constitution text and is loaded into agent context at session start
3. **`tasks.md`** — per-phase constitution checks that evaluate all 10 principles before each phase gate clears
4. **`public/content/index.json` → `modelReplies`** — tracks decisions the human must make, including ratification of the constitution itself

An agent cannot modify the constitution mid-session because:
- AGENTS.md is loaded at session start — changes require a **context reload or agent restart** before they take effect
- The pre-commit hook (`.githooks/pre-commit`) is a **simple 2-line safety net**, not the primary gate — it just checks constitution.md still exists with 10 principles before allowing commits

**To ratify changes to the constitution or rules:**
1. Edit `constitution.md` with the proposed changes
2. Update `AGENTS.md` to match
3. The human responds to the relevant modelReply approving the change
4. **Reload or restart the agent** for the new rules to take effect
5. Only then may the agent act under the new rules

This is enforced by **Principle VII: Context Reload for Rule Changes** — see `constitution.md`.

## Version contract

Format version: 2.1.0 (Living Document Forge compatible). Skill range: 1.2.0–2.0.0. All sections carry stable IDs. Never delete a section without inbound-reference checks.

## Completion criteria

The project is **complete** when:

1. A user can launch with `echo-node --web` or `echo-node --tui` or `echo-node --voice` (legacy)
2. Any backend provider (Hermes, OpenAI, Google, OpenRouter, Claude, Pi) is swappable at launch
3. Any frontend (web, TUI, voice-only) is selectable at launch
4. Google Gemini Multimodal Live API works end-to-end at <800ms latency
5. OpenAI Realtime API works end-to-end at <800ms latency
6. A live monitoring dashboard shows per-turn latency, per-provider breakdowns, and interrupt metrics
7. The legacy local pipeline (STT→LLM→TTS) still works as a fallback
8. A single `bun install && bun start` or `pip install && python -m echo_node` brings up the full system
