# Echo-Node Agent Instructions

This file governs all agents operating on the Echo-Node voice agent project.
It is loaded at session start and cannot be modified mid-session without a context reload.

## Project Root
```
~/code/voice-agent/
```

## Constitution (Full Text — Inlined for Context Survival)

The canonical constitution lives at `echo-node.livingdoc/constitution.md`. The text below is an exact copy. If there is any discrepancy, the file `echo-node.livingdoc/constitution.md` is authoritative.

### Echo-Node Project Constitution v2.0.0

**Preamble:** The Echo-Node voice agent project exists to recover from architectural drift and deliver a production-quality, multi-frontend voice system with interchangeable live-voice providers. This constitution establishes binding rules that every agent operating on this project must follow.

### Principles

**Principle I: Gate Integrity** — The gate is external to any single agent. No agent may define, modify, or waive the criteria by which its own work is judged. All gate checks must be performed by a pre-commit hook installed before the agent session began, a CI/CD pipeline running independently, a second agent in a separate context, or explicit human sign-off recorded in a modelReply.

**Principle II: Constitutional Primacy** — The constitution is the highest authority. Every agent action must be consistent with these principles. The canonical constitution lives at `echo-node.livingdoc/constitution.md`.

**Principle III: Build Order Fidelity** — The implementation order CLI → TUI → Web is binding. Each layer must be verifiably complete before the next begins.

**Principle IV: Honest Status Reporting** — Phase status must reflect reality, not convenience. A phase is "stable" only when all exit criteria are checked programmatically and the gate script reports zero failures.

**Principle V: Immutable Worklog** — Every agent revision produces an append-only worklog entry. Worklogs are never rewritten — corrections are new entries.

**Principle VI: Pre-Commit Verification** — No code change may be committed without passing the gate check. Bypassing with `--no-verify` requires explicit human authorization.

**Principle VII: Context Reload for Rule Changes** — Changes to AGENTS.md, constitution.md, or any gating mechanism require a context reload before taking effect.

**Principle VIII: Mechanical Principle Extraction** — Principle names in AGENTS.md must be extracted mechanically from the canonical constitution.md. Never type principle names from memory.

**Principle IX: Open Decision Tracking** — All decisions requiring human input are tracked as modelReplies in the living document.

**Principle X: Cross-Verification** — No phase completion is valid without cross-verification by the gate check script, a second agent, or human confirmation.

### Governance
- Amendments require human-approved proposals
- Pre-commit hook enforces Principles I, III, VI
- AGENTS.md enforces Principles II, VII, VIII
- Living document manifest enforces Principles IV, IX
- Three violations trigger mandatory human review

## Mandatory Workflow

### On Session Start
1. Read this file (AGENTS.md) — already loaded by context
2. Read `echo-node.livingdoc/constitution.md` — verify principles match
3. Run `bash echo-node.livingdoc/scripts/gate-check.sh` — establish baseline
4. Check the living document at `echo-node.livingdoc/public/content/index.json` for:
   - Open modelReplies that block your intended work
   - Current phase statuses
   - Dashboard health indicators
5. Check `specs/001-echo-node-core/tasks.md` for constitution-checked tasks
6. Do NOT begin work blocked by an open modelReply

### Before Any Phase Change
1. Verify the phase's exit criteria in the living document section
2. Run `bash echo-node.livingdoc/scripts/gate-check.sh`
3. Check that zero gates fail
4. Record a worklog entry in the living document
5. If any principle check fails, STOP — document the failure, do not proceed

### Before Any Commit
1. The pre-commit hook will run automatically
2. If it fails, fix the issue — do not use `--no-verify` without human authorization
3. After any change to AGENTS.md or constitution.md, signal that a reload is needed

### Before Marking a Phase Complete
1. Verify ALL exit criteria are met programmatically
2. Run the gate check — zero failures required
3. A second agent or human must confirm
4. Update the manifest status field
5. Append a worklog entry documenting what was validated

## Living Document Location
```
~/code/voice-agent/echo-node.livingdoc/
  serve.mjs              # Start with: node serve.mjs (port 8080)
  public/
    index.html           # Browser UI
    content/
      index.json         # Manifest — source of truth for phase status
      sections/          # 12 phase specifications with entry/exit criteria
    data/
      annotations.json   # Human and agent annotations
```

## Key Paths
- Gateway: `~/code/voice-agent/gateway/` (Bun + Hono, port 3000)
- Legacy worker: `~/code/voice-agent/v2/assistant_v2.py`
- TUI: `~/code/voice-agent/tui/echo_tui/`
- Web frontend: `~/code/voice-agent/frontend/`
- Provision providers: `~/code/voice-agent/v2/providers/`
- Unified CLI: `~/code/voice-agent/echo_node/cli.py`

## Pre-Commit Hook
Installed at `.githooks/pre-commit` and symlinked to `.git/hooks/pre-commit`.
This hook runs on every `git commit` and rejects if gate-check.sh fails.
The hook was installed before this agent session and cannot be modified during it.

## Environment Variables
- `GEMINI_API_KEY` — unlocks Gemini Live provider
- `OPENAI_API_KEY` — unlocks OpenAI Realtime provider
- `ECHO_DEFAULT_PROVIDER` — default provider for --web and --tui modes
- `ECHO_GATEWAY_URL` — WebSocket URL (default: ws://127.0.0.1:3000/ws)

## Verification Commands
```bash
# Gate check
bash echo-node.livingdoc/scripts/gate-check.sh

# Living document validation
node echo-node.livingdoc/scripts/validate.mjs

# Gateway health
curl -s http://127.0.0.1:3000/api/health

# WebSocket test (requires bun)
bun -e "new WebSocket('ws://127.0.0.1:3000/ws').onopen=()=>{console.log('OK');process.exit()}"
```
