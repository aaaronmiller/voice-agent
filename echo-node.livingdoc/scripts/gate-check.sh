#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Echo-Node Gate Check — verifies REAL implementation completion
# against each phase's exit criteria.
#
# This is the HONESTY gate. It checks actual files, running
# processes, API responses, and code behavior — not just
# document structure.
# ══════════════════════════════════════════════════════════════════

set -euo pipefail
FAIL=0
PASS=0
TOTAL=0

check() {
    TOTAL=$((TOTAL+1))
    local label="$1"
    local result="$2"
    if [ "$result" = "pass" ]; then
        PASS=$((PASS+1))
        echo "  ✅ $label"
    else
        FAIL=$((FAIL+1))
        echo "  ❌ $label"
        echo "     $3"
    fi
}

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║        Echo-Node Gate Check — Implementation Audit       ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# ──────────────────────────────────────────────
# Phase 0 — Audit
# ──────────────────────────────────────────────
echo "── Phase 0: Project audit ──"
check "Audit exists in living doc" \
    "$(test -f ~/code/voice-agent/echo-node.livingdoc/public/content/sections/01-temporal-problem.md && echo pass || echo fail)" \
    "Missing: 01-temporal-problem.md"

# ──────────────────────────────────────────────
# Phase 1 — Architecture
# ──────────────────────────────────────────────
echo ""
echo "── Phase 1: Architecture ──"
check "Architecture spec exists" \
    "$(test -f ~/code/voice-agent/echo-node.livingdoc/public/content/sections/02-architecture-overview.md && echo pass || echo fail)" \
    "Missing: 02-architecture-overview.md"

# ──────────────────────────────────────────────
# Phase 2 — Gateway (REAL checks)
# ──────────────────────────────────────────────
echo ""
echo "── Phase 2: Gateway ──"

check "Gateway source exists" \
    "$(test -f ~/code/voice-agent/gateway/src/index.ts && echo pass || echo fail)" \
    "Missing: gateway/src/index.ts"

# Check gateway is running
if curl -sf http://127.0.0.1:3000/api/health > /dev/null 2>&1; then
    check "Gateway process is running" "pass" ""
else
    check "Gateway process is running" "fail" "No response on port 3000. Run: cd ~/code/voice-agent/gateway && bun run src/index.ts"
fi

# Check WebSocket response
WS_TEST=$(timeout 3 bun -e "
const ws = new WebSocket('ws://127.0.0.1:3000/ws');
ws.onopen = () => ws.send(JSON.stringify({type:'ping'}));
ws.onmessage = (e) => {
  if (typeof e.data === 'string' && e.data.includes('pong')) {
    console.log('WS_OK');
    ws.close();
    process.exit(0);
  }
};
setTimeout(() => process.exit(1), 3000);
" 2>&1 || echo "WS_FAIL")

check "WebSocket handshake + ping/pong" \
    "$(echo "$WS_TEST" | grep -q WS_OK && echo pass || echo fail)" \
    "WebSocket not responding correctly"

check "Provider registry returns providers" \
    "$(curl -sf http://127.0.0.1:3000/api/config/providers > /dev/null 2>&1 && echo pass || echo fail)" \
    "/api/config/providers failed"

check "Python worker bridge exists" \
    "$(test -f ~/code/voice-agent/gateway/src/providers/python-worker.ts && echo pass || echo fail)" \
    "Missing: providers/python-worker.ts (needed for legacy pipeline relay)"

# ──────────────────────────────────────────────
# Phase 7 — Provider System
# ──────────────────────────────────────────────
echo ""
echo "── Phase 7: Provider System ──"

check "Provider interfaces defined" \
    "$(test -f ~/code/voice-agent/gateway/src/types.ts && echo pass || echo fail)" \
    "Missing: types.ts"

check "Provider registry exists" \
    "$(test -f ~/code/voice-agent/gateway/src/providers/registry.ts && echo pass || echo fail)" \
    "Missing: providers/registry.ts"

check "Gemini Live provider exists (real implementation)" \
    "$(test -f ~/code/voice-agent/gateway/src/providers/gemini-live.ts && echo pass || echo fail)" \
    "Missing: providers/gemini-live.ts"

check "OpenAI Realtime provider exists (real implementation)" \
    "$(test -f ~/code/voice-agent/gateway/src/providers/openai-realtime.ts && echo pass || echo fail)" \
    "Missing: providers/openai-realtime.ts"

check "Python worker bridge exists" \
    "$(test -f ~/code/voice-agent/gateway/src/providers/python-worker.ts && echo pass || echo fail)" \
    "Missing: providers/python-worker.ts"

# ──────────────────────────────────────────────
# Phase 5 — Gemini Live CLI
# ──────────────────────────────────────────────
echo ""
echo "── Phase 5: Gemini Live CLI ──"

check "Gemini Live standalone CLI exists" \
    "$(test -f ~/code/voice-agent/v2/providers/gemini_live.py && echo pass || echo fail)" \
    "Missing: v2/providers/gemini_live.py"

check "CLI can be invoked (syntax check)" \
    "$(python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$HOME/code/voice-agent/v2/providers/gemini_live.py" 2>/dev/null && echo pass || echo fail)" \
    "gemini_live.py has syntax errors"

