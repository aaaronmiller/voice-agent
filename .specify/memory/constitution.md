<!--
  Sync Impact Report
  ==================
  Version change: N/A (initial) → 1.0.0
  Modified principles: N/A (first ratification)
  Added sections:
    - Core Principles (7 principles)
    - Technology Constraints
    - Development Workflow
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md — ✅ compatible (Constitution Check section references this file)
    - .specify/templates/spec-template.md — ✅ compatible (no constitution-specific references to update)
    - .specify/templates/tasks-template.md — ✅ compatible (phase structure aligns with principles)
  Follow-up TODOs: None
-->

# Echo-Node Constitution

## Core Principles

### I. Stitch, Don't Rebuild

Every pipeline component (STT, TTS, VAD, wake word, LLM, avatar)
MUST use an existing open-source library as a black box. The project
builds ONLY glue code: provider abstractions, config system, state
machine, integration adapters, and UI shell. Before writing any new
component, contributors MUST search for an existing library that
solves the problem. If one exists and meets requirements, it MUST be
used. Custom implementations are permitted ONLY when no suitable
library exists or when an existing library fails a documented
evaluation.

### II. Split-Stack Ownership

The system is a 3-layer split-stack. Each layer has exclusive
ownership of its domain:

- **Python Audio Worker** MUST own all mic capture, ML inference
  (STT, TTS, VAD, wake word), audio playback, echo cancellation,
  and the 5-state machine. No other layer makes audio or state
  decisions.
- **Bun + Hono Gateway** MUST act as a relay only. It connects
  frontends, integration adapters, and the Python worker. It adds
  session management and REST API. It MUST NOT touch raw audio or
  make pipeline decisions.
- **Svelte 5 Frontend** MUST be a visualizer only. It renders state
  events and drives avatar lip-sync from audio data received via
  the gateway. It MUST NOT call ML models or make pipeline
  decisions.

Violations of layer ownership MUST be rejected during review.

### III. Config-Driven Pipeline

All pipeline behavior MUST be driven by `config.yaml`. No provider
selection, model path, threshold, or pipeline parameter may be
hard-coded. Adding or swapping a provider MUST require ONLY a
config change and a restart — zero code modifications. The config
schema MUST be validated at startup with clear error messages for
invalid values.

### IV. Provider Abstraction

Every ML component (STT, TTS, VAD, wake word, LLM) MUST implement
an abstract base class (ABC) defined in `worker/providers/base.py`.
Each ABC MUST define: `initialize()`, the core processing method
(streaming where applicable), `shutdown()`, and
`vram_requirement_mb`. Adding a new provider means subclassing the
ABC and registering the provider name in `config.yaml`. No provider
may depend on another provider's internals.

### V. Resource-Aware Loading

The system MUST calculate total VRAM requirements from all selected
providers BEFORE loading any models. If the combination exceeds
available VRAM, the system MUST warn the user and suggest
alternatives (smaller models, CPU fallback) rather than crashing
mid-load. CPU/OpenVINO fallback MUST be supported for environments
without CUDA (e.g., Intel Arc GPUs).

### VI. Dual-Mode Operation

The system MUST support two runtime modes with no code divergence:

- **Web UI mode**: Svelte 5 SPA with TalkingHead 3D avatar,
  waveform visualizer, transcript panel, and theme frames.
- **Headless CLI mode**: Terminal-only operation with text output
  and audio-only responses, no graphical dependencies.

Both modes MUST use the same Python worker and gateway. Mode
selection MUST be config-driven.

### VII. Streaming-First Latency

The full voice cycle (end-of-speech to first audio playback) MUST
target under 2 seconds. To achieve this:

- STT MUST stream partial transcripts as audio arrives.
- LLM responses MUST be streamed token-by-token.
- TTS MUST begin synthesizing at sentence boundaries (streaming
  sentence chunker), not after the full LLM response completes.
- Audio playback MUST begin as soon as the first TTS chunk is
  ready.

Blocking any pipeline stage on full completion of the previous
stage is a latency violation and MUST be flagged during review.

## Technology Constraints

- **Python Worker**: Python 3.11+, asyncio, PyAudio/sounddevice,
  ONNX Runtime, PyTorch (inference only), SpeexDSP.
- **Gateway**: Bun runtime, Hono framework, TypeScript.
- **Frontend**: Svelte 5 (SvelteKit), TalkingHead (met4citizen).
- **Inter-layer communication**: WebSocket only. Gateway ↔ Worker
  uses binary audio + JSON control messages. Gateway ↔ Frontend
  uses JSON events.
- **Platform targets**: WSL2 (primary), native Linux, macOS.
  Windows native is NOT a target. WSL2 audio MUST auto-detect
  PipeWire/PulseAudio.
- **Models directory**: `models/` is gitignored. A `setup.sh`
  script MUST download all required models.
- **No paid dependencies**: All runtime dependencies MUST be
  free/open-source. Cloud API providers (OpenRouter, OpenAI,
  Gemini) are optional user-configured endpoints, not project
  dependencies.
- **Gemini Live mode**: The system MUST support an optional
  Gemini Flash Live API mode as an alternative to the local
  modular pipeline. This mode bypasses local STT/TTS (Gemini
  handles both server-side) but MUST still integrate with the
  existing config system, wake word detection, and frontend.

## Development Workflow

- **Phased delivery**: Implementation follows user-story priority
  order (P1 MVP first, then incremental P2/P3 stories). Each
  story MUST be independently testable and deployable.
- **Existing research mandate**: Before building any component,
  search for existing libraries, skills, and GitHub projects that
  solve the problem. Surface findings before writing code.
- **Provider addition guide**: Adding a new STT/TTS/VAD/LLM
  provider MUST follow the documented process in
  `docs/provider-guide.md`: subclass the ABC, implement required
  methods, register in config schema, add integration test.
- **Changelog**: All changes MUST be logged in `CHANGELOG.md`
  under `[Unreleased]` with appropriate category headers.

## Governance

This constitution supersedes ad-hoc decisions about architecture,
layer boundaries, and provider design. Amendments require:

1. A documented rationale for the change.
2. Review of impact on existing providers and integrations.
3. Update to this file with incremented version number.
4. Propagation check across `.specify/templates/` and project
   documentation.

Versioning follows semantic versioning:
- **MAJOR**: Principle removal, redefinition, or architectural
  change that invalidates existing providers/integrations.
- **MINOR**: New principle added or existing principle materially
  expanded.
- **PATCH**: Clarifications, wording fixes, non-semantic
  refinements.

All code reviews MUST verify compliance with layer ownership
(Principle II) and config-driven behavior (Principle III).
Complexity beyond what a principle permits MUST be justified in
the PR description.

**Version**: 1.0.0 | **Ratified**: 2026-03-29 | **Last Amended**: 2026-03-29
