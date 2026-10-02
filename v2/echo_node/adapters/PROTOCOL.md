# Echo-Node adapter protocol (Phase B)

JSON-RPC 2.0 over stdio. One JSON object per line; the host writes
requests to the child's stdin, the child writes responses to stdout.
The child must never write anything else to stdout (log to stderr —
the host forwards it to the app log at debug level).

Both sides import the framing helpers from
`echo_node/adapters/protocol.py`. The host side is
`echo_node/adapters/subprocess_adapter.py`.

## Trust model

**The config file is the trust boundary.** External providers are
declared in `config.yaml` under `external_providers:` — never typed
into the settings UI. A config entry is an explicit argv list:

```yaml
external_providers:
  - slot: stt
    name: whispercpp
    command: ["builtin:stt_whispercpp.py"]
    args: ["--model", "/models/ggml-base.bin"]
```

- `builtin:<file>` resolves to a repo-shipped adapter in
  `echo_node/adapters/`, run under `sys.executable`. The allowlist is
  exact (`BUILTIN_ADAPTERS`): no `..`, no separators, no absolute
  paths, no names outside the set. Anything else in `command` must be
  an explicit argv list from the config file — the host never
  synthesizes paths and never accepts executable paths from the UI.
- A malformed config entry is a **startup-fatal** `ExternalProviderError`
  with a plain message (bad slot, name collision with a built-in,
  traversal attempt, unsupported `protocol_version`).
- `validate()` never raises and never downloads: it reports missing
  binaries/models honestly (`ok: false` + reason) so the settings
  dropdowns simply don't list what isn't there.

## Handshake

First request the host sends, before any work:

```
→ {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
← {"jsonrpc": "2.0", "id": 0, "result": {
      "protocol_version": 1,
      "slot": "stt",            # the slot this adapter serves
      "name": "whispercpp",
      "capabilities": {         # plain dict; see below
        "name": "whisper.cpp", "version": "unknown",
        "languages": [], "streaming": false,
        "license": "MIT", "network": false,
        "notes": "..."
      }}}
```

The host speaks `PROTOCOL_VERSION = 1` and rejects any other version.
The child side should build the capabilities dict literally — it must
not need the `echo_node` package (`protocol.py` has no `echo_node`
import at module top for exactly this reason).

## Methods by slot

Every method takes a params object and returns a result object.
`system`/`phrase`/`score` fields are optional where noted.

| slot           | method        | params                                   | result                              |
|----------------|---------------|------------------------------------------|-------------------------------------|
| stt            | `transcribe`  | `{pcm_b64, sample_rate}`                 | `{text}`                            |
| tts            | `synthesize`  | `{text}`                                 | `{pcm_b64, sample_rate}`             |
| vad            | `is_speech`   | `{pcm_b64, sample_rate}`                 | `{speech, score?}`                  |
| wake_word      | `detect`      | `{pcm_b64, sample_rate}`                 | `{detected, phrase?, score?}`        |
| agent_backend  | `chat`        | `{text, system?}`                        | `{text}`                            |
| all            | `validate`    | `{}`                                     | `{ok, reason, details?}`             |
| all            | `ping`        | `{}`                                     | `{ok}`                              |
| all            | `shutdown`    | `{}`                                     | `{ok}`                              |

Notes:

- **PCM is always 16-bit mono int16, base64-encoded.** The host
  normalizes mic audio to 16 kHz before sending; TTS children report
  their own `sample_rate` (the host writes whatever rate it gets).
- `validate` is the child's **self-probe**: check the binary/model is
  usable with a micro-fixture (a second of silence, a short sentence).
  Never download anything. Return `ok: false` with a human-readable
  `reason` when the adapter can't do its job — the host surfaces that
  string in the settings UI via `validate_all()`.
- Unknown methods get JSON-RPC `-32601`; a handler exception becomes
  `-32603` (the child loop never dies on a bad request); a domain
  error raised as `AdapterError(code, message)` keeps its code.
- `shutdown` is answered, then the child exits 0.

## Host behavior (what adapter authors can rely on)

- **Framing:** one JSON object per line, `jsonrpc: "2.0"`, matching `id`.
- **Timeouts:** every call has a deadline (`request_timeout_s`,
  default 30). On timeout the host raises `AdapterTimeout` to the
  caller; the child should still answer eventually (the response is
  discarded) or exit.
- **Crashes:** if the child dies mid-call, the host restarts it once
  and retries the call transparently. After `max_restarts` (default 3)
  unexpected deaths, calls fail with `AdapterCrashed` naming the
  limit. The restart budget is per handle (i.e. per provider instance).
- **Idle reaping:** after `idle_timeout_s` (default 120) with no calls,
  the host kills the child. The next call spawns a fresh one — this
  does not consume restart budget. Batch-oriented Phase B usage means
  adapters should expect to be spawned often and start fast.
- **Malformed child stdout** (non-JSON lines) is logged and ignored —
  it never hangs the stream or poisons a pending call. Malformed
  *responses* (bad `id`/shape) fail that call with `ProtocolError`.
- **Child stderr** is drained on a background thread into the app log
  (debug level) so a chatty child can't block on a full pipe.

## Writing an adapter

`protocol.run_adapter(handler)` runs the loop; the handler exposes
`rpc_<method>(params)` methods. Minimal example:

