---
date: 2026-10-15
ver: 1.1.0
author: system adjudicator
tags: [strata, plan, voice-unification, system-derived, architecture]
---

# Voice unification plan

## 1. Derivation and evidence

Derive architecture from `intent.md` and `spec.md`: one maintainer, native audio,
hands-free interruption, separate dictation, configuration-only compatible swaps,
and a 2-second response target. Part 1 §1.2 governs historical selections.

This review inspected the ten supplied documents. The workspace has no usable
Git metadata and `archive-inputs/` is empty. Historical repository, research, and
runtime claims remain unverified; their absence does not prove an empty decision
ledger. Decisions below are design choices, not tested implementation claims.

## 2. Architecture overview

```text
voice-agent/
  apps/echo/      conversational dialogue
  apps/dictate/   separately invoked hotkey dictation
  specs/         governing pack and later tasks
  docs/          setup, provider contract, acceptance evidence
```

This is a logical layout, not an existing-directory inventory. Native platform,
configuration, provider, and control responsibilities may share code. Choose
process boundaries during implementation; separate invocation does not require
separate uncoordinated processes. One control boundary arbitrates capture,
playback, cancellation, and dialogue state. VoiceInk remains independent;
predecessor implementations stay external and read-only. Android is delivered
later within the same product scope. No cockpit shell is required by the intent.

## 3. Decisions

**CTX-001: One repository, VoiceInk excluded.**

- Derivation: intent §§2, 7, 9; SPEC-012.
- Use the proposed `aaaronmiller/voice-agent` home for non-VoiceInk work; verify
  its exact identity before migration. Absorbing VoiceInk contradicts scope;
  separate repositories per job increase maintenance and coordination.
- Cost: shared conventions need discipline. No remote migration or twin archival
  is claimed complete by this document.

**CTX-002: Native audio ownership per OS; WSL forwards control.**

- Derivation: intent §3, §5; SPEC-010.
- Windows owns its capture/playback even for WSL callers. Other targets use
  their native audio environment. Return the action's result, including host
  unavailability; an acknowledgement does not prove completion.
- Cost: a small native host component and forwarding boundary. The current
  ownership constraint suffices; old reliability claims are not proof.

**CTX-003: Configuration-driven compatible providers.**

- Derivation: intent §§4–5, §7; SPEC-008/009/012.
- Define supported speech, session, cancellation, and credential capabilities.
  Keep integrations behind that boundary; configuration selects conforming
  endpoints/models without executable registration or changes to core paths.
- Hardcoded providers fail the swap goal. Arbitrary future protocols are not
  promised interchangeable; new capabilities require a separate design change.
- Cost: boundary design and a two-endpoint proof. Select actual technology using
  current capability evidence, not inherited pins or provider defaults.

**CTX-004: Re-derive turn-taking; coordinate dictation.**

- Derivation: intent §§3–4, §6; SPEC-001/002/003/005/007/011.
- Detect genuine user speech during playback while excluding machine output.
  Stop obsolete playback and retain leading user speech. Import neither the old
  implementation nor its fixed state count.
- For dictation, suspend dialogue work/playback, preserve committed history,
  acquire audio ownership, then restore the prior eligible armed state. Disarm
  or permission loss prevents restoration; late results cannot restart output.
- Cost: native acoustic and coexistence testing. Muting all input during playback
  and relying solely on separate processes both fail required behavior.

**CTX-005: Dictation first; retain all target coverage.**

- Derivation: intent §§1, 3, 5; SPEC-006/007/009/011.
- Start with Windows dictation, the smallest acceptance surface, then dialogue,
  Linux, coexistence, and WSL. Android follows as a required later phase.
- Investigate target restrictions before promising delivery, especially background
  listening and insertion/clipboard access. Unsupported behavior remains a gap.
- Cost: early capability checks; a predecessor's working-loop claim is not a pass.

**CTX-006: Keep the live tree's MIT license; no relicensing.**

- Derivation: Part 1 §1.3; constitution G4.
- The shipping lineage is MIT and actively developed — KEEP MIT. The GPL-3.0
  draft direction is withdrawn. Check provenance and required notices before
  admitting implementation material. Keep VoiceStudio implementation and
  assets out. VoiceInk port, if ever, stays a separate concern.

**CTX-007: Separate evaluations from implementation.**

- Derivation: the specification's EVAL bindings; constitution G3.
- Keep public criteria and IDs here; private cases and expected results belong
  outside the repository, conventionally `~/.strata/evals/voice-unification/evals.md`.
  The implementer does not inspect private cases; a separate evaluator runs them.
  Verify matching cases exist before reporting evaluation readiness.
- Cost: maintaining separate cases and results. An external path does not itself
  establish access isolation; this plan mandates no new isolation infrastructure.

## 4. Data and components

- Configuration: validated, versioned app settings; compatible provider choices,
  action bindings, protected-secret references. Invalid settings stop the affected path.
- Dialogue: one ephemeral session with configurable turn memory, armed state,
  and current operation ownership; discard content at session end.
- Dictation: capture, transcribe, insert once into the intended field, restore
  clipboard where still owned. Preserve newer clipboard changes and report failures.
- Diagnostics: local latency, state, and failure records without secrets; no
  raw audio or transcript persistence by default.
- Shared facilities: configuration validation, secret access, native platform
  operations, and control coordination. Provider-specific behavior stays behind
  the provider boundary rather than leaking into dialogue or platform code.

## 5. Deployment and security

Windows native is primary; Linux native is secondary; WSL forwards to Windows;
Android follows in Phase B. VoiceInk's macOS lifecycle remains separate.

Show capture state, honor disarm across components, protect local control from
unintended callers, and validate configuration before device/provider access.
Use protected local secrets with no plaintext fallback or diagnostic leakage.
Do not silently redirect credentials to an unexpected endpoint.

## 6. Preparation and recovery

Follow constitution, specification, clarification, plan, analysis, then tasks.
Record unresolved capability limits and G1–G5 evidence in `preparation.json` before
generating `tasks.md`. Evaluate current provider capabilities when selecting
implementations; no named stack is selected here.

Checkpoint existing work/configuration before implementation or migration,
without exporting secrets. Failed changes return to the last verified state
and retain failure evidence. This merge does not pass runtime gates or execute
Part 1 disposition actions.

## 7. Delivery phases and acceptance

| Phase | Work | Decisive coverage |
|---|---|---|
| A1 | Windows dictation and configuration | SPEC-006/009/011 |
| A2 | Windows dialogue, then Linux dialogue and dictation | SPEC-001–006/009/011 on each native target |
| A3 | Dictation coexistence and compatible provider/model swaps | SPEC-007/008/012 plus affected regressions on both desktops |
| A4 | WSL forwarding and host-failure reporting | SPEC-010 using the proven Windows paths |
| B | Android delivery of the same consumer outcomes | SPEC-001–009/011/012 on Android |

Measure the response target with actual hosted-service and physical audio
evidence under declared conditions. Routing tests alone do not prove latency;
speaker-output exclusion needs speaker tests. Report each target's results
separately. Full completion requires all in-scope targets or an explicit scope
revision; a desktop milestone cannot silently drop Android.
