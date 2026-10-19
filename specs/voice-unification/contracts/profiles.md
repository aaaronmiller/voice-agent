---
date: 2026-10-17
ver: 1.0.0
author: voice-unification implementation (T004)
tags: [spec-prep, contract, voice-unification, profiles]
---

# Saved-profile document format (frozen)

Extends plan §8 (saved profiles). Versioned full-stack combination
documents, exportable/importable between machines. They REPLACE the
legacy `v2/profiles.yaml` + `v2/incarnations.yaml` shapes (template
indices, emoji names, scattered settings maps) — see migration note.

## Schema: `voice-profile/v1`

```yaml
format: voice-profile/v1
name: offline-daily-driver        # unique, kebab-case
version: 1                        # bump on any stack/coverage change
description: "..."                 # one line
stack:                            # registry (slot, name) pairs — T002 contract
  wake_word: openwakeword
  vad: openwakeword
  stt: faster-whisper
  tts: kokoro
  agent_backend: hermes
  avatar: none                    # or rhubarb / musetalk-livetalking
  audio_io: alsa                  # or sounddevice / aec-webrtc
  barge_in: vad_gated
dialogue:                         # gateway/v2 dialogue surface
  provider: hermes                # gateway registry name
  transport: websocket            # websocket | wyoming | livekit
params:                           # bounded overrides only (no free-form code)
  tts.speed: "1.0"
  barge_in.enabled: "true"
secrets:                          # references ONLY — never values
  hermes.api_key: env:HERMES_API_KEY
hardware_floor:                   # minimum declared target
  os: [linux]
  ram_gb: 8
  gpu: optional
  audio: "mic + speakers, 16kHz capture"
covers: [SPEC-001, SPEC-002, SPEC-003, SPEC-004, SPEC-005, SPEC-007,
         SPEC-009, SPEC-011]     # expected passing EVALs (evidence-bound)
evidence: []                      # dated entries appended by T032 matrix
```

## Rules

- `stack.*` values MUST be `(slot, name)` pairs resolvable via the T002
  registry contract; unknown names fail import validation (SPEC-009).
- `params` keys are dotted config paths; unknown keys fail validation.
- `secrets.*` values match `^(env|keyring|file):[^ ]+$`; anything else
  (inline values) fails validation with the field named, no value
  echoed (SPEC-009).
- `covers` is a claim, not proof: each entry needs a dated `evidence`
  item (target, revision, hardware/route, provider, network, method,
  result) before T032 marks the matrix cell green. Desktop-only
  evidence never covers Android (constitution G2).
- Export/import is byte-stable: YAML round-trip through the loader
  produces identical documents (canonical key order above, UTF-8,
  `\n`). Gate: the three live profiles round-trip byte-identical.
- Storage: `specs/voice-unification/profiles/*.yaml` (source of
  truth); runtime copies under user config dir at implementation time.

## Migration from live shapes

`v2/profiles.yaml` (name/template/settings) and `v2/incarnations.yaml`
(active index + per-OS shell commands + settings UI maps) are the
prototypes this format replaces:

- template/incarnation index → explicit `stack` + `dialogue` pairs.
- emoji display names → kebab-case `name` + `description`.
- scattered `settings` maps → bounded `params`.
- shell `command:` blocks → OUT (profiles describe stacks, not launchers).
- plaintext `api_key: ""` fields → `secrets:` references.

## Gate evidence (T004)

Loader + validator at `v2/echo_node/profiles.py`; three live profiles
ported to `specs/voice-unification/profiles/*.yaml`; round-trip probe
`python3 -m echo_node.tests.test_profile_roundtrip` green (byte-identical
export/import).
