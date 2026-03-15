#!/usr/bin/env python3
"""
Merge LoRA adapter with base model and export for Ollama.

After training, this script:
1. Loads the base model + LoRA adapter
2. Merges the adapter weights into the base model
3. Saves the merged model in a format Ollama can import

Usage:
    # Merge and save as safetensors
    python scripts/merge_and_export.py --adapter output/final --output output/merged

    # Also create Ollama Modelfile
    python scripts/merge_and_export.py --adapter output/final --output output/merged --ollama
"""

import argparse
from pathlib import Path

from unsloth import FastLanguageModel


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter and export")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3.5-27B",
                        help="Base model name (e.g. Qwen/Qwen3.5-27B or Qwen/Qwen3.5-9B)")
    parser.add_argument("--adapter", type=str, required=True,
                        help="Path to LoRA adapter directory")
    parser.add_argument("--output", type=str, required=True,
                        help="Output directory for merged model")
    parser.add_argument("--ollama", action="store_true",
                        help="Generate Ollama Modelfile")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading base model: {args.model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=4096,
        load_in_4bit=False,
        load_in_16bit=True,
        full_finetuning=False,
    )

    print(f"Loading adapter from: {args.adapter}")
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, args.adapter)

    print("Merging adapter into base model...")
    model = model.merge_and_unload()

    print(f"Saving merged model to: {output_dir}")
    model.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))

    if args.ollama:
        modelfile_path = output_dir / "Modelfile"
        with open(modelfile_path, "w") as f:
            f.write(f"FROM {output_dir}\n")
            f.write('PARAMETER temperature 0.1\n')
            f.write('PARAMETER num_predict 4096\n')
            f.write(f'SYSTEM """You are an expert software engineer. When given a coding task, analyze the problem carefully, explain your reasoning, then provide the fix. Focus on correctness - use the right mechanism for the problem, not just something that silences the error."""\n')
        model_slug = args.model.split("/")[-1].lower().replace(".", "-")
        print(f"Ollama Modelfile written to {modelfile_path}")
        print(f"\nTo import into Ollama:")
        print(f"  ollama create {model_slug}-nextjs-fix -f {modelfile_path}")

    print("Done!")


if __name__ == "__main__":
    main()
