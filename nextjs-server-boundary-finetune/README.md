# Next.js Server Boundary Fix — LoRA Fine-tune

Fine-tuning Qwen 3.5 with LoRA to fix Next.js webpack build errors where Node.js
built-in modules fail to resolve because they leak into the webpack bundle via
instrumentation hooks or import chains.

## The Problem

The base model gets *close* but uses the wrong webpack mechanism:
- **What it does:** `resolve.fallback: { crypto: false }` — silences the error
  but makes modules `undefined` at runtime (crashes)
- **What it should do:** `config.externals = ['crypto', 'net', ...]` — tells
  webpack to leave these as runtime requires (works correctly)

The larger MoE variants get this right. This fine-tune aims to close that gap.

## Hardware Options

Qwen 3.5 uses a **hybrid architecture** with Mamba-style linear attention (SSM)
layers interleaved with standard transformer layers. The SSM layers use custom
module types that **bitsandbytes cannot quantize to 4-bit**.

| Setup | Model | VRAM needed | Notes |
|-------|-------|-------------|-------|
| **A100 80GB (cloud)** | 27B | ~66 GB | Primary target. RunPod/Lambda/Vast.ai |
| RTX 4090 (local) | 9B | ~22 GB | Local fallback, less capable base |

Uses [Unsloth](https://unsloth.ai) for efficient loading of the hybrid architecture.

## Project Structure

```
nextjs-server-boundary-finetune/
├── configs/
│   ├── a100_80gb.yaml            # 27B on A100 80GB (cloud) — recommended
│   └── qlora_4090.yaml           # 9B on RTX 4090 (local fallback)
├── data/
│   ├── generate_training_data.py # Generates synthetic training examples
│   ├── train.jsonl               # 46 training examples (generated)
│   ├── val.jsonl                 # 3 validation examples (split)
│   └── real_project_context.json # Real ai-toolkit files for reference
├── eval/
│   ├── eval_on_project.py        # Evaluation script (scoring + build test)
│   └── results/                  # Eval results per model
├── scripts/
│   ├── train.py                  # LoRA training script (Unsloth)
│   ├── merge_and_export.py       # Merge adapter + export for Ollama
│   └── cloud_setup.sh            # Bootstrap script for RunPod
├── requirements.txt
└── README.md
```

## Quick Start (Cloud — A100 80GB)

```bash
git clone <this-repo>
cd nextjs-server-boundary-finetune
bash scripts/cloud_setup.sh          # ~20-30 min (compiles CUDA extensions + downloads 52GB model)
python scripts/train.py --config configs/a100_80gb.yaml
```

See [CLOUD_TRAINING.md](CLOUD_TRAINING.md) for detailed RunPod setup (volume config, disk sizing, troubleshooting).

## Quick Start (Local — RTX 4090)

```bash
pip install -r requirements.txt
python scripts/train.py --config configs/qlora_4090.yaml
```

Note: Only trains the 9B model locally. The 27B model requires >= 70 GB VRAM.

## Evaluate

```bash
# Via Ollama
python eval/eval_on_project.py --ollama --model qwen3.5:27b --save-response eval/results/base_response.txt

# Via Unsloth (needs enough VRAM for the model)
python eval/eval_on_project.py --model Qwen/Qwen3.5-27B --save-response eval/results/base_response.txt

# Fine-tuned model
python eval/eval_on_project.py --model Qwen/Qwen3.5-27B --adapter output/final
```

## Export for Ollama

```bash
python scripts/merge_and_export.py --adapter output/final --output output/merged --ollama
ollama create qwen3-5-27b-nextjs-fix -f output/merged/Modelfile
```

## Training Data Design

The training examples teach three things:

1. **The correct mechanism:** webpack `externals` (not `resolve.fallback`)
2. **Transitive deps:** npm packages like `pg` need externalizing too
   (they internally use `net`, `dns`, `stream` etc.)
3. **The wrong approaches:** explicit negative examples showing why
   `resolve.fallback: false` and client-side fallbacks don't work

46 examples with variations in:
- Config file format (.js vs .mjs)
- Module combinations (crypto, net, fs, pg, mongoose, etc.)
- Import chain patterns (instrumentation, API routes, middleware)
- With/without discussion of wrong approaches

## Evaluation Criteria

The eval script scores on 12 points:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| uses_externals | Critical | Uses `config.externals`, not fallback |
| avoids_fallback | Critical | Doesn't recommend `resolve.fallback` as the fix |
| checks_isServer | Critical | Guards with `if (isServer)` |
| includes_pg | Critical | Externalizes `pg` (transitive dep) |
| includes_crypto | Normal | Includes directly failing module |
| includes_net | Normal | Includes directly failing module |
| includes_fs | Normal | Includes directly failing module |
| includes_path | Normal | Includes directly failing module |
| includes_events | Normal | Includes implied dependency |
| includes_pgpass | Normal | Includes transitive dep of pg |
| includes_split2 | Normal | Includes transitive dep of pg |
| spreads_existing | Normal | Preserves existing externals |

**Critical pass** = all 4 critical criteria met.
