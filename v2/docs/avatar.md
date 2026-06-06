# Avatar

Echo-Node v2 ships an optional animated avatar that floats in the bottom-right
corner of the primary screen and lip-syncs to whatever the TTS is saying. It's
a separate PyQt6 process driven by viseme timing from
[Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync).

The assistant works without it; it's purely decorative.

## Requirements

| Component | Where it lives |
|---|---|
| PyQt6 + Pillow | `v2/.venv` (installed by `setup.sh`; on existing envs run `pip install PyQt6 Pillow`) |
| Rhubarb Lip Sync 1.14.0 | `v2/vendor/rhubarb/rhubarb` (bundled), or any `rhubarb` on `$PATH` |
| Pre-built viseme frames | `v2/avatar/frames/<character>/{X,A,B,C,D,E,F,G,H}.png` |

## Enable / disable

`v2/config.yaml`:

```yaml
avatar:
  enabled: true
  character: raccoon-hacker
  recognizer: phonetic        # or pocketSphinx
  extended_shapes: GH         # mouth shapes beyond the A-F+X core set
  rhubarb_path: null          # null = auto-detect
```

Set `enabled: false` to leave the avatar off. If PyQt6, Rhubarb, or the frames
folder is missing, the controller logs the reason and the assistant proceeds
without an avatar (no crash, no silence).

## Built-in characters

| Name | Vibe | Source |
|---|---|---|
| `raccoon-hacker` | Cyberpunk raccoon in a circuit hoodie | ChatGPT image |
| `owl-wizard` | Wise owl in a star-covered hat | ChatGPT image |
| `axolotl-astronaut` | Cybernetic axolotl in a domed helmet | ChatGPT image |
| `axolotl-helmet` | Same vibe, alternate generation (Gemini) | Gemini image |
| `raccoon-cyber` | Wider 3×4 raccoon variant (Gemini) | Gemini image |

Swap at any time by editing `avatar.character` in `config.yaml` and restarting,
or programmatically with `controller.set_character(name)`.

## Adding a new sprite sheet

1. Drop the sheet into `v2/avatar/sources/<name>.png`. Any grid is fine; common
   layouts are 3×3 (9 frames) and 3×4 (12 frames).
2. Add an entry to `v2/avatar/characters.yaml`:

   ```yaml
   characters:
     my-character:
       source: sources/my-character.png
       grid: { cols: 3, rows: 3 }
       visemes:
         X: 0   # idle / closed
         A: 1   # M, B, P
         B: 2   # K, S, T
         C: 3   # EH
         D: 4   # AA (wide open)
         E: 5   # AO (rounded oh)
         F: 6   # UW (puckered ooo)
         G: 7   # F, V (teeth on lip) — fall back to a closed frame if your sheet skipped this
         H: 8   # L  (tongue) — fall back to D if missing
   ```

   Cell indices are row-major, 0-based. Two visemes can point at the same cell;
   the preprocessor de-duplicates the chroma-key work.

3. Rebuild the frames:

   ```sh
   v2/.venv/bin/python -m avatar.preprocess my-character
   ```

   The preprocessor:
   - Strips the baked checker background with a corner-anchored flood fill.
   - Computes a single bounding box across all 9 used cells and crops every
     frame to it, so the character's center stays fixed when the mouth swaps.
   - Writes `v2/avatar/frames/my-character/{X,A,B,C,D,E,F,G,H}.png`.

4. Point `config.yaml` at it (`avatar.character: my-character`) and restart.

## Testing without the mic loop

```sh
cd v2
.venv/bin/python tools/avatar_smoke.py raccoon-hacker
```

That synthesises a short phrase with `espeak-ng`, runs Rhubarb, ships cues to
the sidecar, and exits. Useful for verifying a new sheet or debugging the
chroma-key.

The sidecar itself also has a demo mode if you just want to see the window:

```sh
.venv/bin/python -m avatar.window --character owl-wizard --demo
```

## Architecture

```
                   ┌────────────────────────────────────────┐
   speak(text) ──▶ │ InterruptibleSpeaker.speak()           │
                   │   synthesize_to_wav(chunk) -> WAV      │
                   │   avatar.preload(WAV)  (Rhubarb)       │
                   │   avatar.play()        (cues)          │
                   │   _play_wav(WAV)       (aplay/sd)      │ ──▶ speakers
                   │   avatar.stop()                        │
                   └─────────────────┬──────────────────────┘
                                     │ stdin JSON
                                     ▼
                   ┌────────────────────────────────────────┐
                   │ avatar.window  (PyQt6 sidecar process) │
                   │   QTimer @ ~60 fps walks viseme cues   │
                   │   Frameless, transparent, always-on-top│
                   │   Anchored to bottom-right of screen   │
                   └────────────────────────────────────────┘
```

Rhubarb's `phonetic` recognizer adds ~0.9 s of preload latency per TTS chunk
on a typical 3-second WAV (single-threaded, ~7 MB binary). For shorter chunks
it scales sub-linearly.

## Troubleshooting

- **Avatar didn't appear** — check the assistant's stdout for `[avatar] disabled:`
  lines. Common causes: PyQt6 missing in the venv, Rhubarb binary missing,
  unknown character name, or frame folder empty.
- **Wayland / GNOME shows nothing** — confirm `QT_QPA_PLATFORM=wayland;xcb` is
  set (the controller sets this by default); the `xcb` fallback covers X11.
- **Head drifts between frames** — re-run `python -m avatar.preprocess` after
  upgrading; older builds did per-frame autocrop and had this bug.
- **Wrong mouth shape** — adjust the `visemes:` map for that character in
  `characters.yaml`. The model rarely follows the requested cell order
  perfectly; visual inspection of the source sheet is the source of truth.