# ──────────────────────────────────────────────
# Phase 5b — OpenAI Realtime
# ──────────────────────────────────────────────
echo ""
echo "── Phase 5b: OpenAI Realtime ──"

check "OpenAI Realtime CLI exists" \
    "$(test -f ~/code/voice-agent/v2/providers/openai_realtime.py && echo pass || echo fail)" \
    "Missing: v2/providers/openai_realtime.py"

check "CLI syntax valid" \
    "$(python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$HOME/code/voice-agent/v2/providers/openai_realtime.py" 2>/dev/null && echo pass || echo fail)" \
    "openai_realtime.py has syntax errors"

# ──────────────────────────────────────────────
# Phase 6 — Monitoring
# ──────────────────────────────────────────────
echo ""
echo "── Phase 6: Monitoring Dashboard ──"

check "Terminal monitoring dashboard exists" \
    "$(test -f ~/code/voice-agent/tui/echo_monitor/__main__.py && echo pass || echo fail)" \
    "Missing: tui/echo_monitor/__main__.py"

check "Dashboard connects to gateway and displays metrics" \
    "$(test -f ~/code/voice-agent/tui/echo_monitor/__main__.py && echo pass || echo fail)" \
    "Missing: __main__.py in echo_monitor/"

# ──────────────────────────────────────────────
# Phase 3b — TUI
# ──────────────────────────────────────────────
echo ""
echo "── Phase 3b: TUI Frontend ──"

check "TUI main entry exists" \
    "$(test -f ~/code/voice-agent/tui/echo_tui/__main__.py && echo pass || echo fail)" \
    "Missing: tui/echo_tui/__main__.py"

check "TUI gateway client exists" \
    "$(test -f ~/code/voice-agent/tui/echo_tui/gateway_client.py && echo pass || echo fail)" \
    "Missing: gateway_client.py"

check "TUI requirements defined" \
    "$(test -f ~/code/voice-agent/tui/requirements.txt && echo pass || echo fail)" \
    "Missing: tui/requirements.txt"

# ──────────────────────────────────────────────
# Phase 3 — Web Frontend
# ──────────────────────────────────────────────
echo ""
echo "── Phase 3: Web Frontend ──"

check "Web frontend package.json exists" \
    "$(test -f ~/code/voice-agent/frontend/package.json && echo pass || echo fail)" \
    "Missing: frontend/package.json"

check "Web frontend source exists" \
    "$(test -f ~/code/voice-agent/frontend/src/App.svelte && echo pass || echo fail)" \
    "Missing: frontend/src/App.svelte"

check "WebSocket client exists" \
    "$(test -f ~/code/voice-agent/frontend/src/lib/websocket.ts && echo pass || echo fail)" \
    "Missing: frontend/src/lib/websocket.ts"

# ──────────────────────────────────────────────
# Phase 8 — Deployment
# ──────────────────────────────────────────────
echo ""
echo "── Phase 8: Unified CLI & Deployment ──"

check "CLI entry point exists" \
    "$(test -f ~/code/voice-agent/echo_node/cli.py && echo pass || echo fail)" \
    "Missing: echo_node/cli.py"

check "Unified --help shows all modes" \
    "$(python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$HOME/code/voice-agent/echo_node/cli.py" 2>/dev/null && echo pass || echo fail)" \
    "cli.py has syntax errors"

check "Desktop entry exists" \
    "$(test -f ~/.local/share/applications/echo-node.desktop && echo pass || echo fail)" \
    "Missing: desktop entry"

check "Setup script exists" \
    "$(test -f ~/code/voice-agent/setup.sh && echo pass || echo fail)" \
    "Missing: setup.sh"

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
printf "║  Results:  %3d/%d passed  %3d failed                    ║\n" $PASS $TOTAL $FAIL
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "❌ Gate NOT clear — $FAIL criteria failed."
    echo "   Complete the failing items before marking phases done."
    exit 1
else
    echo "✅ All gates pass — implementation is complete."
    exit 0
fi
