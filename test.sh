#!/bin/bash
# Echo-Node Quick Test Script
# Tests basic connectivity and configuration

set -e

echo "🧪 Echo-Node Quick Test"
echo "======================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

# Check config
echo "1. Checking configuration..."
if [ -f config.yaml ]; then
    pass "config.yaml found"
    
    # Check required fields
    if grep -q "stt:" config.yaml && grep -q "provider:" config.yaml; then
        pass "STT provider configured"
    else
        fail "STT provider not configured"
    fi
    
    if grep -q "tts:" config.yaml && grep -q "provider:" config.yaml; then
        pass "TTS provider configured"
    else
        fail "TTS provider not configured"
    fi
    
    if grep -q "llm:" config.yaml && grep -q "provider:" config.yaml; then
        pass "LLM provider configured"
    else
        fail "LLM provider not configured"
    fi
else
    fail "config.yaml not found - run ./setup.sh first"
    exit 1
fi

echo ""

# Check Python dependencies
echo "2. Checking Python dependencies..."
if [ -d worker/.venv ]; then
    pass "Python virtual environment found"
    
    source worker/.venv/bin/activate
    
    if python -c "import yaml" 2>/dev/null; then
        pass "PyYAML installed"
    else
        fail "PyYAML not installed"
    fi
    
    if python -c "import numpy" 2>/dev/null; then
        pass "NumPy installed"
    else
        fail "NumPy not installed"
    fi
    
    # Optional: check audio libs
    if python -c "import sounddevice" 2>/dev/null; then
        pass "sounddevice installed"
    elif python -c "import pyaudio" 2>/dev/null; then
        pass "PyAudio installed"
    else
        warn "No audio library found (sounddevice or PyAudio)"
    fi
    
    deactivate
else
    fail "Python virtual environment not found - run ./setup.sh"
fi

echo ""

# Check Bun dependencies
echo "3. Checking Bun dependencies..."
if [ -f gateway/package.json ]; then
    pass "Gateway package.json found"
    
    if [ -d gateway/node_modules ] || [ -f gateway/bun.lockb ]; then
        pass "Gateway dependencies installed"
    else
        warn "Gateway dependencies not installed - run 'cd gateway && bun install'"
    fi
else
    fail "Gateway package.json not found"
fi

if [ -f frontend/package.json ]; then
    pass "Frontend package.json found"
    
    if [ -d frontend/node_modules ] || [ -f frontend/bun.lockb ]; then
        pass "Frontend dependencies installed"
    else
        warn "Frontend dependencies not installed - run 'cd frontend && bun install'"
    fi
else
    fail "Frontend package.json not found"
fi

echo ""

# Check models
echo "4. Checking models..."
if [ -d models ]; then
    pass "Models directory found"
    
    if ls models/stt/* 2>/dev/null | head -1 > /dev/null; then
        pass "STT models found"
    else
        warn "No STT models downloaded"
    fi
    
    if ls models/tts/* 2>/dev/null | head -1 > /dev/null; then
        pass "TTS models found"
    else
        warn "No TTS models downloaded"
    fi
    
    if ls models/vad/* 2>/dev/null | head -1 > /dev/null; then
        pass "VAD models found"
    else
        warn "No VAD models downloaded"
    fi
else
    fail "Models directory not found"
fi

echo ""

# Check Ollama (if configured)
echo "5. Checking LLM backend..."
LLM_PROVIDER=$(grep -A2 "llm:" config.yaml | grep "provider:" | awk '{print $2}')

if [ "$LLM_PROVIDER" = "ollama" ]; then
    if command -v ollama &> /dev/null; then
        pass "Ollama CLI found"
        
        if ollama list 2>/dev/null | grep -q .; then
            pass "Ollama models available"
        else
            warn "No Ollama models downloaded - run 'ollama pull llama3.2:7b-q4_K_M'"
        fi
    else
        warn "Ollama CLI not found (required for local LLM)"
    fi
else
    pass "Using cloud LLM provider: $LLM_PROVIDER"
fi

echo ""
echo "======================="
echo "Quick test complete!"
echo ""
echo "Next steps:"
echo "  1. Fix any failed checks above"
echo "  2. Start worker: cd worker && python main.py"
echo "  3. Start gateway: cd gateway && bun run src/index.ts"
echo "  4. (Optional) Start frontend: cd frontend && bun run dev"
echo ""
