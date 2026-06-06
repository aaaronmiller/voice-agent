# REST API: Gateway

**Version**: 1.0.0
**Base URL**: `http://localhost:3000/api`

---

## Endpoints

### GET /api/health

Health check endpoint.

**Response**:
```json
{
  "status": "ok",
  "worker_connected": true,
  "pipeline_state": "dormant",
  "uptime_seconds": 1234
}
```

**Status Codes**:
- `200 OK`: System healthy
- `503 Service Unavailable`: Worker disconnected

---

### GET /api/config

Get current configuration.

**Response**:
```json
{
  "echo_node": { "name": "Gimp", "version": "1.0.0" },
  "stt": { "provider": "sherpa-onnx", "model": "..." },
  "tts": { "provider": "kokoro", "voice": "af_heart" },
  "llm": { "provider": "ollama", "model": "llama3.2:7b" },
  "personality": { "active": "hacker" },
  // ... full config object
}
```

---

### PUT /api/config

Update configuration (partial or full).

**Request**:
```json
{
  "personality": { "active": "butler" },
  "tts": { "provider": "chatterbox" }
}
```

**Response**:
```json
{
  "success": true,
  "restarted_components": ["tts"],
  "message": "Configuration updated. TTS provider reloaded."
}
```

**Status Codes**:
- `200 OK`: Update applied
- `400 Bad Request`: Invalid config schema
- `500 Internal Server Error`: Provider reload failed

---

### GET /api/status

Get current pipeline status.

**Response**:
```json
{
  "state": "dormant",
  "session_active": false,
  "current_personality": "hacker",
  "conversation_turns": 5,
  "vram": {
    "total_mb": 6144,
    "used_mb": 4096,
    "available_mb": 2048
  }
}
```

---

### POST /api/trigger

Manually trigger listening (keyboard hotkey equivalent).

**Request**: Empty body or `{}`

**Response**:
```json
{
  "success": true,
  "message": "Triggered listening"
}
```

**Status Codes**:
- `200 OK`: Triggered successfully
- `409 Conflict`: Pipeline not in DORMANT state

---

### POST /api/stop

Stop current pipeline execution.

**Request**: Empty body or `{}`

**Response**:
```json
{
  "success": true,
  "message": "Pipeline stopped"
}
```

---

### GET /api/personalities

List available personality presets.

**Response**:
```json
{
  "built_in": [
    { "name": "hacker", "description": "Tech-savvy, concise" },
    { "name": "seductive", "description": "Flirtatious, playful" },
    { "name": "butler", "description": "Formal, polite" },
    { "name": "drill-sergeant", "description": "Aggressive, motivational" },
    { "name": "stoner-philosopher", "description": "Laid-back, deep thoughts" }
  ],
  "custom": [
    { "name": "my-custom", "description": "User-defined" }
  ]
}
```

---

### GET /api/avatars

List available VRM avatars.

**Response**:
```json
{
  "bundled": [
    { "model": "avatar-01-casual.vrm", "display_name": "Casual" },
    { "model": "avatar-02-punk.vrm", "display_name": "Punk" },
    // ... more
  ],
  "custom": [
    { "model": "my-avatar.vrm", "display_name": "My Avatar" }
  ]
}
```

---

## Error Response Format

```json
{
  "error": {
    "code": "PROVIDER_NOT_FOUND",
    "message": "Unknown stt provider: vibevoice-tts. Available: sherpa-onnx, faster-whisper, vibevoice-asr",
    "suggestion": "Did you mean 'vibevoice-asr'? VibeVoice-TTS is not available (code removed Sept 2025)."
  }
}
```

---

## Rate Limiting

**MVP**: No rate limiting (localhost only)

**Post-v1**: When LAN access enabled:
- 100 requests/minute per IP
- 429 Too Many Requests if exceeded

---

## Authentication

**MVP**: No authentication (localhost trust boundary)

**Post-v1**: When LAN access enabled:
- API key in `X-API-Key` header
- Configurable allowed IP ranges
