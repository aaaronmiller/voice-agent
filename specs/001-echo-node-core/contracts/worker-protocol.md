# WebSocket Protocol: Gateway ↔ Worker

**Version**: 1.0.0
**Transport**: WebSocket (binary audio + JSON control messages)

---

## Worker → Gateway Events (JSON)

### state_change

Emitted when pipeline state transitions.

```typescript
{
  type: "state_change";
  from: "dormant" | "triggered" | "listening" | "processing" | "speaking";
  to: "dormant" | "triggered" | "listening" | "processing" | "speaking";
  timestamp: number;  // Unix epoch ms
}
```

### transcript_partial

Partial STT result as user speaks.

```typescript
{
  type: "transcript_partial";
  text: string;  // May change as user continues speaking
}
```

### transcript_final

Final STT result after VAD silence detection.

```typescript
{
  type: "transcript_final";
  text: string;  // Final, will not change
}
```

### llm_token

Streaming LLM response token.

```typescript
{
  type: "llm_token";
  token: string;
}
```

### llm_complete

LLM response finished.

```typescript
{
  type: "llm_complete";
  text: string;  // Full accumulated response
}
```

### tts_audio

TTS audio chunk (binary frame + metadata).

```typescript
{
  type: "tts_audio";
  data: ArrayBuffer;  // Binary frame: 16kHz mono float32 PCM
  sample_rate: number;  // e.g., 24000
}
```

### tts_complete

TTS playback finished.

```typescript
{
  type: "tts_complete";
}
```

### vram_report

VRAM usage report at startup.

```typescript
{
  type: "vram_report";
  total_mb: number;
  used_mb: number;
  available_mb: number;
}
```

### error

Error condition.

```typescript
{
  type: "error";
  message: string;
  code: string;  // e.g., "VRAM_EXCEEDED", "PROVIDER_NOT_FOUND"
}
```

---

## Gateway → Worker Commands (JSON)

### keyboard_trigger

Manual activation (bypass wake word).

```typescript
{
  type: "keyboard_trigger";
}
```

### barge_in

Interrupt speaking state (user spoke during TTS playback).

```typescript
{
  type: "barge_in";
}
```

### config_update

Runtime configuration change.

```typescript
{
  type: "config_update";
  config: {
    personality?: string;
    stt?: { provider?: string; threshold?: number };
    tts?: { provider?: string; voice?: string };
    // ... other partial updates
  };
}
```

### stop

Halt pipeline immediately.

```typescript
{
  type: "stop";
}
```

---

## Binary Audio Format

**Direction**: Gateway → Worker (client microphone capture)

| Property | Value |
|----------|-------|
| Sample Rate | 16000 Hz |
| Channels | 1 (mono) |
| Format | float32 (IEEE 754) |
| Endianness | Little-endian |
| Frame Size | 512 samples (32ms) |

**WebSocket Frame**: Binary message type (not JSON)

---

## Connection Lifecycle

```
1. Gateway connects to ws://localhost:9001
2. Worker accepts connection
3. Gateway sends config_update with initial config
4. Worker emits vram_report after model load
5. Worker emits state_change (DORMANT → ready)
6. Event streaming begins
```

---

## Error Handling

| Error Code | Trigger | Recovery |
|------------|---------|----------|
| `VRAM_EXCEEDED` | Model load fails | Suggest smaller models, CPU fallback |
| `PROVIDER_NOT_FOUND` | Invalid provider in config | List available providers |
| `AUDIO_DEVICE_UNAVAILABLE` | Mic access fails | Exit with error message |
| `LLM_UNREACHABLE` | LLM endpoint timeout | Announce error, return to DORMANT |
| `INVALID_STATE_TRANSITION` | Buggy command sequence | Log warning, ignore command |
