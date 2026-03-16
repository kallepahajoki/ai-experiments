# Finnish NER Finetuning — Qwen 3.5

QLoRA finetune of Qwen 3.5 (0.8B/2B/4B/9B) on Finnish NER data from Turku NER corpus and FiNER/Digitoday. Motivated by the [Finnish NER benchmark](../ner-benchmark/finnish-benchmark.md) showing that base Qwen 3.5 models are essentially useless for Finnish entity extraction (best F1: 0.274, vs spaCy's 0.417).

## Quick Start

```bash
# 1. Fetch datasets (run from ner-benchmark dir, or copy datasets-fi here)
cd ../ner-benchmark
python fetch_finnish_data.py
cd ../ner-finetune-finnish

# 2. Prepare training data
python prepare_data.py --datasets-dir ../ner-benchmark/datasets-fi

# 3. Install dependencies
pip install -r requirements.txt

# 4. Train all models (0.8b → 2b → 4b → 9b), export GGUF, register in Ollama
python train_all.py

# Or train specific sizes / skip export
python train_all.py --models 0.8b 4b
python train_all.py --skip-export
python train_all.py --models 4b --epochs 3
```

## Expected VRAM Usage (RTX 4090, 24GB)

| Model | QLoRA 4-bit | Training total | Time/epoch (~5k examples) |
|-------|-------------|----------------|--------------------------|
| 0.8B | ~1.5 GB | ~3 GB | ~10-15 min |
| 2B | ~3 GB | ~5 GB | ~25-35 min |
| 4B | ~5 GB | ~10 GB | ~45-60 min |
| 9B | ~8 GB | ~16 GB | ~90-120 min |

## Files

```
ner-finetune-finnish/
├── prepare_data.py        # Convert annotations to instruction-tuning JSONL
├── train.py               # QLoRA finetune with Unsloth (single model)
├── train_all.py           # Train + export + register all model sizes
├── export_to_ollama.py    # Merge adapter + export GGUF + Ollama Modelfile
├── requirements.txt       # Python dependencies
├── data/                  # Generated training data (train.jsonl, eval.jsonl)
└── output/                # Trained adapters and GGUF exports
```

## Training Data

Uses the full Turku NER corpus (~800 docs, 11k entities) and FiNER/Digitoday (~3,700 docs, 196k entities). The `prepare_data.py` script:
- Extracts sentence-level examples with BIO-tagged entities
- Formats as chat messages (system prompt in Finnish, user=text, assistant=JSON entities)
- Keeps ~10% negative examples (sentences with no entities)
- Splits 85/15 train/eval

## After Finetuning

Re-run the Finnish NER benchmark with the finetuned models to measure improvement:

```bash
# Deploy finetuned model
ollama create qwen3.5-4b-fi-ner -f output/qwen3.5-4b-fi-ner-gguf/Modelfile

# Run benchmark (from ai-toolkit/ner-benchmark)
anvil atlas ner --space bench-fi-turku-ner --backend llm -m "qwen3.5-4b-fi-ner" --preview --json > results-fi/qwen_4b_ft_turku-ner.json
```
