#!/usr/bin/env bash
# Anvil Firewall — Merge LoRA adapter and convert to GGUF for Ollama deployment.
#
# Usage:
#   bash deploy/convert_to_gguf.sh                                        # default: 4B ward
#   bash deploy/convert_to_gguf.sh --config config-0.8b-gate.yaml --name anvil-ward-gate
#   bash deploy/convert_to_gguf.sh --config config-4b-thinker.yaml --name anvil-ward-thinker
#   bash deploy/convert_to_gguf.sh --adapter-dir ./output/qwen3.5-0.8b-ward --base-model Qwen/Qwen3.5-0.8B --name anvil-ward-gate
#
# Steps:
#   1. Merges LoRA adapter into base model
#   2. Converts merged model to GGUF (f16)
#   3. Quantizes to Q4_K_M
#   4. Copies GGUF + Modelfile to output directory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LLAMA_CPP_DIR="${PROJECT_DIR}/../../llama.cpp"
OUTPUT_DIR="/mnt/c/AI/GGUF"
ADAPTER_DIR=""
BASE_MODEL=""
MODEL_NAME="anvil-ward"
QUANTIZATION="Q4_K_M"
CONFIG_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --llama-cpp-dir) LLAMA_CPP_DIR="$2"; shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --adapter-dir) ADAPTER_DIR="$2"; shift 2 ;;
        --base-model) BASE_MODEL="$2"; shift 2 ;;
        --name) MODEL_NAME="$2"; shift 2 ;;
        --quantization) QUANTIZATION="$2"; shift 2 ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python3"
if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Error: venv not found at ${PROJECT_DIR}/.venv"
    echo "Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Resolve adapter dir and base model from config if provided
if [[ -n "$CONFIG_FILE" ]]; then
    if [[ ! -f "${PROJECT_DIR}/${CONFIG_FILE}" ]]; then
        echo "Error: config not found: ${CONFIG_FILE}"
        exit 1
    fi
    if [[ -z "$ADAPTER_DIR" ]]; then
        ADAPTER_DIR=$("$VENV_PYTHON" -c "import yaml; cfg=yaml.safe_load(open('${PROJECT_DIR}/${CONFIG_FILE}')); print(cfg['training']['output_dir'])")
    fi
    if [[ -z "$BASE_MODEL" ]]; then
        BASE_MODEL=$("$VENV_PYTHON" -c "import yaml; cfg=yaml.safe_load(open('${PROJECT_DIR}/${CONFIG_FILE}')); print(cfg['model']['name'])")
    fi
fi

# Defaults if nothing specified
ADAPTER_DIR="${ADAPTER_DIR:-${PROJECT_DIR}/output/qwen3.5-4b-ward}"
BASE_MODEL="${BASE_MODEL:-Qwen/Qwen3.5-4B}"

# Derive merged dir from model name
MERGED_DIR="${PROJECT_DIR}/output/merged-${MODEL_NAME}"

echo "Configuration:"
echo "  Base model:  ${BASE_MODEL}"
echo "  Adapter:     ${ADAPTER_DIR}"
echo "  Merged dir:  ${MERGED_DIR}"
echo "  Model name:  ${MODEL_NAME}"
echo "  Quantization: ${QUANTIZATION}"
echo "  Output dir:  ${OUTPUT_DIR}"
echo ""

if [[ ! -d "$ADAPTER_DIR" ]]; then
    echo "Error: adapter not found at ${ADAPTER_DIR}"
    echo "Run training first."
    exit 1
fi

CONVERT_SCRIPT="${LLAMA_CPP_DIR}/convert_hf_to_gguf.py"
if [[ ! -f "$CONVERT_SCRIPT" ]]; then
    echo "Error: llama.cpp not found at ${LLAMA_CPP_DIR}"
    echo "Clone it: git clone https://github.com/ggerganov/llama.cpp ${LLAMA_CPP_DIR}"
    exit 1
fi

# Step 1: Merge LoRA adapter into base model
echo "=== Step 1/3: Merging LoRA adapter into base model ==="
"$VENV_PYTHON" -c "
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch, os

print('Loading base model ${BASE_MODEL}...')
model = AutoModelForCausalLM.from_pretrained(
    '${BASE_MODEL}', dtype=torch.bfloat16, trust_remote_code=True
)
tokenizer = AutoTokenizer.from_pretrained('${ADAPTER_DIR}', trust_remote_code=True)

print('Loading LoRA adapter from ${ADAPTER_DIR}...')
model = PeftModel.from_pretrained(model, '${ADAPTER_DIR}')

print('Merging...')
model = model.merge_and_unload()

os.makedirs('${MERGED_DIR}', exist_ok=True)
print('Saving merged model to ${MERGED_DIR}...')
model.save_pretrained('${MERGED_DIR}', safe_serialization=True)
tokenizer.save_pretrained('${MERGED_DIR}')
print('Done.')
"

# Step 2: Convert to GGUF (f16)
echo ""
echo "=== Step 2/3: Converting to GGUF (f16) ==="
F16_GGUF="${MERGED_DIR}/${MODEL_NAME}.f16.gguf"
"$VENV_PYTHON" "$CONVERT_SCRIPT" "$MERGED_DIR" --outfile "$F16_GGUF" --outtype f16
echo "Written: ${F16_GGUF}"

# Step 3: Quantize
echo ""
echo "=== Step 3/3: Quantizing to ${QUANTIZATION} ==="
QUANTIZED_GGUF="${OUTPUT_DIR}/${MODEL_NAME}.${QUANTIZATION}.gguf"
LLAMA_QUANTIZE="${LLAMA_CPP_DIR}/build/bin/llama-quantize"

if [[ ! -f "$LLAMA_QUANTIZE" ]]; then
    echo "llama-quantize not found. Building llama.cpp..."
    (cd "$LLAMA_CPP_DIR" && cmake -B build && cmake --build build --config Release -j "$(nproc)")
    if [[ ! -f "$LLAMA_QUANTIZE" ]]; then
        echo "Error: build failed, llama-quantize not found at ${LLAMA_QUANTIZE}"
        exit 1
    fi
fi

mkdir -p "$OUTPUT_DIR"
"$LLAMA_QUANTIZE" "$F16_GGUF" "$QUANTIZED_GGUF" "$QUANTIZATION"

echo ""
echo "=== Conversion complete ==="
echo "GGUF:      ${QUANTIZED_GGUF}"
echo "Size:      $(du -h "${QUANTIZED_GGUF}" | cut -f1)"
echo ""
echo "To import into Ollama:"
echo "  ollama create ${MODEL_NAME} -f <Modelfile>"
