---
date: 2026-10-17 01:54 UTC
ver: 1.0.0
author: system (strata preparation)
tags: [strata, continuity, voice-unification, ledger]
---

# Ledger

Append-only. Never edited, reordered, or pruned. Sequence numbers are
monotonic and never reused. Phase.step uses STRATA phase notation.

## 1 [0.existing] decision
- What: Consumed the human-authored unification pack (intent/spec/plan/
  constitution/PART1 v1.1.0 plus research-2026-10.md and live plan v1.2.0) as
  Existing-specs intake; authorship itself is ratification, so no review gate
  blocks preparation.
- Why: Strata SKILL.md Phase 0 Existing-specs mode; the pack IS the human's
  spec and arrives pre-ratified.
- Effect: This preparation works from
  `specs/voice-unification/` in `aaaronmiller/voice-agent` (live lineage at
  d81069e); the stale `/home/cheta/code/voice-agent` copy is documented as
  superseded, not edited.
- Outcome: pending

## 2 [3.derive] decision
- What: Kept CTX-001…CTX-007 as the derived layer and recorded their
  SPEC citations explicitly (CTX-004 now cites SPEC-001/002/003/005/007/011;
  CTX-003 cites SPEC-008/009/012; CTX-005 cites SPEC-006/007/009/011).
- Why: Validator drift check requires every SPEC clause cited by the context
  layer; five clauses (002/003/005/009/011) were previously uncited.
- Effect: plan.md v1.2.1 derivation lines; no architectural change.
- Outcome: pending validator re-run

## 3 [4.allow] decision
- What: Added `layer-allow.txt` with three genuine user-facing names:
  `voiceink` (out-of-scope product boundary), `express` (ordinary verb at
  spec.md:11), `intent.md` (provenance reference at spec.md:10).
- Why: Validator separation hits were false positives — quarantined product
  names and plain English, not prescribed stacks. Strata rule 1 requires
  justifying rather than deleting explicit user constraints.
- Effect: New file `specs/voice-unification/layer-allow.txt`.
- Outcome: pending validator re-run

## 4 [4.substrate] decision
- What: Declared substrate S3 with pre-locked contract/phases/license and
  live-resolved provider selection, process boundaries, and profile contents.
- Why: Strata rule 6 (honesty); the validator requires a declared S0..S5
  level, and claiming above S3 would misrepresent build-time resolution.
- Effect: New file `specs/voice-unification/substrate.md`.
- Outcome: pending

## 5 [4.evals] decision
- What: Created the external held-out eval manifest at
  `~/.strata/evals/voice-unification/evals.md` with blind cases EVAL-001…
  EVAL-012 bound to SPEC-001…SPEC-012; public criteria stay in spec.md, only
  IDs and pass/fail assertions cross the boundary.
- Why: Strata rule 3 (eval binding); twelve bound clauses with no manifest
  are clauses that lie with confidence. Store sits outside the repo so the
  builder cannot read the tests it is graded on.
- Effect: New external file; isolation beyond path separation (separate
  evaluator context) is NOT established and is disclosed in substrate.md.
- Outcome: pending validator re-run

## 6 [5.refine-adversarial] refinement
- What: Adversarial pass over intent failure conditions vs spec coverage:
  every intent §6 bullet has at least one clause (provider stall→SPEC-005,
  mic loss→SPEC-011, music/noise→SPEC-002, barge-in→SPEC-003, invalid
  config/insertion→SPEC-009/006); no new clause needed.
- Why: Strata Phase 5a lens 1; findings become clauses, failure conditions,
  or documented decisions.
- Effect: No artifact change; coverage recorded here.
- Outcome: complete

## 7 [5.refine-trace] refinement
- What: Traceability pass: all twelve clauses trace to intent sections;
  context decisions cite their clauses; research annex stays candidate-only
  (quarantine honored — no candidate promoted to mandate).
- Why: Strata Phase 5a lens 2 plus `--trace` output.
- Effect: plan.md v1.2.1 citations; research-2026-10.md unchanged.
- Outcome: complete

## 8 [5.refine-practice] refinement
- What: Current-practice pass: preparation targets the live lineage
  (`gateway/src/providers/registry.ts`, `v2/echo_node/slots/`,
  `v2/profiles.yaml`), not the stale `/home/cheta/code/voice-agent` copy or
  the retired aaa-voice-assistant checkout; tasks will carry observable
  acceptance gates and recovery per constitution G5.
- Why: Strata Phase 5a lens 3; agents build now against the repo that ships.
- Effect: Recorded here and in standing.md; tasks.md next.
- Outcome: complete

## 9 [7.relocate] decision
- What: Removed the stale `/home/cheta/code/voice-agent` copy (checkpointed
  to `~/agent_trash/voice-agent-stale-2026-10-17/` with MANIFEST + restore
  line) and moved the authoritative repo from `code/buttplug/voice-agent` to
  `code/voice-agent`; updated preparation.json buildRoot, standing, and
  reset-handoff to the new root.
- Why: User-authorized removal of the conflicting pack copy; single
  authoritative checkout at the top-level path AGENTS.md already names.
- Effect: `specs/voice-unification/{preparation.json,reset-handoff.md,
  ledger/standing.md,workbench.json}` point at `/home/cheta/code/voice-agent`;
  historical `buttplug/voice-agent` strings remain only in PART1 inventory
  (provenance) and archive notes.
- Outcome: pending validator + workbench re-check
