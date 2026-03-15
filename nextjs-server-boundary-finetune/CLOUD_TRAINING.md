# Cloud Training on RunPod (A100 80GB)

## Pod Configuration

| Setting | Value |
|---------|-------|
| GPU | 1x A100 80GB (or H100) |
| Template | RunPod PyTorch (comes with CUDA 12.4 + torch pre-installed) |
| Container disk | 20 GB (minimum) |
| Network volume | 50 GB (stores model weights + pip packages across restarts) |

### Network Volume Setup

Attach a network volume so you don't re-download 52 GB of model weights and
recompile CUDA extensions every time you start a pod.

1. In RunPod, create a **Network Volume** (50 GB, same region as your pod)
2. Attach it when creating the pod — it mounts at `/workspace`
3. Set the HuggingFace cache to use the volume:

```bash
export HF_HOME=/workspace/hf_cache
```

Add this to your `.bashrc` on the pod so it persists:

```bash
echo 'export HF_HOME=/workspace/hf_cache' >> ~/.bashrc
```

## Setup & Training

```bash
git clone <this-repo>
cd nextjs-server-boundary-finetune
bash scripts/cloud_setup.sh
python scripts/train.py --config configs/a100_80gb.yaml
```

The setup script takes ~20-30 minutes:
- pip packages: ~5 min (mostly compiling `causal-conv1d` and `mamba-ssm` CUDA extensions)
- Model download: ~10-20 min (52 GB)

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

The RunPod PyTorch template comes with torch pre-installed. If pip tries to
**upgrade torch**, it downloads ~8 GB of nvidia CUDA wheels and can fill the
container disk.

Fix: the setup script uses `--no-deps` for packages that would pull in a new
torch. If you're installing manually, avoid `pip install torch` or any package
that pins a different torch version.

To free space:
```bash
pip cache purge
rm -rf /tmp/pip-*
```

### `causal-conv1d` or `mamba-ssm` build takes forever

These are CUDA C++ extensions that compile from source. 5-10 minutes each is
normal. Use `--no-build-isolation` for `mamba-ssm` if the default fails:

```bash
pip install mamba-ssm --no-build-isolation
```

### `ModuleNotFoundError: No module named 'datasets'`

The initial `pip install -r requirements.txt` failed partway through (likely
on the `unsloth` extras specifier) and nothing got installed. Use the setup
script instead of installing from requirements.txt directly:

```bash
bash scripts/cloud_setup.sh
```

### Reusing a Volume Across Pod Restarts

If you attached a network volume and set `HF_HOME=/workspace/hf_cache`, the
model weights persist. You still need to re-run the setup script for pip
packages (they live on the container disk), but the model download step will
be skipped since the weights are already cached on the volume.
