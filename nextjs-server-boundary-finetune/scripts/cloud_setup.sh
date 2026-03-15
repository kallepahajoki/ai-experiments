#!/bin/bash
# cloud_setup.sh — Bootstrap a RunPod pod for Qwen 3.5 27B LoRA fine-tuning
#
# Assumes: RunPod PyTorch template (CUDA 12.4, torch pre-installed)
# Usage:   bash scripts/cloud_setup.sh
# Then:    python scripts/train.py --config configs/a100_80gb.yaml
#
# IMPORTANT:
#   - Use a pod with >= 50 GB disk (container + volume). The model weights
#     alone are ~52 GB, plus pip packages need ~10 GB.
#   - Attach a network volume so you can reuse the setup across pod restarts.
#     Mount it at /workspace and set HF_HOME=/workspace/hf_cache before running.
#   - Do NOT let pip upgrade torch — the RunPod template's torch is pre-built
#     for the pod's CUDA version. Upgrading pulls ~8 GB of nvidia wheels and
#     can fill the disk.

set -euo pipefail

echo "=== Cloud Setup for Qwen 3.5 27B Fine-tuning ==="
echo ""

# 1. System-level build dependencies for causal-conv1d / mamba-ssm compilation
echo "--- Installing system dependencies ---"
apt-get update -qq && apt-get install -y --no-install-recommends git build-essential > /dev/null

# 2. Install Python dependencies
#    Key constraint: keep the pre-installed torch to avoid disk bloat.
echo "--- Installing Python dependencies ---"
pip install --upgrade pip -q

# Core deps — pin torch to avoid upgrade (RunPod's torch is fine)
pip install -q --no-deps transformers peft trl datasets accelerate pyyaml huggingface_hub
# Install their transitive deps without touching torch
pip install -q datasets accelerate peft trl transformers

# Unsloth — install without deps first, then let it pull only what it needs.
# The [cu124-torch240-ampere] extras specifier is fragile; --no-deps is safer.
pip install -q --no-deps unsloth unsloth_zoo

# causal-conv1d and mamba-ssm compile CUDA C++ extensions from source.
# These take 5-10 minutes each — this is normal.
echo "--- Building causal-conv1d (CUDA extension, ~5 min) ---"
pip install -q causal-conv1d

echo "--- Building mamba-ssm (CUDA extension, ~5-10 min) ---"
pip install -q mamba-ssm --no-build-isolation

# 3. Verify GPU is visible and has enough VRAM
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

# 4. Verify key imports work
echo "--- Verifying imports ---"
python -c "
from unsloth import FastLanguageModel
from datasets import Dataset
from trl import SFTTrainer
print('  All imports OK')
"

# 5. Pre-download model weights so training doesn't stall
#    Uses HF_HOME if set (e.g. /workspace/hf_cache on a network volume)
echo "--- Downloading Qwen/Qwen3.5-27B weights (~52 GB, may take 10-20 min) ---"
python -c "
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen3.5-27B')
print('  Model download complete')
"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Run training with:"
echo "  python scripts/train.py --config configs/a100_80gb.yaml"
echo ""
echo "After training, download the adapter:"
echo "  scp -r output/final/ your-machine:~/adapter/"
echo "  # or: zip -r adapter.zip output/final && download via RunPod UI"
