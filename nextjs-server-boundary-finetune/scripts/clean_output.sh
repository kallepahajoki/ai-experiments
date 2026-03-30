#!/bin/bash
# Clean up previous training run outputs to free disk space on the network volume.
# Run before starting a new training run.
#
# Usage: bash scripts/clean_output.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Cleaning previous training outputs ==="

# Training checkpoints and final adapter
if [ -d "$PROJECT_DIR/output" ]; then
    size=$(du -sh "$PROJECT_DIR/output" 2>/dev/null | cut -f1)
    echo "Removing output/ (${size})..."
    rm -rf "$PROJECT_DIR/output"
fi

# Merged model / GGUF intermediates
for dir in /workspace/gguf /workspace/gguf_gguf; do
    if [ -d "$dir" ]; then
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        echo "Removing ${dir}/ (${size})..."
        rm -rf "$dir"
    fi
done

# Stale GGUF files in project root
find "$PROJECT_DIR" -maxdepth 1 -name "*.gguf" -exec rm -v {} \;

echo ""
df -h /workspace 2>/dev/null || true
echo ""
echo "=== Done ==="
