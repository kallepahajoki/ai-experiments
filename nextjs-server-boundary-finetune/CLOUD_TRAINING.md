# Cloud Training on RunPod (A100 80GB)

## Pod Configuration

| Setting | Value |
|---------|-------|
| GPU | 1x A100 80GB (or H100) |
| Template | RunPod PyTorch (comes with CUDA + torch pre-installed) |
| Container disk | 20 GB (default is fine) |
| Network volume | 200 GB (model weights ~52 GB, venv ~12 GB, GGUF export needs ~100 GB temp) |

## First-Time Setup

Attach a network volume (50 GB, same region as your pod) — it mounts at `/workspace`.

```bash
git clone <this-repo> /workspace/git/nextjs-server-boundary-finetune
cd /workspace/git/nextjs-server-boundary-finetune
bash scripts/cloud_setup.sh
python scripts/train.py --config configs/a100_80gb.yaml
```

The setup script:
- Creates a Python venv on the volume (`/workspace/venv`)
- Installs all dependencies into the venv
- Downloads model weights to `/workspace/hf_cache` (~52 GB)
- Optionally compiles CUDA extensions (causal-conv1d, mamba-ssm) — if these
  fail, unsloth falls back to a pure torch implementation

Total setup time: ~20-30 min (mostly model download + optional CUDA compilation).

## Resuming After Pod Restart

The venv and model weights persist on the volume. Just activate and go:

```bash
source /workspace/venv/bin/activate
export HF_HOME=/workspace/hf_cache
cd /workspace/git/nextjs-server-boundary-finetune
python scripts/train.py --config configs/a100_80gb.yaml
```

## Retrieving the Adapter

After training completes, download the LoRA adapter from `output/final/`:

```bash
# Option 1: scp
scp -r output/final/ your-machine:~/adapter/

# Option 2: zip and download via RunPod UI
zip -r adapter.zip output/final
```

## Troubleshooting

### `No space left on device`

Usually caused by pip upgrading torch and downloading ~8 GB of nvidia CUDA
wheels onto the container disk. The setup script avoids this by using a venv
on the network volume. If you hit this anyway:

```bash
pip cache purge
rm -rf /tmp/pip-*
```

### `causal-conv1d` or `mamba-ssm` build fails

These CUDA extensions sometimes fail to compile (nvcc out of memory, version
mismatches). This is OK — unsloth falls back to a pure torch implementation.
Training works, just slightly slower.

To retry manually:
```bash
MAX_JOBS=1 pip install causal-conv1d
MAX_JOBS=1 pip install mamba-ssm --no-build-isolation
```

### `ModuleNotFoundError`

Make sure the venv is activated:
```bash
source /workspace/venv/bin/activate
```

### Import order warning for unsloth

If you see a warning about unsloth needing to be imported before trl/transformers,
the train.py script already handles this — the warning is harmless if using the
provided script.
