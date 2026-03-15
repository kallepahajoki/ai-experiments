#!/usr/bin/env bash
# Ward — Train and evaluate all three model sizes, then benchmark.
#
# Usage:
#   bash run_all_models.sh              # Train + eval all three, then benchmark
#   bash run_all_models.sh --skip-data  # Skip data generation step
#   bash run_all_models.sh --skip-gguf  # Skip GGUF conversion
#   bash run_all_models.sh --benchmark-only  # Only run benchmark (adapters must exist)
#
# Models trained:
#   0.8B  -> ./output/qwen3.5-0.8b-ward
#   2B    -> ./output/qwen3.5-2b-ward
#   4B    -> ./output/qwen3.5-4b-ward

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python3"

SKIP_DATA=false
SKIP_GGUF=false
BENCHMARK_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-data) SKIP_DATA=true; shift ;;
        --skip-gguf) SKIP_GGUF=true; shift ;;
        --benchmark-only) BENCHMARK_ONLY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Error: venv not found. Set up first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [[ "$BENCHMARK_ONLY" == false ]]; then
    # Step 1: Generate data once (shared by all models)
    if [[ "$SKIP_DATA" == false ]]; then
        echo ""
        echo "========================================"
        echo " Step 1: Generating training data"
        echo "========================================"
        "$VENV_PYTHON" "${SCRIPT_DIR}/data/generate_data.py"
    else
        echo "Skipping data generation."
    fi

    # Train each model
    for CONFIG in config-0.8b.yaml config-2b.yaml config-4b.yaml; do
        if [[ ! -f "${SCRIPT_DIR}/${CONFIG}" ]]; then
            echo "Config not found: ${CONFIG} — skipping"
            continue
        fi

        echo ""
        echo "========================================"
        echo " Training: ${CONFIG}"
        echo "========================================"

        PIPELINE_ARGS="--config ${CONFIG} --skip-data"
        if [[ "$SKIP_GGUF" == true ]]; then
            PIPELINE_ARGS="${PIPELINE_ARGS} --skip-gguf"
        fi

        bash "${SCRIPT_DIR}/run_pipeline.sh" ${PIPELINE_ARGS}
    done
fi

# Benchmark
echo ""
echo "========================================"
echo " Benchmark: comparing all three models"
echo "========================================"
"$VENV_PYTHON" "${SCRIPT_DIR}/benchmark.py" \
    --configs config-0.8b.yaml config-2b.yaml config-4b.yaml \
    --skip-missing \
    --output output/benchmark_results.json

echo ""
echo "=== All done ==="
