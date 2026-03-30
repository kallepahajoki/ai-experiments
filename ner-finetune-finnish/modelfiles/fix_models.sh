#!/usr/bin/env bash
# Fix finetuned model Modelfiles — adds proper Qwen ChatML template
#
# Run this on the 4090 machine (where Ollama runs).
# The FROM directive references the existing model, so Ollama
# reuses the same GGUF weights and just updates the template/params.
#
# Usage:
#   bash fix_models.sh
#
# If Ollama is stuck, restart it first:
#   sudo systemctl restart ollama   # Linux
#   # or kill the ollama process and restart

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Fixing finetuned model templates ==="
echo ""

for size in 0.8b 2b 4b; do
    modelfile="${SCRIPT_DIR}/Modelfile.qwen3.5-fi-ner-${size}"
    model_name="qwen3.5-fi-ner:${size}"

    if [ ! -f "$modelfile" ]; then
        echo "SKIP ${model_name} — Modelfile not found at ${modelfile}"
        continue
    fi

    echo "Creating ${model_name} with ChatML template..."
    ollama create "${model_name}" -f "${modelfile}"
    echo "  Done"
    echo ""
done

echo "=== Verifying ==="
echo ""

# Quick smoke test on 0.8b
echo "Testing qwen3.5-fi-ner:0.8b..."
response=$(ollama run qwen3.5-fi-ner:0.8b "Helsinki on Suomen pääkaupunki." 2>&1 | head -5)
echo "  Response: ${response}"
echo ""
echo "=== All models fixed ==="
