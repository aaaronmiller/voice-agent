# Echo-Node Frontend

Svelte 5 frontend for the Echo-Node voice AI interface.

## Architecture

```
src/
├── routes/
│   ├── +layout.svelte    # Root layout (SSR disabled)
│   └── +page.svelte      # Main page with all components
├── lib/
│   ├── components/
│   │   ├── avatar-display.svelte   # TalkingHead VRM avatar
│   │   ├── waveform.svelte         # Audio visualizer
│   │   ├── transcript.svelte       # Conversation history
│   │   ├── status-indicator.svelte # Pipeline state display
│   │   └── frame.svelte            # Theme wrapper
│   ├── stores/
│   │   ├── websocket.svelte.ts     # WebSocket connection store
│   │   └── pipeline-state.svelte.ts # State machine store
│   ├── utils/
│   │   └── audio.ts                # Audio utilities
│   └── index.ts                    # Public exports
└── app.css                         # Global styles
```

## Components

### AvatarDisplay
TalkingHead VRM avatar wrapper with:
- Automatic model loading from configured URL
- Lip-sync from audio amplitude
- Idle animations (blinking, gaze, subtle movements)
- Model switching support

### Waveform
Audio waveform visualizer:
- Animated bars during LISTENING state
- Smooth interpolation for natural movement
- Configurable bar count, height, and color

### Transcript
Conversation history display:
- Scrollable message list
- User/assistant message differentiation
- Partial transcript (streaming STT) display
- Auto-scroll to latest message
- Timestamp display (optional)

### StatusIndicator
Pipeline state indicator:
- 5-state display (DORMANT, TRIGGERED, LISTENING, PROCESSING, SPEAKING)
- Color-coded with pulse animations
- Compact and normal display modes

### Frame
Theme wrapper component:
- 5 theme presets (minimal, cyberpunk, retro-terminal, glassmorphism, none)
- CSS custom properties for theming
- Animated accent border

## Stores

### websocketStore
WebSocket connection management:
- Auto-reconnection with exponential backoff
- Event subscription system
- Message type routing
- Connection status tracking

```typescript
import { useWebSocket } from '$lib/stores/websocket';

const ws = useWebSocket();
ws.connect();
ws.send({ type: 'keyboard_trigger' });
ws.on('state_change', (data) => console.log(data));
```

### pipelineStateStore
State machine and conversation tracking:
- Current pipeline state
- Transcript history
- Partial transcript (streaming)
- LLM response accumulation
- VRAM usage reporting

```typescript
import { usePipelineState } from '$lib/stores/pipeline-state';

const pipeline = usePipelineState();
console.log(pipeline.state); // 'listening'
console.log(pipeline.isListening); // true
```

## WebSocket Protocol

Events received from gateway:

| Event | Payload | Description |
|-------|---------|-------------|
| `state_change` | `{ from, to, timestamp }` | Pipeline state transition |
| `transcript_partial` | `{ text }` | Streaming STT update |
| `transcript_final` | `{ text }` | Final STT result |
| `llm_token` | `{ token }` | Streaming LLM response |
| `llm_complete` | `{ text }` | LLM response complete |
| `tts_audio` | `{ data, sample_rate }` | TTS audio chunk (ArrayBuffer) |
| `tts_complete` | - | TTS playback complete |
| `error` | `{ message, code }` | Error notification |
| `vram_report` | `{ total_mb, used_mb, available_mb }` | VRAM usage stats |

Events sent to gateway:

| Event | Payload | Description |
|-------|---------|-------------|
| `keyboard_trigger` | - | Manual activation (spacebar) |
| `barge_in` | - | Interrupt speaking state |
| `stop` | - | Halt pipeline |
| `config_update` | `{ config }` | Update configuration |

## Development

```bash
# Install dependencies
pnpm install

# Start dev server
pnpm dev

# Build for production
pnpm build

# Preview production build
pnpm preview

# Run tests
pnpm test

# Lint and format
pnpm lint
pnpm format
```

## Theming

Themes are applied via the `Frame` component using CSS custom properties:

```svelte
<Frame theme="cyberpunk">
  <!-- Your content -->
</Frame>
```

Available themes:
- `minimal` - Clean, subtle borders
- `cyberpunk` - Neon cyan/pink, sharp corners
- `retro-terminal` - Green phosphor aesthetic
- `glassmorphism` - Frosted glass effect
- `none` - No frame styling

## Accessibility

- Semantic HTML throughout
- ARIA labels on interactive elements
- Keyboard navigation support (spacebar trigger)
- Reduced motion support via `prefers-reduced-motion`
- Focus indicators for keyboard users

## Dependencies

- **Svelte 5** - UI framework with runes reactivity
- **SvelteKit** - Application framework
- **Three.js** - 3D rendering
- **@pixiv/three-vrm** - VRM model loader
- **talkinghead** - Avatar animation library
