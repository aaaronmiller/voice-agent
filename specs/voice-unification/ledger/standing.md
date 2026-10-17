---
date: 2026-10-17 01:54 UTC
ver: 1.0.0
author: system (strata preparation)
tags: [strata, continuity, voice-unification, standing]
---

# Standing

## Where this is

Voice unification is in specification preparation (Strata Phase 4–6) against
the live lineage `aaaronmiller/voice-agent` at d81069e. Intent, spec, plan
(v1.2.1), constitution, research annex, substrate, eval manifest, and ledger
exist; `tasks.md`, `preparation.json`, `reset-handoff.md`, and
`workbench.json` pointers are still to be written. The validator is not yet
green. No implementation has started under this preparation.

## Last decisions that matter

- SEQ 1: human-authored pack consumed as pre-ratified Existing-specs intake;
  stale `/home/cheta/code/voice-agent` copy superseded, live
  `buttplug/voice-agent` copy authoritative.
- SEQ 2–3: drift citations completed in plan v1.2.1; `layer-allow.txt`
  justifies voiceink / express / intent.md as user-facing names.
- SEQ 4–5: substrate S3 declared; twelve blind evals held outside the repo at
  `~/.strata/evals/voice-unification/evals.md`; evaluator-context isolation
  NOT established (disclosed).
- SEQ 6–8: three refinement passes complete — failure-condition coverage
  verified, traceability recorded, live-tree targeting confirmed.

## Not yet decided

- Exact registry slot schema and profile document format (deferred to tasks;
  `v2/echo_node/slots/` ABCs and `v2/profiles.yaml` are the prototypes to
  extend, per plan §8).
- Windows-native audio approach and Android delivery shape (plan CTX-002 /
  CTX-005 require capability checks before promises; intent §3 + §5 govern).
- Whether `001-echo-node-core` tasks.md is superseded or extended by the new
  unification tasks (decision point before task IDs are frozen).

## Next

Write `specs/voice-unification/tasks.md` (gated, dependency-ordered, mapped
to SPEC/EVAL IDs with recovery), then `preparation.json` with real gate
evidence, then `reset-handoff.md`; re-run the validator to green before any
fresh-harness initiation.

## Substrate note

Declared S3. Pre-locked: twelve SPEC/EVAL bindings, phase order A1→B,
MIT/no-AGPL, VoiceInk independence, eval separation. Live-resolved at build
time: per-slot provider selection, process boundaries, profile contents,
config schema. No runtime acceptance is proven by this preparation.
