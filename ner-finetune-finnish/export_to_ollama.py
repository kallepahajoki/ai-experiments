#!/usr/bin/env python3
"""
Merge LoRA adapter into base model and export as GGUF for Ollama.

Usage:
    python export_to_ollama.py --model 4b --quant q4_k_m
    python export_to_ollama.py --model 0.8b --quant q8_0
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export finetuned model to Ollama")
    parser.add_argument("--model", choices=["0.8b", "2b", "4b"], required=True)
    parser.add_argument("--quant", default="q4_k_m",
                        help="GGUF quantization (q4_k_m, q8_0, f16)")
    parser.add_argument("--output-dir", default="./output")
    args = parser.parse_args()

    adapter_path = Path(args.output_dir) / f"qwen3.5-{args.model}-fi-ner" / "adapter"
    gguf_path = Path(args.output_dir) / f"qwen3.5-{args.model}-fi-ner-gguf"

    if not adapter_path.exists():
        print(f"Adapter not found at {adapter_path}")
        print("Run train.py first.")
        return

    print(f"Loading adapter from {adapter_path}")

    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter_path),
        max_seq_length=2048,
        load_in_4bit=False,
    )

    # Save as GGUF
    print(f"Exporting to GGUF ({args.quant})...")
    model.save_pretrained_gguf(
        str(gguf_path),
        tokenizer,
        quantization_method=args.quant,
    )

    # Create Ollama Modelfile
    model_tag = f"qwen3.5-{args.model}-fi-ner"
    modelfile_content = f"""FROM ./{args.quant}.gguf
PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER stop <|im_end|>

SYSTEM Olet nimettyjen entiteettien tunnistaja (NER). Poimi tekstistä kaikki nimetyt entiteetit ja palauta JSON-lista."""

    modelfile_path = gguf_path / "Modelfile"
    modelfile_path.write_text(modelfile_content)

    print(f"\nGGUF exported to {gguf_path}")
    print(f"\nTo load in Ollama:")
    print(f"  cd {gguf_path}")
    print(f"  ollama create {model_tag} -f Modelfile")
    print(f"  ollama run {model_tag}")


if __name__ == "__main__":
    main()
