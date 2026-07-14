# PLAN — Buttplug Voice Agent

## Project Goal
Voice agent built on the buttplug protocol framework with Python worker, Bun/TypeScript gateway, and Svelte 5 frontend (spec 001-echo-node-core). Currently 60-70% functional.

## Key Files Already Present
- `README.md` — Project documentation
- `CLAUDE.md` — Development guidelines
- `voice-agent-requirements.md` — Requirements document
- `worker/` — Python worker (main.py, config.py, pipeline.py)
- `gateway/` — TypeScript gateway
- `frontend/` — Svelte 5 frontend
- `specs/001-echo-node-core/` — Spec (data-model.md, plan.md, quickstart.md)
- `docs/` — Setup and integration docs (hermes-integration, provider-guide, setup guides)

## What's Done
- Worker, gateway, and frontend scaffolds exist
- Pipeline.py implements core worker logic
- Documentation for WSL2, Fedora, and macOS setups written
- Hermes integration doc exists
- 60-70% functional per audit

## What's Needed
- [ ] Complete remaining 30-40% functionality
- [ ] Resolve any integration gaps with Hermes
- [ ] Test end-to-end voice pipeline
- [ ] Decide if overlaps with aaa-voice-assistant should be merged

## Related Scratchfiles
- E1: `~/.hermes/pastes/E1.md` — buttplug-synergy
- C8: Completed audit (buttplug-audit)
