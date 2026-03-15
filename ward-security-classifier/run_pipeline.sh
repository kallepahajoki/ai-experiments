#!/usr/bin/env bash
# Anvil Ward — Full fine-tuning pipeline.
#
# Usage:
#   bash run_pipeline.sh                        # Run all steps (default config.yaml)
#   bash run_pipeline.sh --config config-2b.yaml  # Use a specific model config
#   bash run_pipeline.sh --skip-data           # Skip data generation (use existing JSONL)
#   bash run_pipeline.sh --skip-gguf           # Train + evaluate only, skip GGUF conversion
#
# Steps:
#   1. Generate training data from generate_data.py
#   2. Fine-tune the model
#   3. Evaluate the model
#   4. Convert to GGUF and copy to output directory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python3"

SKIP_DATA=false
SKIP_GGUF=false
CONFIG="config.yaml"

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-data) SKIP_DATA=true; shift ;;
        --skip-gguf) SKIP_GGUF=true; shift ;;
        --config) CONFIG="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "Using config: ${CONFIG}"

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Error: venv not found. Set up first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Step 1: Generate data
if [[ "$SKIP_DATA" == false ]]; then
    echo "=== Step 1/4: Generating training data ==="
    "$VENV_PYTHON" "${SCRIPT_DIR}/data/generate_data.py"
    echo ""
else
    echo "=== Step 1/4: Skipping data generation ==="
fi

# Step 2: Train
echo "=== Step 2/4: Fine-tuning model ==="
"$VENV_PYTHON" "${SCRIPT_DIR}/train.py" --config "${CONFIG}"
echo ""

# Step 3: Evaluate
echo "=== Step 3/4: Evaluating model ==="
"$VENV_PYTHON" "${SCRIPT_DIR}/evaluate.py" --config "${CONFIG}"
echo ""

# Step 4: Convert to GGUF
if [[ "$SKIP_GGUF" == false ]]; then
    echo "=== Step 4/4: Converting to GGUF ==="
    bash "${SCRIPT_DIR}/deploy/convert_to_gguf.sh"
else
    echo "=== Step 4/4: Skipping GGUF conversion ==="
fi

echo ""
echo "=== Pipeline complete ==="
