# Hardware testing guide

What the VM couldn't verify, in the order to verify it. Everything below
runs from the repo root (`~/code/voice-agent/`); the assistant itself
lives in `v2/`.

## 0. Sanity: imports + test suites

```bash
cd v2
python3 -m compileall -q echo_node avatar tools assistant_v2.py
for t in test_phase_a test_phase_b test_phase_c test_phase_d \
         test_external_ui_logic test_config_surgery test_aec_wiring \
         test_tts_streaming; do
  python3 -m echo_node.tests.$t 2>&1 | tail -1
done
python3 -m pytest echo_node/tests/test_stt_ab.py echo_node/tests/test_llamaswap.py -q
```

All green is the baseline. If anything is red here, stop — that's a repo
problem, not a hardware problem.

## 1. `validate_all()` — the provider census

Headless (mirrors assistant startup: config externals included):

```bash
cd v2 && python3 - <<'EOF'
from pathlib import Path
from assistant_v2 import load_config
from echo_node.adapters import register_external_providers
from echo_node.slots.registry import get_registry
config = load_config(Path("config.yaml"))
print("externals:", register_external_providers(config))
for key, res in sorted(get_registry().validate_all().items()):
    print(f"{'OK  ' if res['ok'] else 'MISS'} {key:32s} {res['reason'][:90]}")
EOF
```

Or in the GUI: settings → Agent tab → **Re-check** (same validators,
✓/✗ marks on the dropdowns, reason in the tooltip).

What the marks mean:

- **OK** — the provider's real probe passed (binary/module/model/endpoint
  present). It appears in the settings dropdowns.
- **MISS** — honest "missing X": the dependency isn't installed, the
  model file isn't there, or the endpoint isn't reachable. Nothing
  downloads anything; nothing crashes. Install what's missing and
  re-check.
- Experimental providers (`ECHO_INCLUDE_EXPERIMENTAL=1`) are hidden from
  dropdowns unless that env var is set — this is deliberate, not a bug.

Expected on a fresh machine: `parakeet`/`kokoro`/`espeak-ng`/`hermes`
OK after `./setup.sh`; GPU tiers MISS until their pip packages + CUDA +
model files exist.

## 2. Per-slot smoke tests

Do these in order — each slot feeds the next.

**Mic → text (STT):** record 5 s and transcribe it:

```bash
cd v2
arecord -q -D default -f S16_LE -c 1 -r 16000 -d 5 -t wav /tmp/smoke.wav
# say "the quick brown fox jumps over the lazy dog" while it records
python3 - <<'EOF'
from pathlib import Path
from echo_node.components.stt import ParakeetSTT
stt = ParakeetSTT({"provider": "parakeet"})
stt.load()
print(stt.transcribe(Path("/tmp/smoke.wav")))
EOF
```

Swap `ParakeetSTT` for `FasterWhisperSTT` / `OnnxAsrSTT` to smoke the
other in-process providers (same `transcribe(path)` surface).

**Text → speaker (TTS):**

```bash
cd v2 && python3 - <<'EOF'
from pathlib import Path
from echo_node.components.tts import KokoroTTS
tts = KokoroTTS({})
tts.synthesize_to_wav("Testing one two three.", Path("/tmp/tts.wav"))
print("wrote /tmp/tts.wav, sr=", tts.sample_rate if hasattr(tts, "sample_rate") else "?")
EOF
aplay -q /tmp/tts.wav
```

Streaming providers (`dots`, `cosyvoice3`, `voxcpn`, any Wyoming TTS)
expose `generate_stream()` — first-audio latency should be ~150–400 ms,
not the whole-utterance time. The speaker uses it automatically when the
provider overrides it (no config change needed).

**Wake word:** `python3 -m echo_node.components.wake` (if it has a CLI;
otherwise check `WakeDetector` via the assistant run below) — clap/speak
the phrase and watch for the detection print.

**VAD:** the barge-in loop prints `[barge-in] playback interrupted` when
it hears sustained speech over playback. The `[timing]` lines (see §6)
confirm the thresholds.

**Full loop:** `./run.sh` (or `python3 v2/assistant_v2.py`), say the wake
phrase, ask something short, interrupt it mid-answer — interruption
should land within ~0.5 s of sustained speech.

## 3. STT A/B: Parakeet vs the alternatives

