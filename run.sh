#!/bin/bash
# Echo-Node Startup Script
# Usage: ./run.sh

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║              Echo-Node Voice AI v1.0                  ║"
echo "╚═══════════════════════════════════════════════════════╝"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check prerequisites
check_prereq() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}ERROR: Python 3 not found${NC}"
        exit 1
    fi
    
    if ! command -v bun &> /dev/null; then
        echo -e "${RED}ERROR: Bun not found${NC}"
        exit 1
    fi
    
    if ! command -v ollama &> /dev/null; then
        echo -e "${YELLOW}WARNING: Ollama not found. Install from https://ollama.ai${NC}"
    fi
}

# Install dependencies
install_deps() {
    echo -e "\n${YELLOW}[1/4] Installing Python dependencies...${NC}"
    cd worker
    pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt
    cd ..
    
    echo -e "\n${YELLOW}[2/4] Installing Bun dependencies...${NC}"
    cd gateway
    bun install
    cd ..
}

# Download models
download_models() {
    echo -e "\n${YELLOW}[3/4] Downloading ML models...${NC}"
    cd worker
    python3 download_models.py
    cd ..
}

# Start Ollama
start_ollama() {
    if command -v ollama &> /dev/null; then
        echo -e "\n${YELLOW}[Ollama] Checking...${NC}"
        if ! curl -s http://localhost:11434 >/dev/null 2>&1; then
            echo -e "${YELLOW}[Ollama] Starting...${NC}"
            ollama serve &
            sleep 3
            
            echo -e "${YELLOW}[Ollama] Pulling phi4 model (~4GB)...${NC}"
            ollama pull phi4
        else
            echo -e "${GREEN}[Ollama] Already running${NC}"
        fi
    fi
}

# Start worker
start_worker() {
    echo -e "\n${YELLOW}[4/4] Starting Worker...${NC}"
    cd worker
    python3 main.py &
    WORKER_PID=$!
    cd ..
}

# Start gateway
start_gateway() {
    echo -e "\n${GREEN}[Gateway] Starting...${NC}"
    cd gateway
    bun run src/index.ts &
    GATEWAY_PID=$!
    cd ..
}

# Main
main() {
    check_prereq
    
    # Check for --skip-deps flag
    SKIP_DEPS=false
    for arg in "$@"; do
        if [ "$arg" = "--skip-deps" ]; then
            SKIP_DEPS=true
        fi
    done
    
    if [ "$SKIP_DEPS" = false ]; then
        install_deps
        download_models
    else
        echo -e "${YELLOW}Skipping dependency installation${NC}"
    fi
    
    start_ollama
    start_worker
    start_gateway
    
    echo -e "\n${GREEN}╔═══════════════════════════════════════════════════════╗"
    echo "║  Echo-Node is running!                                  ║"
    echo "║  - Worker: http://localhost:9001 (WebSocket)           ║"
    echo "║  - Gateway: http://localhost:3000 (REST + WebSocket)   ║"
    echo "║                                                           ║"
    echo "║  Say 'Hey Gimp' to activate, or press Enter for         ║"
    echo "║  keyboard trigger.                                       ║"
    echo "╚═══════════════════════════════════════════════════════╝${NC}"
    
    # Wait for Ctrl+C
    trap "echo -e '\n${YELLOW}Shutting down...${NC}'; kill \$WORKER_PID \$GATEWAY_PID 2>/dev/null; exit 0" INT TERM
    
    wait
}

main "$@"
