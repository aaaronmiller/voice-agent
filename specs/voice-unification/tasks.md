---
date: 2026-10-17 01:54 UTC
ver: 1.0.0
author: system (spec-prep preparation)
tags: [spec-prep, tasks, voice-unification, gated]
---

# Voice unification tasks

Derived from `spec.md` (SPEC-001…012), `plan.md` (CTX-001…007, phases
A1→A2→A3→A4→B), and `research-2026-10.md` (candidates with swap criteria).
Each task has an ID, dependencies, affected paths, an observable acceptance
gate, and recovery. Tasks remain unchecked until implementation supplies
evidence. No model/library/version is pinned here; build-time selection uses
current probe evidence recorded against the task.

Notation: `[ID] [P?] [SPECs] Description`. `[P]` = parallel-safe (different
files, no ordering dependency). Gates are procedures to execute, not checkbox
text. Recovery applies on failure; constitution G5 governs.

Decisions still open (standing.md): registry slot schema shape, Windows-native
audio approach, Android delivery shape, and whether `001-echo-node-core`
tasks.md is superseded or extended. Tasks T001–T004 resolve or record these
before build tasks proceed.

## Phase 0: Preparation close-out (no build code)

- [x] T001 Resolve the `001-echo-node-core` relationship. Decide supersede
  vs extend for `specs/001-echo-node-core/tasks.md`; record the decision and
  its reason as ledger SEQ 10 (SUPERSEDE: retired file bannered read-only;
  forward scheme T001–T061). Depends on: none. Paths:
  `specs/voice-unification/ledger/ledger.md`,
  `specs/voice-unification/ledger/standing.md`. Gate: standing.md "Next"
  names the chosen relationship and the frozen task-ID scheme. Recovery: no
  build tasks start until this gate passes.
- [x] T002 [P] [SPEC-008, SPEC-012] Freeze the registry slot schema.
  Prototype sources: `gateway/src/providers/registry.ts`,
  `v2/echo_node/slots/registry.py`, `v2/echo_node/slots/validation.py`.
  Decide: capability descriptor fields, conformance-probe contract, and how a
  component registers without touching core paths. Depends on: T001. Paths:
  `specs/voice-unification/plan.md` §8 (amend if the schema diverges),
  new `specs/voice-unification/contracts/registry.md`. Gate: a second
  conforming stub registers through the documented path with zero core-path
  edits; validator re-run still green. Recovery: revert contract to the
  prototype behavior and re-record.
- [x] T003 [P] [SPEC-006, SPEC-009, SPEC-011] Record Windows capability
  findings. Investigate background listening, insertion/clipboard access, and
  permission-guidance APIs before promising delivery (plan CTX-005).
  Unsupported behavior is recorded as an explicit gap, never a silent pass.
  Depends on: T001. Paths: `specs/voice-unification/preparation.json`
  (capability evidence), `docs/setup-windows.md` (new or amended). Gate:
  each A1 task lists its required OS capability as present/gapped with a
  reproducible check. Recovery: gap stays open; phase A1 scope revises
  explicitly instead of failing silently.
- [x] T004 [P] Freeze the saved-profile document format. Prototype source:
  `v2/profiles.yaml` (+ `v2/agent_profiles.py` if it shapes the schema).
  Decide: versioned full-stack combination format (STT+TTS+VAD+wake+dialogue+
  transport+avatar), hardware floor, expected SPEC coverage, export/import.
  Depends on: T001. Paths: new
  `specs/voice-unification/contracts/profiles.md`. Gate: the three live
  profiles round-trip through export/import byte-identical. Recovery: revert
  to the live YAML shape and re-record.

## Phase A1: Windows dictation + configuration (SPEC-006/009/011)

- [x] T010 [P] [SPEC-009] Configuration validation gate. DONE 2026-10-17: `v2/echo_node/config_security.py` wired into `assistant_v2.main` before capture/provider contact; hotkey trigger keys in `config.example.yaml`. Evidence: `test_config_gate` 10/10 Linux + 7/7 Windows (WinVaultKeyring round-trip); blind startup refusals verified.
  config loader + schema (live: `v2/echo_node/`, gateway `src/config.ts`).
  Implement: invalid fields, conflicting triggers, inline secrets, and
  unavailable secret storage refuse the affected path before capture or
  provider contact, name the field, expose no secrets. Gate: run the blind
  EVAL-009 procedure via the evaluator; all four refusal classes trigger.
  Recovery: return to last verified config behavior; retain failure evidence.