Record 3–5 clips (16 kHz mono PCM16 WAVs — the harness rejects anything
else with a clear message), then:

```bash
cd v2
python3 tools/stt_ab.py --list
python3 tools/stt_ab.py --a parakeet --b faster-whisper --c onnx-asr \
    --out ab.json --csv ab.csv clips/*.wav
column -t -s, ab.csv | head
```

The report holds transcript + `latency_s` + `error` per (file, provider);
a provider that fails on a file records the error instead of aborting.
Compare word-error informally (ear-check the transcripts) and latency
formally. Experimental STT providers need `ECHO_INCLUDE_EXPERIMENTAL=1`.

## 4. Wyoming round-trips against real servers

Start the reference servers (conventional defaults):

| server | default port | provides |
|---|---|---|
| wyoming-faster-whisper | 10300 | STT |
| wyoming-piper | 10200 | TTS |
| wyoming-openwakeword | 10400 | wake word |

Declare one in `config.yaml` (or the settings External tab):

```yaml
external_providers:
  - slot: tts
    name: wy-piper
    transport: tcp
    host: 127.0.0.1
    port: 10200
```

Then re-run the `validate_all()` snippet from §1 — `tts/wy-piper` should
flip to OK — and select it in the TTS dropdown. Wyoming TTS streams
`audio-chunk` events, so it takes the streaming playback path (§6).
`command:` is forbidden on `transport: tcp` entries (schema error tells
you).

## 5. AEC on/off comparison

```yaml
# config.yaml
audio:
  provider: aec-webrtc   # experimental: ECHO_INCLUDE_EXPERIMENTAL=1
```

needs `pip install pywebrtc-audio`. The orchestrator feeds every played
sentence into the AEC far-end reference automatically (see the `[aec]`
log lines). Test: play loud TTS while silent — with AEC off the mic
meter/VAD should twitch from speaker bleed; with AEC on it should stay
flat. Then speak over playback — barge-in must still trigger. If
interruption stops working with AEC on, that's a real bug: report the
`[timing]` + `[barge-in]` lines.

## 6. External subprocess adapters (whisper.cpp / Piper)

Either edit `config.yaml` (commented examples under
`external_providers:`) or use settings → **External** tab → Add →
repo-adapter quick-pick (`builtin:stt_whispercpp.py` /
`builtin:tts_piper.py`), fill the model/binary args, hit **Test** (runs
the real `validate()` before saving), then Save. Re-run §1: the new
entries appear as `stt/whispercpp (external)` etc. when their binaries
exist. Kill-on-idle is 120 s by default — the child process should be
gone from `ps` two minutes after the last use.

## 7. What "good" looks like — latency targets

Per-turn timings land in two places:

- stdout as `[timing] key=value` lines during the run;
- `logs/session_YYYYMMDD_HHMMSS.jsonl` — one JSON record per turn
  (`TurnRecord`: raw `t_*` wall timestamps plus derived `latency_*`).

Fields that matter (all seconds, monotonic):

| field | meaning | healthy target |
|---|---|---|
| `latency_llm_first_token` | llm_start → first token | < 1.5 s (local) |
| `t_tts_first_chunk − t_tts_start` | first **audio** chunk (streaming) | 0.15–0.5 s |
| `latency_ears_to_mouth` | you stop speaking → playback starts | < 2.5 s |
| barge-in | sustained speech → `[barge-in] playback interrupted` | < 0.5 s |

Notes:

- `t_tts_first_chunk` is the first *audio* chunk when the provider
  streams (`generate_stream`), the finished WAV otherwise — it's the
  honest apples-to-apples metric either way.
- Streaming engages only when the provider overrides `generate_stream`
  **and** no avatar lip-sync is active (Rhubarb needs the full utterance;
  avatar users keep the blocking path deliberately).
- If a streaming provider's generator dies before the first chunk, the
  speaker retries the sentence through the blocking path; if it dies
  mid-stream, the partial audio stands and the rest of the reply goes
  blocking. Both print a `[tts]` line — silence there means streaming
  worked.

## 8. Reporting back

For anything that misbehaves, capture:

1. the `validate_all()` line for the provider,
2. the `[timing]` / `[tts]` / `[barge-in]` / `[aec]` stdout lines,
3. the turn's JSON record from `logs/session_*.jsonl`,
4. `config.yaml` (redact keys) + which dropdown selections were active.
