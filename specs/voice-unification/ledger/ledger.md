---
date: 2026-10-17 01:54 UTC
ver: 1.0.0
author: system (spec-prep preparation)
tags: [spec-prep, continuity, voice-unification, ledger]
---

# Ledger

Append-only. Never edited, reordered, or pruned. Sequence numbers are
monotonic and never reused. Phase.step uses spec-prep phase notation.

## 1 [0.existing] decision
- What: Consumed the human-authored unification pack (intent/spec/plan/
  constitution/PART1 v1.1.0 plus research-2026-10.md and live plan v1.2.0) as
  Existing-specs intake; authorship itself is ratification, so no review gate
  blocks preparation.
- Why: spec-prep SKILL.md Phase 0 Existing-specs mode; the pack IS the human's
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
  names and plain English, not prescribed stacks. spec-prep rule 1 requires
  justifying rather than deleting explicit user constraints.
- Effect: New file `specs/voice-unification/layer-allow.txt`.
- Outcome: pending validator re-run

## 4 [4.substrate] decision
- What: Declared substrate S3 with pre-locked contract/phases/license and
  live-resolved provider selection, process boundaries, and profile contents.
- Why: spec-prep rule 6 (honesty); the validator requires a declared S0..S5
  level, and claiming above S3 would misrepresent build-time resolution.
- Effect: New file `specs/voice-unification/substrate.md`.
- Outcome: pending

## 5 [4.evals] decision
- What: Created the external held-out eval manifest at
  `~/.spec-prep/evals/voice-unification/evals.md` with blind cases EVAL-001…
  EVAL-012 bound to SPEC-001…SPEC-012; public criteria stay in spec.md, only
  IDs and pass/fail assertions cross the boundary.
- Why: spec-prep rule 3 (eval binding); twelve bound clauses with no manifest
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
- Why: spec-prep Phase 5a lens 1; findings become clauses, failure conditions,
  or documented decisions.
- Effect: No artifact change; coverage recorded here.
- Outcome: complete

## 7 [5.refine-trace] refinement
- What: Traceability pass: all twelve clauses trace to intent sections;
  context decisions cite their clauses; research annex stays candidate-only
  (quarantine honored — no candidate promoted to mandate).
- Why: spec-prep Phase 5a lens 2 plus `--trace` output.
- Effect: plan.md v1.2.1 citations; research-2026-10.md unchanged.
- Outcome: complete

## 8 [5.refine-practice] refinement
- What: Current-practice pass: preparation targets the live lineage
  (`gateway/src/providers/registry.ts`, `v2/echo_node/slots/`,
  `v2/profiles.yaml`), not the stale `/home/cheta/code/voice-agent` copy or
  the retired aaa-voice-assistant checkout; tasks will carry observable
  acceptance gates and recovery per constitution G5.
- Why: spec-prep Phase 5a lens 3; agents build now against the repo that ships.
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
## 10 [0.prepare-closeout] decision
- What: T001 resolved as SUPERSEDE. `specs/001-echo-node-core/tasks.md`
  (T001-T127, 127/127 checked) is retired to historical reference,
  read-only; `specs/voice-unification/tasks.md` (T001-T061, SPEC-mapped,
  gated) is the sole authoritative forward task list. A supersession
  banner now heads the retired file pointing at the successor.
- Why: (1) ID-namespace collision — both schemes use T001... with
  different meanings (e.g. core-T010 = provider ABCs vs uni-T010 =
  config validation gate). (2) The retired checkboxes claim completion
  while the live gate is NOT clear (25/28 on 2026-10-17: WS handshake,
  providers endpoint, desktop entry fail), so they cannot gate current
  work. (3) Unification tasks carry SPEC/EVAL bindings + recovery per
  constitution G5; the old scheme has neither. (Task text named this
  SEQ 9; SEQ 9 was consumed by the relocate entry, so this is SEQ 10 —
  numbers never reused.)
- Effect: standing.md "Next" names supersede + the frozen T001-T061
  scheme; T002-T004 unblocked. No build tasks start until that gate
  passes (per tasks.md recovery).
- Outcome: complete

## 11 [0.prepare-closeout] milestone
- What: Phase 0 complete — T001-T004 checked with evidence. T001
  SUPERSEDE (SEQ 10, 001-core bannered read-only). T002 contract
  `contracts/registry.md` + stub gates green both sides (py 29 entries,
  gw stub-2 via registerProvider). T003 `docs/setup-windows.md` +
  preparation.json windowsCapabilities; rich-format clipboard and
  elevated-window insert stay explicit GAPs. T004 `contracts/profiles.md`
  + `v2/echo_node/profiles.py` + 3 profiles in
  `specs/voice-unification/profiles/` round-trip byte-identical;
  spec-prep-validate PASSED post-change.
- Why: Tasks remain unchecked until implementation supplies evidence;
  Phase 0 gates now have it. No build code — contracts, docs, probes,
  decisions only.
- Effect: Phase A1 (T010-T012) unblocked. A1 needs declared Windows
  hardware + evaluator EVAL procedures; this Linux host cannot supply
  either — reported as the standing blocker, not worked around.
