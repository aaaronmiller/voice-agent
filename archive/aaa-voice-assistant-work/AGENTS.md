# AGENTS.md

## Project Overview

Windows Voice Assistant - A cross-platform voice application built with Tauri (Rust backend) and React + TypeScript + shadcn/ui frontend. Provides push-to-talk speech-to-text and wake word conversational AI capabilities.

---

## Build Commands

### Frontend (React/TypeScript)
```bash
npm run dev          # Start Vite dev server
npm run build        # TypeScript compile + Vite build
npm run typecheck    # TypeScript type checking only
npm run lint         # ESLint (when configured)
```

### Backend (Rust/Tauri)
```bash
cd src-tauri && cargo build          # Debug build
cd src-tauri && cargo build --release # Release build
cd src-tauri && cargo test           # Run all Rust tests
cd src-tauri && cargo test <test_name> # Run single test
cd src-tauri && cargo clippy         # Rust linter
cd src-tauri && cargo fmt            # Format Rust code
```

### Tauri (Combined)
```bash
npm run tauri:dev    # Development with hot reload
npm run tauri:build  # Production build
```

---

## Code Style Guidelines

### Rust Backend

**Imports:** Group by external crates, then internal modules. Alphabetize within groups.
```rust
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::config::Settings;
```

**Error Handling:** Use `thiserror` for custom error types. Provide descriptive error messages.
```rust
#[derive(Error, Debug)]
pub enum AudioError {
    #[error("Failed to access device: {0}")]
    DeviceError(String),
    #[error("Recording failed: {0}")]
    RecordError(#[from] std::io::Error),
}
```

**Naming Conventions:**
- Structs/Enums: `PascalCase` (e.g., `AudioManager`, `HotkeyId`)
- Functions/Methods: `snake_case` (e.g., `start_recording`, `list_input_devices`)
- Constants: `SCREAMING_SNAKE_CASE`
- Module names: `snake_case` (files match: `audio.rs`, `hotkey.rs`)

**Struct Organization:** Fields before impl blocks. Public methods before private.
```rust
pub struct AudioManager {
    input_device: Option<AudioDevice>,
    is_recording: bool,
}

impl AudioManager {
    pub fn new() -> Result<Self, AudioError> { ... }
    pub fn start_recording(&mut self) -> Result<(), AudioError> { ... }
}
```

### TypeScript Frontend

**Imports:** React first, external libraries, internal aliases, then relative imports.
```typescript
import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { useSettingsStore } from '@/stores/settings'
import { cn } from '@/lib/utils'
```

**Naming Conventions:**
- Components: `PascalCase` (e.g., `SettingsPanel`, `EQVisualizer`)
- Functions/hooks: `camelCase` (e.g., `useAudioLevels`, `formatTimestamp`)
- Files: `kebab-case.tsx` for components (e.g., `settings-panel.tsx`)
- Stores: `*.store.ts` (e.g., `settings.store.ts`)

**Component Structure:**
```typescript
interface ComponentProps {
  title: string
  onAction?: () => void
}

export function Component({ title, onAction }: ComponentProps) {
  // hooks at top
  const [state, setState] = useState(false)
  
  // derived values
  const displayText = useMemo(() => title.toUpperCase(), [title])
  
  // effects
  useEffect(() => { ... }, [])
  
  // handlers
  const handleClick = () => { ... }
  
  // render
  return ( ... )
}
```

**Styling:** Use Tailwind with cn() utility for conditional classes.
```typescript
<div className={cn(
  "base-classes",
  isActive && "active-classes",
  className
)}>
```

---

## Project Structure

```
src/
├── components/      # React components
│   └── ui/          # shadcn/ui primitives
├── hooks/           # Custom React hooks
├── stores/          # Zustand state stores
├── types/           # TypeScript type definitions
├── lib/             # Utility functions (utils.ts)
└── main.tsx         # App entry point

src-tauri/src/
├── main.rs          # Tauri app entry
├── lib.rs           # Library exports
├── audio.rs         # Audio capture/playback
├── clipboard.rs     # Clipboard management
├── config.rs        # Configuration store
├── hotkey.rs        # Global hotkey handling
├── hardware.rs      # GPU detection
└── bin/             # Standalone binaries
```

---

## Testing

### Rust Tests
```bash
cd src-tauri
cargo test                           # All tests
cargo test test_name                 # Single test
cargo test -- --nocapture            # Show stdout
cargo test --lib                     # Unit tests only
```

Property-based testing uses `proptest`. Add to Cargo.toml dev-dependencies:
```toml
[dev-dependencies]
proptest = "1.4"
```

### TypeScript Tests
```bash
npm test                 # Run all tests (when configured)
npm run test:watch       # Watch mode
```

Property-based testing uses `fast-check` (already in devDependencies).

---

## Key Patterns

### Tauri IPC Commands
Define in Rust with `#[tauri::command]`:
```rust
#[tauri::command]
fn get_settings(state: State<AppState>) -> Result<Settings, String> {
    state.config.get().map_err(|e| e.to_string())
}
```

Invoke from TypeScript:
```typescript
import { invoke } from '@tauri-apps/api/core'
const settings = await invoke<Settings>('get_settings')
```

### State Management
Use Zustand stores in `src/stores/`:
```typescript
interface SettingsStore {
  theme: 'light' | 'dark' | 'system'
  setTheme: (theme: string) => void
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  theme: 'system',
  setTheme: (theme) => set({ theme }),
}))
```

### Error Handling Pattern
Return `Result<T, E>` in Rust, throw typed errors in TypeScript:
```typescript
// TypeScript
class AppError extends Error {
  constructor(public code: string, message: string) {
    super(message)
  }
}

try {
  await invoke('risky_operation')
} catch (e) {
  throw new AppError('OPERATION_FAILED', String(e))
}
```

---

## Pre-commit Checklist

- [ ] `npm run typecheck` passes
- [ ] `cd src-tauri && cargo clippy -- -D warnings` passes
- [ ] `cd src-tauri && cargo fmt -- --check` passes
- [ ] No console.log() in production code
- [ ] No unwraps in Rust production code (use proper error handling)

---

## Platform Notes

- **OS:** Windows 11 target, Linux development
- **Audio:** Uses `cpal` for cross-platform audio (currently disabled in Cargo.toml)
- **GPU:** Intel Arc A370M with SYCL backend detection
- **Config Location:** `%APPDATA%/voice-assistant/config.json` on Windows