```python
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocol as P

class MySTT:
    def rpc_initialize(self, params):
        return {"protocol_version": P.PROTOCOL_VERSION, "slot": "stt",
                "name": "mystt", "capabilities": {"name": "mystt", ...}}
    def rpc_validate(self, params):
        return {"ok": True, "reason": "...", "details": {}}
    def rpc_ping(self, params):
        return {"ok": True}
    def rpc_transcribe(self, params):
        pcm = P.b64_to_pcm16(params["pcm_b64"])  # int16 numpy, 16 kHz mono
        ...
        return {"text": "..."}
    def rpc_shutdown(self, params):
        return {"ok": True}

if __name__ == "__main__":
    raise SystemExit(P.run_adapter(MySTT()))
```

The three shipped adapters (`stt_whispercpp.py`, `tts_piper.py`,
`stt_reference.py`) are the reference implementations. The test fake
(`echo_node/tests/testdata/fake_adapter.py`, modes `echo` / `hang` /
`crash-once` / `crash-always` / `garbage`) exercises every host-side
guarantee above — see `echo_node/tests/test_phase_b.py`.

## Batch-only in Phase B

The protocol has no streaming methods yet (no `transcribe_stream` /
`synthesize_stream`). The host sends whole utterances and writes whole
wavs. Streaming is Phase D work, alongside the Wyoming TCP adapters.

---

# Wyoming TCP transport (Phase D)

Any Wyoming-protocol server (wyoming-faster-whisper, wyoming-piper,
wyoming-openwakeword, …) can take the `stt`, `tts`, or `wake_word`
slot over TCP — no subprocess, no JSON-RPC. Implementation:
`echo_node/adapters/wyoming.py` (`WyomingAdapter` base + `WyomingSTT` /
`WyomingTTS` / `WyomingWakeWord`, built by `make_wyoming_provider`).

## Trust model

The trust boundary is unchanged: the config file. A `transport: tcp`
entry names a `host` (default `127.0.0.1`) and a `port` (required);
`command`/`args` are **startup-fatal** for tcp entries — the adapter
only opens a TCP connection, it never spawns anything, so there is no
executable-path surface at all. `validate()` is a TCP connect probe
(3 s); refused/timed out → honest missing-result, never an exception,
so the provider simply stays out of the settings dropdowns until its
server is running. Registered with `external=True`, marked
" (external)" like subprocess providers.

## Framing (verified against upstream)

Event names and framing were verified against the upstream wyoming
source (rhasspy/wyoming, now OHF-Voice/wyoming, main, 2026-10-01:
`event.py`, `asr.py`, `tts.py`, `wake.py`, `audio.py`). The `wyoming`
PyPI package is deliberately not used — the client is stdlib-only
(sockets + json + numpy), so there is no new dependency to install.

One event on the wire is:

```
{"type": <str>, "version": <str>, "data_length": N, "payload_length": M}\n
<data_length bytes of JSON>        # the event's "data" dict
<payload_length bytes of raw data> # e.g. PCM for audio-chunk
```

`payload_length` is omitted when there is no payload. We send
`version: "echo-node"` (servers ignore it). The reader is
deadline-bounded and never over-reads: a fresh buffered reader is
created per event, so reading even one byte past the declared lengths
would swallow the next event's header.

## Event flows

| slot      | client sends                                              | server answers                              |
|-----------|-----------------------------------------------------------|---------------------------------------------|
| stt       | `transcribe` (`name`?, `language`?) then `audio-start` / `audio-chunk`+ / `audio-stop` (16 kHz mono PCM16) | `transcript` (`text`) — streaming servers may also emit `transcript-chunk` (each chunk *replaces* the previous); a bare `transcript-stop` falls back to the last chunk |
| tts       | `synthesize` (`text`, `voice` = `{name, speaker?}` or `{language}`) | `audio-start` (rate/width/channels) / `audio-chunk`+ (PCM payload) / `audio-stop`; concatenated and written as WAV at the server's rate. Only 16-bit mono server output is supported |
| wake_word | `detect` (`names`?) then `audio-start` / `audio-chunk`+ / `audio-stop` | `detection` (`name`?) → `(True, name, 1.0)`; `not-detected` → `(False, "", 0.0)`. Upstream `Detection` carries **no confidence score** — 1.0/0.0 are presence flags, not calibrated confidences |

An `error` event from the server raises `WyomingProtocolError` with
the server's text. Connections are per-request (connect → send → read
→ close); there is no reconnect state machine.

## Config schema (tcp entries)

```yaml
external_providers:
  - slot: stt
    name: wy-faster-whisper
    transport: tcp          # default is `subprocess`
    host: 127.0.0.1        # default
    port: 10300            # required. Conventional Wyoming defaults
                           # (confirm against your server): faster-whisper
                           # 10300, piper 10200, openwakeword 10400
    model: tiny-int8        # optional → transcribe `name`
    language: en            # optional → transcribe `language` / tts voice language
    voice_name: en_US-amy-medium  # optional → synthesize `voice.name`
    voice_speaker: spk1     # optional, rides along with voice_name
    phrase_names: ["hey_jarvis"]   # optional → detect `names`
    connect_timeout_s: 3.0
    request_timeout_s: 30.0
    chunk_samples: 1024
```

Not served over Wyoming TCP: the VAD slot (the protocol's
`voice-started`/`voice-stopped` events are not a per-chunk query),
`agent_backend`, and everything the subprocess transport doesn't
cover either. Schema violations (`transport: bogus`, tcp + `command`,
missing/bad `port`, unsupported slot) fail startup with
`ExternalProviderError`.

## Honest gaps

- No real Wyoming server exists on the build VM; round-trips are
  verified against fake TCP servers in `echo_node/tests/test_phase_d.py`
  only. Run against the real servers before trusting this in production.
- The conventional ports are the projects' documented defaults, not
  re-verified against live servers in this session.
- The `error`-event shape follows wyoming convention (type `error`,
  data `text`/`code`) but was not re-verified against a live server.