- Outcome: complete

## 12 [A1.build] milestone
- What: Phase A1 complete — T010-T012 checked with evidence on
  declared hardware SPECTRE-16 (Windows 11 Pro 10.0.27965, Python 3.11,
  torch CPU-only, mic consent Allow, 14 sounddevice inputs, keyring+
  pywin32 installed by this task). T010 `config_security.py` + startup
  wiring (10/10 Linux, 7/7 Windows incl. WinVault round-trip, blind
  startup refusals). T011 `dictation.py` + `hf-whisper` registry STT
  (17/17 logic, 6/6 Windows HW E2E; tiny 3s load / 1.6s per 3s audio).
  T012 `capture_guard.py` + recorder/dictate wiring (19/19 logic, 3/3
  Windows live). Suite: T002 (30 entries) + T004 + T010 + T011 + T012
  green; ruff clean on new files (pre-existing stt.py/vad.py findings
  untouched); living-doc gate unchanged 25/28 (pre-existing WS/
  providers/desktop-entry fails, out of A1 scope).
- Why: A1 gates carry observable evidence per task; evaluator-held
  EVAL-006/009/011 remain the independent blind confirmation (G3).
- Effect: A1 closed. Next: A2 T020 (Windows dialogue loop) — needs
  provider pick (hosted vs local STT/LLM/TTS) + 2s-budget design.
  Known gaps carried: rich-format clipboard, elevated-window insert,
  cold-start STT latency (preload at service start mitigates).
- Outcome: complete

## 13 [A2.build] decision
- What: T020 done partial — EVAL-001 (arming/offline) + EVAL-005
  (stall/failure→armed idle) pass with evidence; EVAL-004 (≤2s) stays
  OPEN and is recorded as a gap, not a pass. Provider-agnosticism
  honored: no backend picked — loop runs slot-default providers
  (openwakeword / hf-whisper / sapi, all proven on SPECTRE-16) and any
  conforming backend plugs via registry + `backend.provider` config.
  Added: arm/disarm + guard wiring + level meter + stall timeout +
  sanitized failure + budget verdict + dialogue keys. Probe
  `test_dialogue_gate` 20/20. Windows timing: wake 0.3s/3.4ms-chunk,
  stt 1.2s, SAPI tts 2.5s (batch 3.7s OVER budget sans streaming);
  no live backend on host (hermes:8642 closed, no keys, no ollama).
  Lint at exact baseline parity (orchestrator + tts deltas zero).
- Why: The 2s loop needs a live backend's token stream overlapping
  TTS (the `speak_stream` path already exists for exactly this).
  Claiming EVAL-004 on batch timings would be dishonest (G2/G5).
- Effect: T021 (echo exclusion + barge-in) is next and needs no
  backend either (VAD/AEC/playback-cancellation acoustics). EVAL-004
  waits on: live backend on declared hardware, or an explicit
  scope revision.
- Outcome: complete (partial — EVAL-004 open)

## 14 [A2.build] milestone
- What: EVAL-004 CLOSED — streaming turn on SPECTRE-16 measured 1.79s
  WITHIN budget (fw-tiny stt 0.60s + qwen2.5:0.5b first-token 0.85s +
  warm-SAPI first-sentence TTS 0.32s, overlapped not batched). SEQ 13's
  OPEN gap is resolved, not reinterpreted: new evidence, new verdict.
- Why numbers were off: every component was measured cold. Whisper
  load 3-8s vs inference 0.6-1.6s; SAPI one-shot 2-2.5s = 0.6s PS
  spawn + 1.2s .NET/SAPI init + synth (warm host 0.01-0.3s); ollama
  reload 6.6-24s on the 1.1G-RAM box vs 0.16-0.85s pinned-warm
  first-token. Fixes: STT prewarm (already in loop), persistent SAPI
  host (`SapiTTS.load/warm`, one-shot fallback), ollama `keep_alive: -1`
  (+ `OLLAMA_KEEP_ALIVE=-1` on the server). faster-whisper tiny int8
  installed on Windows (1.07s vs 1.57s transformers).
- GPU verdict: Intel-only box (Iris Xe + Arc A370M, no NVIDIA → no
  CUDA anywhere). ORT CPU-only on both OSes; torch CPU-only both
  sides; OpenVINO sees Arc GPUs but no current provider uses them.
  CPU int8 + warm persistence is the correct fight today. No, we were
  not using GPU — there is no GPU to use for these providers.
- Added: `OllamaBackend` (registry `ollama`, config-only selection,
  SSE streaming, keep_alive pinned, no key, validated live). Suite:
  all six probes green (registry 32 entries); ruff at baseline parity
  on backends.py/orchestrator/tts.py (zero new findings, zero
  deletions). Voicemode kokoro :8880 hangs (30s timeout, empty) —
  not our path, recorded and skipped.
- Effect: T020 fully closed (EVAL-001/004/005). Next: T021 echo
  exclusion + barge-in. OLLAMA_KEEP_ALIVE=-1 + model pinned for the
  session; server persistence across reboots is operator setup
  (recorded, not automated here).
- Outcome: complete
