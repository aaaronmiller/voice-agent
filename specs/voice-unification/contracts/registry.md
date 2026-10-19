---
date: 2026-10-17
ver: 1.0.0
author: voice-unification implementation (T002)
tags: [spec-prep, contract, voice-unification, registry]
---

# Registry contract (frozen)

Extends plan CTX-003 + §8. Two coexisting registries; one rule each.

## Rule (both sides)

Adding a component = registering descriptor + probe (+ profile entry);
core paths never change (SPEC-012). Executable registration changes
(e.g. a new `registerProvider("…")` call in gateway core, a new
`reg.register(…)` line inside `register_builtin`) are NOT configuration —
EVAL-008/012 fail on them.

## Python: `v2/echo_node/slots/` (slot ABCs + registry)

- Slot set (frozen enum `SlotType`): `wake_word`, `vad`, `stt`, `tts`,
  `agent_backend`, `avatar`, `audio_io`, `barge_in`.
- Capability descriptor fields (frozen `Capability` dataclass): `name`,
  `version` (default `"unknown"`), `languages` (default `[]`),
  `streaming` (default `False`), `vram_gb` (default `None`),
  `gpu_required` (default `False`), `license` (default `"unknown"`),
  `network` (default `False`), `notes` (default `""`). Unknowns stay
  `"unknown"` — never guessed.
- Conformance probe: classmethod `validate(config) -> ValidationResult`
  (`ok`, `reason`, `details`); validators never raise — exceptions become
  a failing `ValidationResult`. A `validate_fn` override is allowed when
  one class registers under several names with different probes
  (e.g. alsa vs sounddevice).
- Registration path (no core edits): construct your own
  `ProviderRegistry()` (or pass one into `register_builtin`), call
  `register(slot, name, cls, experimental=…, capabilities=…,
  validate_fn=…)`. `get_registry()` singleton + `register_builtin` are
  core — adding built-ins there is a code change, not configuration.
- Conformance proof: `validate_all()` report + `working(slot)` dropdown
  source (passes validation only; experimental hidden unless
  `ECHO_INCLUDE_EXPERIMENTAL=1`).

## Gateway: `gateway/src/providers/registry.ts` (dialogue providers)

- Descriptor: `VoiceProvider` interface + `ProviderConfig` in
  `gateway/src/types.ts`; availability = API key present (cloud) or
  always-available (local) per `listAvailableProviders`.
- Probe: `createProvider(name, config)` returns non-null + `init()`
  resolves; `null` = unknown name or failed init (logged, never throws).
- Registration path: `registerProvider(name, factory)` with lazy import
  inside the factory (keeps memory minimal).
- Live names: `stub`, `gemini-live`, `openai-realtime`, `hermes`,
  `pi-agent`, `python-worker`. SPEC-008 proof (T031) wires its two
  endpoints via provider *selection* in configuration, not by editing
  this registry file.

## Gate evidence (T002)

A second conforming stub (Python `STTProvider` subclass + gateway
`VoiceProvider`) registers through the documented paths with zero
core-path edits; `validate_all()` + gateway `bun test` still green.
Probe script: `v2/echo_node/tests/test_registry_stub_gate.py`
(gated throwaway, kept — it IS the EVAL-012 regression tripwire).
