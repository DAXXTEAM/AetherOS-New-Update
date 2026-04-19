#!/bin/bash
# AetherOS Installation Script
set -e

echo "AetherOS Installer v1.0"
echo "========================"

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ $(echo "$PYTHON_VERSION < 3.10" | bc -l) -eq 1 ]]; then
    echo "ERROR: Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION"

# Install core dependencies
echo "Installing core dependencies..."
pip install \
    chromadb \
    langgraph \
    langchain \
    langchain-core \
    pydantic \
    cryptography \
    2>&1 | tail -3

# Optional: GUI dependencies
echo "Installing GUI dependencies (optional)..."
pip install PyQt6 2>/dev/null || echo "⚠️  PyQt6 not available (GUI mode disabled)"

# Create config directories
mkdir -p ~/.aetheros/{logs,chromadb,audit}
mkdir -p ~/aetheros_workspace

echo ""
echo "✅ AetherOS installed successfully!"
echo ""
echo "Usage:"
echo "  python aetheros.py              # Interactive CLI"
echo "  python aetheros.py --gui        # GUI mode"
echo "  python aetheros.py --task '...' # Single task"
echo "  ./scripts/boot.sh               # Full boot sequence"
