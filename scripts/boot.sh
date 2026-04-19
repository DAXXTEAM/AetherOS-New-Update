#!/bin/bash
# AetherOS Master Boot Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================================"
echo "  AetherOS Boot Sequence"
echo "  $(date)"
echo "================================================"

# Ensure Python environment
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required"
    exit 1
fi

# Check dependencies
echo "[1/4] Checking dependencies..."
python3 -c "import chromadb, langgraph, langchain, pydantic, cryptography" 2>/dev/null || {
    echo "Installing dependencies..."
    pip install chromadb langgraph langchain langchain-core pydantic cryptography 2>&1 | tail -3
}

# Create directories
echo "[2/4] Creating directories..."
mkdir -p ~/.aetheros/{logs,chromadb,audit}
mkdir -p ~/aetheros_workspace

# Verify system
echo "[3/4] Running system check..."
cd "$PROJECT_DIR"
python3 -c "
import sys
sys.path.insert(0, '.')
from config.settings import AetherConfig
from core.model_manager import ModelManager
from security.crypto import QuantumSafeCrypto
config = AetherConfig()
config.ensure_dirs()
print('  ✅ Configuration OK')
print('  ✅ Crypto initialized')
print('  ✅ Directories created')
"

# Launch
echo "[4/4] Launching AetherOS..."
echo ""
cd "$PROJECT_DIR"
python3 aetheros.py "$@"
