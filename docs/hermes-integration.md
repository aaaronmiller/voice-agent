# Hermes Integration

Echo-Node v2 can use Hermes Agent as its conversation backend through Hermes'
OpenAI-compatible API server.

## Grounding

- Local Hermes source:
  `/home/misscheta/.hermes/hermes-agent/gateway/platforms/api_server.py`
  documents `POST /v1/chat/completions`, `GET /v1/models`, and `GET /health`.
- Hermes web docs found on 2026-06-06 describe the same API-server shape:
  `http://localhost:8642/v1`.

## Configure Hermes

Hermes needs the API server platform enabled. The equivalent config is:

```yaml
platforms:
  api_server:
    enabled: true
    extra:
      host: "127.0.0.1"
      port: 8642
      key: "sk-local-hermes"
```

If Hermes is configured through environment variables, use the matching
`API_SERVER_ENABLED`, `API_SERVER_HOST`, `API_SERVER_PORT`, and `API_SERVER_KEY`
values.

Start or restart the Hermes gateway after changing its config.

## Configure Echo-Node

From WSL/bash:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
HERMES_API_KEY=sk-local-hermes ./integrate-hermes
```

This edits only `v2/config.yaml`:

```yaml
llm:
  provider: hermes
  base_url: http://127.0.0.1:8642/v1
  api_key: sk-local-hermes
  model: hermes-agent
```

Then run:

```bash
./run.sh
```

## Verify

```bash
curl -s http://127.0.0.1:8642/health
```

For a chat probe:

```bash
curl -s http://127.0.0.1:8642/v1/chat/completions \
  -H "Authorization: Bearer sk-local-hermes" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"ping"}],"stream":false}'
```

## Notes

- Keep the Hermes API server bound to `127.0.0.1` unless you intentionally need
  LAN access.
- Echo-Node supplies wake word, Parakeet STT, Kokoro TTS, silence detection, and
  barge-in. Hermes supplies the agent reasoning and tools.
- If Hermes has no API key configured, leave `HERMES_API_KEY` empty and rerun
  `./integrate-hermes`.
