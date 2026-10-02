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
  - Status (2026-10-01): **built, awaiting real-hardware validation.**
    `echo_node/slots/` (SlotType, Capability, 8 ABCs), `registry.py`
    (explicit registration, `working()`, `validate_all()`),
    `validation.py` (graceful probes). All existing components migrated as
    providers under their exact config names; dispatch in
    `InterruptibleSpeaker`/`Assistant`/`validate_config` routes through the
    registry with historical fallbacks preserved. Dropdowns wired:
    avatar popup (STT/TTS/backend), incarnations chooser (regenerated at
    load, YAML fallback kept). Conformance suite
    `echo_node/tests/test_phase_a.py` — 93 checks pass on a bare VM.
    Validators honestly report missing models/binaries/keys on machines
    without them. Not yet run on GPU/audio hardware — that pass is the
    real gate before Phase B.
- **Phase B — SubprocessAdapter.** JSON-RPC-over-stdio adapter; 2–3 external
  adapters as proof (e.g. a whisper.cpp STT, a Piper-style TTS). Validates the
  "any program can take a slot's place" claim end to end.
  - Status (2026-10-01): **built, awaiting real-hardware validation.**
    `echo_node/adapters/` — `protocol.py` (shared JSON-RPC 2.0 framing,
    child main loop, PCM/wav helpers; importable without the echo_node
    package so adapter children stay self-contained), `subprocess_adapter.py`
    (host: lazy spawn, initialize handshake with version check,
    per-call timeouts → `AdapterTimeout`, transparent restart-on-crash
    with `max_restarts` → `AdapterCrashed`, kill-on-idle reaping,
    malformed child lines logged-and-ignored, stderr drained),
    `__init__.py` (`register_external_providers`: config-schema
    validation, `builtin:` allowlist resolution, name-collision/unknown-slot
    startup errors), three executable reference adapters
    (`stt_whispercpp.py`, `tts_piper.py`, `stt_reference.py` — faster-whisper
    shim that never downloads models), `PROTOCOL.md` (spec + trust model).
    Slots served: stt, tts, vad, wake_word, agent_backend (`chat` method).
    The config file is the trust boundary — settings UI never accepts
    executable paths; validated externals appear in the existing
    registry-driven dropdowns marked " (external)".
    Conformance suite `echo_node/tests/test_phase_b.py` — 37 checks pass
    on a bare VM (fake adapter modes: echo/hang/crash-once/crash-always/
    garbage; shipped adapters honestly report missing binaries/models).
    Batch-only; no streaming methods yet. Real gate: run a whisper.cpp /
    Piper adapter on Aaron's hardware.
