# Odysseus Integration

Echo-Node v2 can use Odysseus as its conversation backend through Odysseus'
token-authenticated sync chat endpoint.

## Grounding

- Local Odysseus source:
  `/home/misscheta/odysseus/routes/webhook_routes.py` defines
  `POST /api/v1/chat`.
- The local route requires a Bearer API token with `chat` scope.
- The Odysseus README says the app binds to `127.0.0.1:7000` by default and
  supports Ollama, llama.cpp, vLLM, OpenRouter, OpenAI, MCP, memory, and skills.

## Configure Odysseus

Start Odysseus:

```bash
cd /home/misscheta/odysseus
./odysseus-launch.sh
```

Or use its documented native command:

```bash
cd /home/misscheta/odysseus
source venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

In Odysseus, create an API token with `chat` scope.

## Configure Echo-Node

From WSL/bash:

```bash
cd /home/misscheta/Downloads/voice-agent/v2
ODYSSEUS_API_TOKEN=ody_your_real_token ./integrate-odysseus
```

Optional model override:

```bash
ODYSSEUS_API_TOKEN=ody_your_real_token \
ODYSSEUS_MODEL=qwen3:4b \
./integrate-odysseus
```

This edits only `v2/config.yaml`:

```yaml
llm:
  provider: odysseus
  base_url: http://127.0.0.1:7000
  api_key: ody_your_real_token
  model: ""
```

Then run:

```bash
./run.sh
```

## Verify

```bash
curl -s http://127.0.0.1:7000/api/v1/chat \
  -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"ping"}'
```

## Important Misconfiguration To Avoid

Odysseus `.env` uses `LLM_HOST` as a host name or host list input for discovery.
Do not set it to a full `/v1/chat/completions` URL. Use app settings or endpoint
fields for full API URLs, and keep `LLM_HOST` as a host such as `localhost`.

## Notes

- Echo-Node supplies hands-free voice, wake word, Parakeet STT, Kokoro TTS,
  silence detection, and barge-in.
- Odysseus supplies workspace chat, memory, tools, and model routing.
- Odysseus outbound webhooks intentionally reject private/internal URLs; that is
  why this integration uses Echo-Node calling Odysseus, not Odysseus calling a
  loopback Echo-Node webhook.
