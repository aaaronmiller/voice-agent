---
date: 2026-10-17 01:54 UTC
ver: 1.0.0
author: system (spec-prep preparation)
tags: [spec-prep, handoff, voice-unification, reset]
---

# Reset handoff — voice unification

## Build root (only authority)

`/home/cheta/code/voice-agent` — repo
`git@github.com:aaaronmiller/voice-agent.git`, revision `eb56e43` at
preparation time (moved from `code/buttplug/voice-agent` 2026-10-17; stale
`/home/cheta/code/voice-agent` copy removed, checkpointed to
`~/agent_trash/voice-agent-stale-2026-10-17/`).

## Canonical paths (all relative to build root)

- Intent: `specs/voice-unification/intent.md`
- Spec: `specs/voice-unification/spec.md` (SPEC-001…012, EVAL-001…012)
- Plan: `specs/voice-unification/plan.md` (v1.2.1, CTX-001…007 + §8 registry)
- Tasks: `specs/voice-unification/tasks.md` (T001…T061, all unchecked)
- Constitution: `specs/voice-unification/constitution.md` (G1–G5)
- Organization (existing-state, read-only): `specs/voice-unification/PART1-organization.md`
- Research annex: `specs/voice-unification/research-2026-10.md`
- Substrate: `specs/voice-unification/substrate.md` (S3)
- Continuity: `specs/voice-unification/ledger/ledger.md` (SEQ 1–8),
  `specs/voice-unification/ledger/standing.md`
- Receipt: `specs/voice-unification/preparation.json` (hashes + gate evidence)
- Held-out evals (evaluator only, NEVER the builder):
  `~/.spec-prep/evals/voice-unification/evals.md`

## Validated inputs

Human-authored pack consumed as pre-ratified Existing-specs intake
(authorship IS ratification — review available, NOT required; silence is
consent). Validator green at preparation close. Later disagreement enters as
a layer-scoped change request against intent.md, never a retroactive block.

## Preparation commands run (all green)

- `python3 spec-prep-validate.py specs/voice-unification` → PASSED
- `python3 spec-prep-validate.py specs/voice-unification --trace` → 12/12
  bound, 12/12 cited
- `python3 spec-prep-validate.py --audit <spec.md> <plan.md>` →
  source-pack check recorded during preparation (2 advisory notes resolved
  via citations + layer-allow.txt)

## Unresolved material items

1. T001: supersede-vs-extend decision for `specs/001-echo-node-core/tasks.md`.
2. Windows capability findings (T003) — background listening, insertion,
   clipboard, permission APIs.
3. Android delivery shape (Phase B) — capability checks first.
4. Evaluator-context isolation NOT established (path separation only).

## Next authorized task

T001 (resolve the 001-echo-node-core relationship, ledger SEQ 9), then
T002–T004, then Phase A1. Tasks remain unchecked until implementation
supplies evidence.

## Scope of initiation authority

Preparation ONLY. No implementation is authorized by this handoff. A fresh
harness starts at the build root above, reads `ledger/standing.md` and the
ledger tail first, then intent and spec, verifies receipt hashes, and
requires explicit launch authority before touching code. The authoring
session writes no implementation, marks no task complete, and authors no
fresh-session acknowledgement.
