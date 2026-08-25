#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Echo-Node — One-command setup
# ══════════════════════════════════════════════════════════════════

set -euo pipefail

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              Echo-Node Voice Agent Setup                  ║"
echo "╚═══════════════════════════════════════════════════════════╝"

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "  Root: $ROOT"

# ── 1. Python venv ──
echo ""
echo "── 1. Python virtual environment ──"
if [ ! -d "$ROOT/.venv" ]; then
    python3 -m venv "$ROOT/.venv"
    echo "  Created .venv"
fi
source "$ROOT/.venv/bin/activate"

# ── 2. Install Python deps ──
echo ""
echo "── 2. Python dependencies ──"
pip install -q --upgrade pip
pip install -q -e "$ROOT" 2>/dev/null || pip install -q websockets pyaudio 2>/dev/null
pip install -q -r "$ROOT/tui/requirements.txt" 2>/dev/null || true
echo "  Done"

# ── 3. Bun deps (gateway + frontend) ──
echo ""
echo "── 3. Bun dependencies ──"
if command -v bun &> /dev/null; then
    cd "$ROOT/gateway" && bun install --silent 2>/dev/null && echo "  Gateway: ✓"
    cd "$ROOT/frontend" && bun install --silent 2>/dev/null && echo "  Frontend: ✓"
    cd "$ROOT"
else
    echo "  WARNING: bun not found. Install: curl -fsSL https://bun.sh/install | bash"
fi

# ── 4. Legacy model setup ──
echo ""
echo "── 4. Legacy models (optional) ──"
if [ -f "$ROOT/v2/setup.sh" ]; then
    cd "$ROOT/v2" && bash setup.sh --models-only 2>/dev/null || true
    cd "$ROOT"
    echo "  Legacy models: ✓"
else
    echo "  Skipped (v2/setup.sh not found)"
fi

# ── 5. Desktop entry ──
echo ""
echo "── 5. Desktop entry ──"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
cp "$ROOT/echo-node.desktop" "$DESKTOP_DIR/" 2>/dev/null && echo "  Installed" || echo "  Skipped"

# ── 6. Config ──
echo ""
echo "── 6. Configuration ──"
if [ ! -f "$ROOT/config.yaml" ]; then
    if [ -f "$ROOT/v2/config.yaml" ]; then
        cp "$ROOT/v2/config.yaml" "$ROOT/config.yaml"
        echo "  Copied from v2/config.yaml"
    else
        echo "  WARNING: No config.yaml found. Create one or copy from config.example.yaml"
    fi
fi

# ── 7. Install CLI ──
echo ""
echo "── 7. CLI entry point ──"
CLI_DIR="${HOME}/.local/bin"
mkdir -p "$CLI_DIR"
cat > "$CLI_DIR/echo-node" << 'CLISCRIPT'
#!/bin/bash
ROOT="$(cd "$(dirname "$(dirname "$(readlink -f "$0")")")" && pwd)"
if [ -f "$ROOT/.venv/bin/python3" ]; then
    exec "$ROOT/.venv/bin/python3" -m echo_node.cli "$@"
else
    exec python3 -m echo_node.cli "$@"
fi
CLISCRIPT
chmod +x "$CLI_DIR/echo-node"
echo "  Installed to $CLI_DIR/echo-node"
echo "  Add to PATH if needed: export PATH=\"\$PATH:$CLI_DIR\""

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  Setup Complete!                                         ║"
echo "║                                                           ║"
echo "║  Try:    echo-node --help                                 ║"
echo "║  Web:    echo-node --web                                  ║"
echo "║  TUI:    echo-node --tui                                  ║"
echo "║  Voice:  echo-node --voice-mode                            ║"
echo "║                                                           ║"
echo "║  Set env vars:                                            ║"
echo "║    export GEMINI_API_KEY='your-key'                      ║"
echo "║    export OPENAI_API_KEY='your-key'                      ║"
echo "╚═══════════════════════════════════════════════════════════╝"