- **Phase C — substitution sweep**, in the payoff order of §2.
  - Status (2026-10-01): **items a–d built, awaiting real-hardware validation.**
    Defaults and default provider selection unchanged everywhere; all new
    providers register `experimental=True` (gated behind
    `ECHO_INCLUDE_EXPERIMENTAL=1`); no validator downloads or crashes on
    machines without the deps/hardware.
    - (a) **Silero v6 VAD** — `echo_node/components/vad.py::SileroVAD`,
      registered as `vad/silero`. Wraps the `silero-vad` 6.x API
      (`load_silero_vad(onnx=True)`, 512-sample windows, max window
      probability + RMS floor). `validate()` probes `silero_vad` (+ torch)
      module presence only — never loads the model (first load downloads
      weights). The old `SileroVad` alias still points at OpenWakeWordVad
      for historical config compat.
    - (b) **Echo cancellation** — `echo_node/components/aec.py::AecAudioIO`,
      registered as `audio_io/aec-webrtc`. WebRTC AEC3 via the
      `pywebrtc-audio` PyPI package (pre-built wheels; rejected the
      SWIG/meson build-from-source bindings and speexdsp's older MDF).
      Wraps `MicStream`'s capture path; a far-end ring buffer fed by
      `feed_far_end()` supplies the speaker reference. Honest validator
      notes true full-duplex AEC needs hardware validation. Wiring is
      done: the orchestrator resolves the audio_io provider through the
      registry (`audio.provider`, defaulting to `audio.backend`) and
      passes `feed_far_end` to `InterruptibleSpeaker` as
      `far_end_callback` when `aec-webrtc` is active.
    - (c) **TTS tiers** — `Qwen3TTS` (`tts/qwen3-tts`, Qwen3-TTS-0.6B,
      `qwen_tts.Qwen3TTSModel`, streaming) and `VoxCPMTTS` (`tts/voxcpn`,
      VoxCPM-0.5B, `voxcpm.VoxCPM`) in `components/tts.py`, following the
      Kokoro/Dots pattern (constructor presence-check, lazy model load,
      `generate_custom_voice` / `generate(...)` synthesis, CUDA-required
      validators that never download). API surfaces verified against
      upstream docs but NOT exercised on-device (no GPU here); exact
      kwarg names are commented as unverified. The VoxCPM 0.5B HF id
      (`openbmb/VoxCPM`) is a guess — `openbmb/VoxCPM2` is the verified
      2B id; override via `model_id`.
    - (d) **LiveTalking harness** — `avatar_video/livetalking_musetalk.py::
      LiveTalkingMuseTalk`, registered as `avatar/musetalk-livetalking`,
      genuinely implements the `AvatarRenderer` contract (preload/play/stop)
      around the MuseTalk prototype. Remaining gaps (docstring + TASKS.md):
      not the real LiveTalking (no WebRTC, no interruption protocol, no
      task tracking); per-WAV batch generation, not chunked streaming;
      placeholder frame sink; coarse stop (no generation preemption);
      hardware validation pending.
    - Incidental fix: `EspeakTTS` never implemented `load()`, which made it
      abstract and broke `create_tts()`'s historical espeak-ng fallback —
      a Phase-A ABC-migration regression. Added the no-op `load()`
      (matches existing no-op `unload`/`warm`).
    - Conformance suite `echo_node/tests/test_phase_c.py` — 40 checks pass
      on a bare VM (validators honestly report missing deps; experimental
      gating verified with stubbed validators; `test_phase_a.py` and
      `test_phase_b.py` stay green).
    - Real gate: Aaron's hardware — GPU for Qwen3/VoxCPM/MuseTalk, mic +
      speakers for AEC3, torch for Silero.
  - Item 5 — `tools/stt_ab.py` A/B harness: runs 2+ STT providers over the
    same WAVs, records transcripts + latency to JSON/CSV, errors recorded
    not crashed (17 tests).
  - Item 6 — `LlamaSwapBackend` (`backends.py`, config key `"llama-swap"`,
    experimental): talks to llama-swap's OpenAI-compatible endpoint
    (`llama_swap.base_url`, default `http://127.0.0.1:8080`); validator
    probes `/v1/models` with a 5s timeout, honest-missing when no server
    (12 tests).
- **Phase D — Wyoming TCP adapters, avatar slot, capability intersection.**
  The UI only offers combinations whose capabilities intersect (e.g. no
  streaming-only TTS paired with a batch-only playback path).
  - Status (2026-10-01): **Wyoming TCP adapters built, awaiting real-hardware
    validation.** `echo_node/adapters/wyoming.py` — stdlib-only Wyoming
    client (`WyomingAdapter` base: per-call TCP connect, deadline-bounded
    reads, clean close; `WyomingSTT` / `WyomingTTS` / `WyomingWakeWord`).
    Framing and event names verified against the upstream wyoming source
    (OHF-Voice/wyoming main, 2026-10-01): header line
    `{"type","version","data_length"[, "payload_length]}` + data blob +
    payload; `transcribe`→`transcript`, `synthesize`→audio stream,
    `detect`→`detection`/`not-detected`. The `wyoming` PyPI package is
    deliberately NOT used (not installed; raw sockets keep the host
    stdlib-only). Config: `transport: tcp` entries in `external_providers:`
    with `host` (default 127.0.0.1) + `port` (required; conventional
    faster-whisper 10300 / piper 10200 / openwakeword 10400 — documented
    defaults, not re-verified live); `command`/`args` are startup-fatal
    for tcp entries. Wyoming providers register `external=True`
    (" (external)" in dropdowns); `validate()` is a 3 s TCP connect
    probe that never raises. Slots: stt/tts/wake_word only — the Wyoming
    VAD events are not a per-chunk query. Conformance suite
    `echo_node/tests/test_phase_d.py` — 35 checks pass on a bare VM
    against fake Wyoming TCP servers; `test_phase_a`/`test_phase_b`
    still green. Real gate: run against wyoming-faster-whisper,
    wyoming-piper, wyoming-openwakeword on real hardware. Still open in
    Phase D: the avatar slot and capability-intersection UI filtering.

    Post-D additions (2026-10-01, on main):
    - **Streaming TTS playback** — `TTSProvider.generate_stream()` is now an
      optional slot-ABC method; `InterruptibleSpeaker` plays chunks as they
      arrive (aplay raw-float stdin / sounddevice OutputStream) with barge-in
      polled between chunks, blocking fallback, and `t_tts_first_chunk` as
      first-*audio* latency. WyomingTTS got a real `generate_stream` (it
      already received audio-chunk events); Qwen3TTS's `streaming=True` was
      corrected to `False` (upstream qwen_tts is offline-only). Avatar
      lip-sync keeps the blocking path. Suite:
      `echo_node/tests/test_tts_streaming.py` — 36 checks.
    - **Capability-aware dropdown tooltips** — STT/TTS/backend dropdowns show
      a one-line Capability summary (streaming/batch, languages, CPU/GPU,
      license) above the validation reason in the tooltip; Qt-free
      `format_capability_summary()` in `adapters/ui_helpers.py`.
    - **Hardware testing guide** — `docs/HARDWARE_TESTING.md`: ordered
      checklist (validate_all, per-slot smoke tests, STT A/B, Wyoming
      round-trips, AEC on/off, subprocess adapters, latency targets,
      turn-record log locations).

## 5. Open questions

- Branch strategy for the rework (feature branch off `muse/polish-pass`?).
- Keep the avatar inside v2 or split it into its own package?
- Which machine is the validation reference (the 4050 laptop?) and do agents
  get SSH/runner access to it for the hardware-gated tests?
