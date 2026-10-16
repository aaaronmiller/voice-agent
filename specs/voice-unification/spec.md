---
date: 2026-10-15
ver: 1.1.0
author: system adjudicator
tags: [strata, spec, voice-unification, eval-binding, contract]
---

# Voice unification specification

Public behavioral contract derived from `intent.md`. Each SPEC-ID retains its
matching EVAL-ID; private cases follow constitution G3. Platforms express scope,
not implementation choices.

## 1. Acceptance conditions

Armed idle means ready without re-arming. Disarming stops capture/playback and
prevents pending work from restarting them. Dictation alone does not arm dialogue.
User input excludes ordinary assistant entries.

Record target, revision, hardware/audio route, provider, network conditions,
measurement method, and results. Windows, Linux, and Android require separate
native evidence; SPEC-010 covers Windows through WSL. Restrictions remain gaps,
not passes. macOS evidence cannot substitute.

## 2. Contract clauses

### 2.1 Hands-free dialogue

**SPEC-001** [EVAL-001] WHEN the user arms an idle system with valid configuration
and permission, THE system SHALL indicate readiness and remain armed across turns
until disarmed or unavailable. Local wake detection, speech-activity detection, and input-level indication
SHALL work offline.

- Eval: one action enables repeated turns; offline controls work; disarm during
  listening, waiting, or playback prevents later capture/output.
- Trace: intent §§3–5, §8 story 1.

**SPEC-002** [EVAL-002] WHILE armed, THE system SHALL exclude machine-only audio
from user input and new turns while continuing to detect genuine user speech.

- Eval: playback, music, and notifications create no false user turns; mixed
  audio retains human speech. Muting all input cannot satisfy SPEC-003.
- Trace: intent §3, §5, §6, §8 story 2.

**SPEC-003** [EVAL-003] WHEN the user speaks during machine output, THE system
SHALL stop that output and retain the utterance, including its beginning, without
a hotkey. Force-listen SHALL preserve echo exclusion and permission limits.

- Eval: interruption wins; obsolete output stays canceled. Force-listen is distinct
  from dictation and cannot activate disarmed dialogue.
- Trace: intent §3, §6, §8 story 2.

**SPEC-004** [EVAL-004] WHEN the user finishes a dialogue utterance under declared
reference conditions, THE system SHALL produce audible response content within
2 seconds.

- Eval: measure actual speech end to actual audible content, including all
  intervening work; report trials and failures. Chimes, filler, and errors do not count.
- Trace: intent §4.

**SPEC-005** [EVAL-005] WHEN a provider fails or stalls beyond a configured finite
timeout, THE system SHALL report a sanitized reason and return eligible armed
dialogue to armed idle. Disarm or unavailable prerequisites SHALL keep it disabled.

- Eval: refusal, connection loss, and stalled responses never hang silently;
  next speech works without re-arming; late results cannot restart canceled output.
- Trace: intent §§4, 6.

### 2.2 Dictation

**SPEC-006** [EVAL-006] WHEN dictation is triggered in a focused editable field,
THE system SHALL transcribe, insert once at the intended cursor, and restore prior
clipboard content and supported formats, preserving any newer concurrent copy.

- Eval: correct insertion/restoration; failure, cancellation, or focus change
  preserves data and never pastes into another field.
- Trace: intent §3, §5, §6, §8 story 3.

**SPEC-007** [EVAL-007] WHEN dictation is triggered during dialogue, THE system SHALL
suspend dialogue or queue dictation, preserve history and exclusive audio ownership,
then restore the eligible prior state unless disarmed or unavailable.

- Eval: dictation during listening, response wait, and playback never becomes a
  dialogue turn; success/failure preserves history. Only one dialogue exists.
- Trace: intent §4, §8 story 3.

### 2.3 Provider configuration

**SPEC-008** [EVAL-008] WHEN configuration selects another conforming dialogue
endpoint or model, THE system SHALL use it without source changes or rebuilding.

- Eval: distinct compatible endpoints and a model change use the same application;
  executable registration changes are not configuration.
- Trace: intent §§4–5, §8 story 4.

**SPEC-009** [EVAL-009] WHEN configuration is invalid, THE system SHALL refuse the
affected path before capture/provider contact and identify the field without
exposing secrets. Credentials SHALL use protected local references without
plaintext persistence or fallback.

- Eval: invalid fields, conflicting triggers, inline secrets, and unavailable
  secret storage fail visibly; valid references work without leaking values.
- Trace: intent §§3, 6.

### 2.4 Platform reach

**SPEC-010** [EVAL-010] WHEN invoked from a WSL shell, THE system SHALL execute the
requested action on Windows, retain host audio ownership, and report its result
or failure to the caller.

- Eval: forwarded actions complete; unavailable/lost host reports failure;
  acknowledgement is not completion; WSL opens no audio devices.
- Trace: intent §3, §5, §8 story 4.

**SPEC-011** [EVAL-011] IF microphone permission or a device is unavailable,
THE system SHALL disable affected capture and give actionable OS guidance without
retry loops. Runtime loss SHALL stop capture and preserve session data.

- Eval: denial, revocation, removal, explicit retry; permission restoration does
  not re-arm deliberately disarmed dialogue.
- Trace: intent §§3, 6.

### 2.5 Maintainability

**SPEC-012** [EVAL-012] WHEN a conforming provider/model changes, THE system SHALL
preserve dialogue, dictation, and platform behavior without modifying their code.

- Eval: configuration-only diff plus applicable regressions. New protocols or
  capabilities require a separate design change, not a configuration-only pass.
- Trace: intent §4, §7.

## 3. Exclusions and evidence status

macOS implementation, cloning/dubbing/audiobooks, and model training/serving are
excluded. No framework, provider, model, version, or audio interface is selected.
Evaluation bindings and runtime passes are unverified by this merge; desktop-only
evidence cannot complete Android scope.
