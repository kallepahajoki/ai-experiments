#!/bin/bash
# cloud_setup.sh — Bootstrap a RunPod pod for Qwen 3.5 27B LoRA fine-tuning
#
# Assumes: RunPod PyTorch template (CUDA toolkit pre-installed)
# Usage:   bash scripts/cloud_setup.sh
# Then:    python scripts/train.py --config configs/a100_80gb.yaml
#
# IMPORTANT:
#   - Attach a network volume (50 GB) mounted at /workspace.
#   - This script creates a venv on the volume so deps persist across restarts.
#   - Set HF_HOME=/workspace/hf_cache so model weights also persist.

set -euo pipefail

echo "=== Cloud Setup for Qwen 3.5 27B Fine-tuning ==="
echo ""

# 1. System-level build dependencies
echo "--- Installing system dependencies ---"
apt-get update -qq && apt-get install -y --no-install-recommends git build-essential > /dev/null

# 2. Create venv on the network volume (persists across pod restarts)
VENV_DIR="/workspace/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "--- Creating venv at $VENV_DIR ---"
    python -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 3. Set HF cache to volume
export HF_HOME=/workspace/hf_cache

# 4. Install Python dependencies
echo "--- Installing Python dependencies ---"
pip install --upgrade pip -q

# Install torch (will match the pod's CUDA version)
pip install -q torch torchvision

# Install training stack
pip install -q unsloth "transformers<=5.2.0" datasets accelerate peft "trl<=0.24.0" pyyaml

# causal-conv1d and mamba-ssm are optional CUDA extensions for Mamba/SSM layers.
# They compile from source (~5-10 min each). If they fail, unsloth falls back
# to a pure torch implementation (slower but functional).
echo "--- Building causal-conv1d (CUDA extension, ~5 min — optional) ---"
MAX_JOBS=1 pip install -q causal-conv1d 2>/dev/null || echo "WARNING: causal-conv1d build failed — will use torch fallback"

echo "--- Building mamba-ssm (CUDA extension, ~5-10 min — optional) ---"
MAX_JOBS=1 pip install -q mamba-ssm --no-build-isolation 2>/dev/null || echo "WARNING: mamba-ssm build failed — will use torch fallback"

# 5. Verify GPU is visible and has enough VRAM
echo "--- Verifying GPU ---"
python -c "
import torch
assert torch.cuda.is_available(), 'No GPU detected!'
gpu = torch.cuda.get_device_name(0)
vram = torch.cuda.get_device_properties(0).total_mem / 1e9
print(f'  GPU: {gpu}')
print(f'  VRAM: {vram:.1f} GB')
assert vram >= 70, f'Need >= 70 GB VRAM, got {vram:.1f} GB. Use an A100 80GB or H100.'
print('  GPU check passed')
"

# 6. Verify key imports work
echo "--- Verifying imports ---"
python -c "
from unsloth import FastLanguageModel
from datasets import Dataset
from trl import SFTTrainer
print('  All imports OK')
"

# 7. Pre-download model weights so training doesn't stall
echo "--- Downloading Qwen/Qwen3.5-27B weights (~52 GB, may take 10-20 min) ---"
python -c "
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen3.5-27B')
print('  Model download complete')
"

echo ""
echo "=== Setup complete ==="
echo ""
echo "On future pod restarts, just activate the venv:"
echo "  source /workspace/venv/bin/activate"
echo "  export HF_HOME=/workspace/hf_cache"
echo ""
echo "Run training with:"
echo "  python scripts/train.py --config configs/a100_80gb.yaml"
echo ""
echo "After training, download the adapter:"
echo "  scp -r output/final/ your-machine:~/adapter/"
echo "  # or: zip -r adapter.zip output/final && download via RunPod UI"