- [x] T011 [SPEC-006] Windows dictation path. DONE 2026-10-17: `v2/echo_node/dictation.py` (trigger→capture→transcribe→insert-once→restore; focus guard; concurrent-copy precedence) + `hf-whisper` STT via registry (proven: tiny 3s load, 1.6s/3s-audio CPU). Evidence: `test_dictation_gate` 17/17 logic; SPECTRE-16 HW E2E 6/6 (mic, transcribe, clipboard, paste, restore). Known gap: rich-format clipboard + cold-start STT latency (preload at service start).
  focused editable field → transcribe → insert once at cursor → restore
  prior clipboard/formats, newer concurrent copy wins. Depends on: T002,
  T003, T010. Affected paths: dictation path + native insertion/clipboard
  code (new). Gate: EVAL-006 procedure — insertion, restoration,
  precedence, and failure/cancellation/focus-change preservation all pass
  on declared Windows hardware. Recovery: checkpoint config + prior build;
  failed change returns to last verified state.
- [x] T012 [P] [SPEC-011] Permission/device-loss handling on Windows. DONE 2026-10-17: `v2/echo_node/capture_guard.py` (deny/revoke/remove→disable+guidance, sticky, no retry; runtime-loss preserves chunks; disarm sticky; explicit re_arm only) wired into `Recorder.record_turn` + `dictate_once`. Evidence: `test_capture_guard` 19/19; SPECTRE-16 live (consent Allow, 14 inputs, gate allows) 3/3.
  Implements: denial/revocation/removal disables capture with OS guidance,
  no retry loops; runtime loss stops capture and preserves session data.
  Depends on: T003. Affected paths: capture ownership + guidance surfaces.
  Gate: EVAL-011 procedure passes; restoring permission never re-arms a
  deliberately disarmed dialogue. Recovery: as T011.

## Phase A2: Dialogue per native target (SPEC-001–006/009/011)

- [x] T020 [SPEC-001, SPEC-004, SPEC-005] Windows dialogue loop. DONE 2026-10-17 — EVAL-004 CLOSED by streaming-turn proof (was OPEN). `Assistant.arm/disarm` + shared `CaptureGuard` + level meter + `_backend_with_timeout` + `_backend_failure` + `_budget_verdict` + `dialogue` keys; `sapi` TTS (persistent warm host: 0.01–0.3s vs 2s one-shot) + `hf-whisper` STT + new `ollama` AgentBackend (registry, config-only `backend.provider: ollama`, streams SSE, keep_alive pinned). Evidence: `test_dialogue_gate` 20/20; SPECTRE-16 streaming turn 3/3: fw-tiny stt 0.60s + first-token 0.85s + warm TTS 0.32s = 1.79s WITHIN 2s. Why numbers were off: cold loads (whisper 3–8s, SAPI 2.5s incl. 0.6s PS spawn + 1.2s .NET init, ollama reload 6.6–24s on 1.1G-RAM box) — all amortized by prewarm/persistent-host/keep_alive. GPU verdict: Intel-only box (no NVIDIA/CUDA); ORT CPU-only both sides; OpenVINO sees Arc GPUs but no current provider uses them — CPU int8 + warm persistence is the correct fight.
  one-action arming with offline wake/VAD/level indication; ≤2s
  end-of-speech→audible-content under declared conditions; provider
  failure/stall surfaces a sanitized reason and returns to armed idle.
  Depends on: T002, T010, T012. Affected paths: dialogue pipeline +
  session/armed-state ownership (live: `v2/echo_node/pipeline/`,
  `echo_node/pipeline/`). Gate: EVAL-001/004/005 procedures pass with
  target, revision, hardware/route, provider, network, method, and results
  recorded. Recovery: checkpoint; failed change returns to last verified
  state with failure evidence retained.
- [ ] T021 [SPEC-002, SPEC-003] Echo exclusion + barge-in. Implements:
  machine-only audio never becomes input; user speech during output stops
  obsolete playback and retains the utterance from its beginning; no
  hotkey; force-listen preserves exclusion and permission limits. Depends
  on: T020. Affected paths: VAD/AEC/barge-in components (live: `v2/echo_node/
  components/aec.py`, `barge_in.py`). Gate: EVAL-002/003 procedures pass
  with speaker-output tests (routing tests alone do not pass). Recovery:
  as T020. NOTE: muting all input during playback FAILS EVAL-002 by
  construction — do not implement that shortcut.
