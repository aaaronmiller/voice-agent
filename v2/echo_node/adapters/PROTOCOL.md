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
