# Other Laptop Setup — Echo-Node + T3 Code Remote Control

## 1. Install T3 Code CLI

```bash
npm install -g t3code-cli
```

## 2. Pair with This Machine

1. On **this machine** (Cheta-surface-studio), launch T3 Code:
   ```bash
   t3
   ```
   Then in the T3 Code UI, go to Settings → Copy Pairing URL.

2. On **the other laptop**:
   ```bash
   t3cli auth pair --url <paste-pairing-url-here>
   ```

3. Verify:
   ```bash
   t3cli auth status
   t3cli project list
   ```

## 3. Start a Remote Session

```bash
t3cli start "Implement feature X" --worktree ~/code/voice-agent --wait
```

Or attach to a running session:
```bash
t3cli list
t3cli attach <session-id>
```

## 4. Environment Variables (for Echo-Node)

The other laptop needs these env vars for direct API access:

```bash
export GEMINI_API_KEY=<copy-from-primary-laptop-env>
export OPENROUTER_API_KEY=<copy-from-primary-laptop-env>
export ANTHROPIC_API_KEY=<copy-from-primary-laptop-env>
export GROQ_API_KEY=<copy-from-primary-laptop-env>
export OPENCODE_API_KEY=<copy-from-primary-laptop-env>
```

## 5. Grafana Dashboard

Open https://aaaronmiller.grafana.net in your browser (log in with Google account).
Metrics from this machine are flowing to Grafana Cloud already.

## 6. Aliases (on this machine)

Already set in ~/.bashrc:
- `t3` → T3 Code AppImage
- `t3cli` → T3 Code CLI
- `opencode` → OpenCode (default model: opencode-go/deepseek-v4-flash)
- `dsh` → DeepSeek Harness (via OpenRouter, model: deepseek/deepseek-v4-flash)