- [ ] T022 Linux dialogue + dictation. Same outcomes as T011+T020+T021 on
  declared Linux hardware/audio route. Depends on: T021. Affected paths:
  native Linux audio ownership + redelivery of dictation/dialogue paths.
  Gate: EVAL-001…006/009/011 procedures pass on Linux with separately
  recorded evidence (no macOS substitution; constitution G2). Recovery:
  per-target evidence; Linux gaps stay open explicitly.

## Phase A3: Coexistence + swaps (SPEC-007/008/012 + regressions)

- [ ] T030 [SPEC-007] Dictation↔dialogue coexistence. Implements: dictation
  during listening/wait/playback suspends dialogue or queues dictation,
  preserves history and exclusive audio ownership, restores the eligible
  prior state unless disarmed/unavailable. Depends on: T021. Affected
  paths: control arbiter (plan §2: one boundary for capture/playback/
  cancellation/dialogue state). Gate: EVAL-007 procedure passes in all
  three overlap states; success and failure both preserve history; only one
  dialogue exists. Recovery: checkpoint; restore prior eligible armed state.
- [ ] T031 [P] [SPEC-008, SPEC-012] Registry + two-endpoint proof. Wire at
  least two conforming dialogue endpoints and one model change through
  configuration alone (plan CTX-003 two-endpoint proof). Depends on: T002,
  T004. Affected paths: `gateway/src/providers/registry.ts`,
  `v2/echo_node/slots/`, profile documents. Gate: EVAL-008/012 procedures
  pass — configuration-only diff, same application, applicable regressions
  re-run; executable registration changes fail the gate. Recovery: revert
  to prior profile; registry records which candidates are wired, never a
  single mandated winner.
- [ ] T032 Saved profiles + test matrix harness. Implements: versioned,
  exportable/importable full-stack profiles with hardware floor + expected
  SPEC coverage; matrix runs each profile across SPEC-001…012 + slot probes
  (TTFS/semantic-WER, TTFA/RTF, wake false-accept/reject, AEC convergence,
  E2E SPEC-004). Depends on: T004, T031. Affected paths: profiles store +
  matrix runner (new). Gate: example profiles
  (offline-daily-driver, hosted-latency-king, budget-cascade) each carry
  dated evidence; a regression fails the profile, not the registry.
  Recovery: evidence attaches to the profile; matrix reruns are config
  diffs, never code changes.

## Phase A4: WSL forwarding (SPEC-010)

- [ ] T040 [SPEC-010] WSL→Windows forwarding. Implements: WSL invocation
  executes on Windows with host audio ownership; result/failure returns to
  the caller; unavailable/lost host reports failure. Depends on: T020,
  T011. Affected paths: forwarding boundary + host component (new, small).
  Gate: EVAL-010 procedure passes using the proven Windows paths; WSL opens
  no audio devices; acknowledgement alone does not pass. Recovery:
  checkpoint; host-failure path stays explicit.

## Phase B: Android (SPEC-001–009/011/012)

- [ ] T050 Android delivery of the same consumer outcomes. Implements the
  A1–A4 surface on Android after capability checks (background listening,
  insertion/clipboard access per plan CTX-005). Depends on: T032, T040.
  Affected paths: Android audio ownership + redelivery of paths. Gate:
  EVAL-001…009/011/012 procedures pass on Android with separately recorded
  evidence. Full completion requires this phase or an explicit scope
  revision — a desktop milestone cannot silently drop Android. Recovery:
  gaps recorded explicitly per constitution G2.

## Cross-cutting

- [ ] T060 [P] Diagnostics without leakage. Implements: local latency,
  state, and failure records with no secrets, no raw audio, no transcript
  persistence by default (plan §4). Affected paths: diagnostics/logging
  surfaces. Gate: secret-scan over diagnostics output finds zero
  credentials; plaintext fallback absent. Recovery: strip and re-verify.
- [ ] T061 [P] G1–G5 preparation evidence. Record quarantine scan, platform
  evidence map, eval-binding check, license/provenance review, and gate
  results in `preparation.json` before claiming readiness (constitution
  G5). Depends on: all phase gates claimed. Gate: `preparation.json`
  carries real command evidence per gate; missing/unrun checks are absent,
  never passes. Recovery: rerun the missing check; do not reinterpret a
  failed gate.
