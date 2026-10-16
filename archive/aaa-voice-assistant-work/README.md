# aaa-voice-assistant — preserved user work

Moved here 2026-08-11 from `/home/cheta/code/aaa-voice-assistant` (that repo is
being retired; its install artifacts and junk are quarantined in
`pending-deletions/` inside the old repo, awaiting review).

Contents: the unique components of the project:

- `src/` — Python assistant (STT/TTS, persona, overlay, memory, startup manager)
- `src-tauri/` — Tauri shell (Rust), build artifacts (`target/`) removed
- `docs/`, `tests/`, `cli.py`, `quickstart.py`, `benchmark_memory_large.py`,
  `test_stt.py`
- Frontend/config: `index.html`, `package.json`, `pnpm-*`, `vite.config.*`,
  `tsconfig*`, `tailwind.config.js`, `postcss.config.js`, `tauri.conf.json`
- `requirements.txt`, `AGENTS.md`, `README.md`

Not preserved (reproducible or junk): `node_modules/`, `ai-env/` (venv),
`src-tauri/target/`, audit/process markdown files, `pending-deletions/`
contents.

Git history still exists at `/home/cheta/code/aaa-voice-assistant` (local only —
remote push is impossible: history exceeds GitHub's 2 GiB single-pack limit).
