# Textual TUI application

**Phase:** 3b — TUI Frontend | **Status:** Pending | **Owner:** Frontend team

## Entry criteria

- [x] Gateway is running (Phase 2 complete)
- [x] WebSocket protocol finalized (Phase 1)
- [x] Python 3.11+ available (Textual runs on Python)

## Implementation

### File structure

```
tui/
├── requirements.txt
├── echo_tui/
│   ├── __init__.py
│   ├── __main__.py          # Entry point: python -m echo_tui
│   ├── app.py               # Textual App class
│   ├── screens/
│   │   ├── main.py          # Main conversation screen
│   │   ├── settings.py      # Settings screen
│   │   └── latency.py       # Latency dashboard screen
│   ├── widgets/
│   │   ├── Transcript.py    # Scrollable transcript
│   │   ├── LatencyPanel.py  # Live latency metrics
│   │   ├── StatusBar.py     # State indicator
│   │   ├── ProviderSelect.py # Provider combo box
│   │   └── Waveform.py      # ASCII waveform (optional)
│   ├── gateway_client.py    # WebSocket client for gateway
│   ├── audio.py             # Local audio capture/playback
│   └── metrics.py           # Latency aggregation display
```

### Gateway client (`gateway_client.py`)

Uses `websockets` library to connect to the gateway:

```python
class GatewayClient:
    def __init__(self, url: str = "ws://127.0.0.1:3000/ws"):
        self.url = url
        self.ws: websockets.WebSocketClientProtocol | None = None
        
    async def connect(self):
        self.ws = await websockets.connect(self.url)
        
    async def send_audio(self, data: bytes):
        await self.ws.send(data, binary=True)
        
    async def set_provider(self, name: str):
        await self.ws.send(json.dumps({"type": "set_provider", "provider": name}))
        
    async def receive(self) -> ServerMessage:
        msg = await self.ws.recv()
        if isinstance(msg, bytes):
            return {"type": "audio_data", "data": msg}
        return json.loads(msg)
```

### Main screen layout

```
┌──────────────────────────────────────────────────┐
│ Echo-Node                              [● idle]  │
├───────────────────────────────────┬──────────────┤
│                                   │  Latency     │
│  Transcript                        │  ├ ears→mouth │
│                                   │  │   342ms    │
│  [You] what's the weather like?   │  ├ first tok  │
│                                   │  │   180ms    │
│  [Sam] let me check...            │  ├ total      │
│                                   │  │   1.2s     │
│  > It's 72° and sunny in...      │  └──────────────┤
│                                   │               │
│                                   │  Provider      │
│                                   │  [Gemini Live▼]│
│                                   │               │
│  [You] thank you                  │  [Push to     │
│  [Sam] you're welcome!            │   Talk (Space)]│
├───────────────────────────────────┴──────────────┤
│ [Space] PTT  [P] Settings  [L] Latency  [Q] Quit│
└──────────────────────────────────────────────────┘
```

### Key bindings

| Key | Action |
|---|---|
| `Space` (hold) | Push to talk |
| `Escape` | Interrupt / stop |
| `p` / `P` | Toggle settings panel |
| `l` / `L` | Toggle latency dashboard |
| `t` | Cycle transcript view |
| `q` / `Ctrl+C` | Quit |
| `Tab` | Focus navigation |

### Latency dashboard screen

A separate full-screen view showing:
- Live per-turn latency bar chart
- Rolling average line
- Per-provider comparison (if multiple providers used in session)
- Percentile distribution (p50, p95, p99)
- Turn count and time-series sparkline
- Interrupt frequency

## Exit criteria

- [ ] `python -m echo_tui` starts the TUI
- [ ] Connects to gateway WebSocket
- [ ] Push-to-talk captures and sends audio
- [ ] Assistant audio plays back
- [ ] Transcript scrolls with new messages
- [ ] Provider selector works
- [ ] Latency panel updates every turn
- [ ] Settings screen allows config changes
- [ ] All key bindings work
- [ ] Works in GNOME terminal and kitty
