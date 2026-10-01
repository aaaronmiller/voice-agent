# Echo-Node v2 — Improvement Roadmap: pluggable components + validated provider registry

Goal: every pipeline slot becomes swappable — built-in providers plus any external
program implementing the slot contract. Settings shows dropdowns of **validated
alternatives only**. No free-form executable paths (arbitrary command execution
in a settings UI, untestable matrix — every precedent surveyed avoids this).

## 1. Architecture

**Per-slot ABCs** (`echo_node/slots/`): `WakeWord`, `VAD`, `STT`, `TTS`,
`AgentBackend`, `AvatarRenderer`, `AudioIO`, `BargeInPolicy`. Each ABC defines:
- the method contract,
- a `Capability` descriptor dataclass (name, version, languages, streaming vs
  batch, vram_mb, license, needs_network, needs_gpu),
- a `validate()` classmethod running a real workload probe (Wyoming-style:
  sample WAV in → non-empty result out; TTS: synth a sentence, assert RMS > 0).

**Registry** (`echo_node/registry.py`): discovers built-in providers via entry
points (`echo_node.stt`, … — the OpenVoiceOS plugin-manager pattern) plus
config-declared external adapters. Runs validators at startup and on settings
change. `registry.working(slot)` is the **only** source for settings dropdowns —
a provider that fails validation vanishes from the UI instead of erroring at
runtime (the ESPHome/Wyoming capability-advertisement pattern).

**SubprocessAdapter**: one generic adapter per slot ABC. Spawns a *declared*
command, speaks JSON-RPC 2.0 over stdio. A provider entry is
`{slot, command, args, protocol_version}` — auditable, no path injection,
process lifecycle (spawn/health-check/kill-on-idle) owned by Echo-Node. This is
the cheapest way "any program implements a slot" (voice2json's Unix-pipeline
philosophy). Wyoming-style TCP adapters can be added later for non-Python
components without changing the ABCs.

**Contract-first**: in-process plugins and external adapters share the exact
same ABC, so validation probes target the contract, not the implementation.

## 2. Component substitution candidates (surveyed Sept 2026)

Ordered by payoff. "Strictly better" = adopt; the rest = A/B on real hardware.

1. **VAD → Silero v6** (`silero-vad` 6.2.x, MIT). Strictly better than the stale
   bundled model: 16% fewer errors on noisy data, same ~1.5% CPU. Drop-in.
2. **Barge-in rework** (biggest UX win). PipeWire `libpipewire-module-echo-cancel`
   (WebRTC AEC3) removes the threshold-boost hack at its root → LiveKit
   turn-detector for semantic end-of-utterance (~10ms, CPU) → Pipecat-style
   interruption state machine (arm only while TTS plays; immediate vs buffered
   modes) → text-domain echo rejection as the cheap second net (fuzzy-match
   transcripts against text-in-flight, ~40 lines).
3. **TTS tiers**: add **Qwen3-TTS-0.6B** (97ms first-packet streaming, 3-sec
   zero-shot clone, Apache-2.0 — verify the quantized path fits 6GB VRAM) and
   **VoxCPM-0.5B** (expressive prosody tier, Apache-2.0, fits 6GB). Kokoro stays
   the default low-latency tier.
4. **Avatar**: wrap MuseTalk v1.5 in **LiveTalking** (the production harness the
   prototype lacks: interruption, WebRTC, task tracking). Evaluate LivePortrait
   as a second renderer (MIT code/weights, but bundled InsightFace models are
   research-only — swap the detector).
5. **STT**: A/B **Qwen3-ASR-0.6B** (52 langs, Apache-2.0) vs Parakeet v3 on real
   traffic. Consider sherpa-onnx as the unified runtime (one dep for
   Parakeet/Whisper/Moonshine/VAD/KWS).
6. **Local model routing**: **llama-swap** replaces the ad-hoc Hermes server
   pattern — hot-swaps local models, exposes OpenAI- *and* Anthropic-compatible
   endpoints.
7. **Wake word**: prototype **LiveKit wakeword** (0.08 FP/hr reported) vs
   openWakeWord A/B on a real mic. Keep openWakeWord default until then.
   (Porcupine excluded — free tier retired June 2026.)

**Watch, don't adopt**: Fish Speech S2 (non-commercial license), Voxtral-4B-TTS
(VRAM), Ditto (16GB+), Kyutai Moshi full-duplex (architecture ideas only),
Moonshine v2 streaming STT (promising, English-first — revisit).

**Unverified, check before adopting**: Qwen3-TTS VRAM on 6GB, gpt-oss-20b
VRAM on the 4050, Nemotron-3.5-ASR license, sherpa-onnx KWS model license.

## 3. Validation & testing strategy

- **Per-provider `validate()`**: workload probes per slot (STT: transcribe a
  fixture WAV → non-empty; TTS: synth → RMS > 0 + expected sample rate; VAD:
  fixture with known speech/silence boundaries; wake: fixtures with/without
  the phrase).
- **Conformance suite**: every registry provider must pass its slot's contract
  tests. Interface tests need no GPU; real validation needs the hardware matrix
  (the 4050-class laptop is the reference target).
- **"Proactively support any software that fits"**, made concrete: the
  conformance suite *defines* "fits". We can't QA the universe, but anyone —
  us, contributors, future agents — can add a provider by implementing the ABC
  and passing validation. New candidates enter as `experimental` until
  validated on target hardware.
- **Cutting-edge sweep**: a scheduled job checks registered providers for new
  releases and proposes candidates; promotion to a settings dropdown requires
  passing validation, never just a version bump.

## 4. Phased plan

- **Phase A — slots + registry + validators.** Define ABCs, capabilities, and
  the registry; migrate every existing component as a first-party provider
  (no behavior change). Settings dropdowns for STT/TTS/backend read from
  `registry.working(slot)`.
- **Phase B — SubprocessAdapter.** JSON-RPC-over-stdio adapter; 2–3 external
  adapters as proof (e.g. a whisper.cpp STT, a Piper-style TTS). Validates the
  "any program can take a slot's place" claim end to end.
- **Phase C — substitution sweep**, in the payoff order of §2.
- **Phase D — Wyoming TCP adapters, avatar slot, capability intersection.**
  The UI only offers combinations whose capabilities intersect (e.g. no
  streaming-only TTS paired with a batch-only playback path).

## 5. Open questions

- Branch strategy for the rework (feature branch off `muse/polish-pass`?).
- Keep the avatar inside v2 or split it into its own package?
- Which machine is the validation reference (the 4050 laptop?) and do agents
  get SSH/runner access to it for the hardware-gated tests?
