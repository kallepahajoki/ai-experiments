#!/usr/bin/env python3
"""
Merge LoRA adapter into base model and export as GGUF for Ollama.

Uses llama.cpp for fast conversion (instead of Unsloth's slow Python export).

Usage:
    python export_to_ollama.py --model 4b --quant Q4_K_M
    python export_to_ollama.py --model 0.8b --quant Q8_0
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE_MODELS = {
    "0.8b": "Qwen/Qwen3.5-0.8B",
    "2b":   "Qwen/Qwen3.5-2B",
    "4b":   "Qwen/Qwen3.5-4B",
    "9b":   "Qwen/Qwen3.5-9B",
}

SCRIPT_DIR = Path(__file__).resolve().parent
LLAMA_CPP_DIR = SCRIPT_DIR / "../../llama.cpp"
CONVERT_SCRIPT = LLAMA_CPP_DIR / "convert_hf_to_gguf.py"
LLAMA_QUANTIZE = LLAMA_CPP_DIR / "build/bin/llama-quantize"
DEFAULT_GGUF_OUTPUT = Path("/mnt/c/AI/GGUF")


def main():
    parser = argparse.ArgumentParser(description="Export finetuned model to Ollama")
    parser.add_argument("--model", choices=["0.8b", "2b", "4b", "9b"], required=True)
    parser.add_argument("--quant", default="Q4_K_M",
                        help="GGUF quantization (Q4_K_M, Q8_0, F16)")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--gguf-output-dir", default=str(DEFAULT_GGUF_OUTPUT),
                        help="Directory for final quantized GGUF files")
    parser.add_argument("--llama-cpp-dir", default=str(LLAMA_CPP_DIR))
    args = parser.parse_args()

    base_model = BASE_MODELS[args.model]
    model_tag = f"qwen3.5-{args.model}-fi-ner"
    adapter_path = Path(args.output_dir) / f"{model_tag}" / "adapter"
    merged_path = Path(args.output_dir) / f"merged-{model_tag}"
    gguf_output_dir = Path(args.gguf_output_dir)

    convert_script = Path(args.llama_cpp_dir) / "convert_hf_to_gguf.py"
    llama_quantize = Path(args.llama_cpp_dir) / "build/bin/llama-quantize"

    if not adapter_path.exists():
        print(f"Adapter not found at {adapter_path}")
        print("Run train.py first.")
        return

    if not convert_script.exists():
        print(f"llama.cpp not found at {args.llama_cpp_dir}")
        print("Clone it: git clone https://github.com/ggerganov/llama.cpp")
        return

    if not llama_quantize.exists():
        print(f"llama-quantize not found at {llama_quantize}")
        print(f"Build it: cd {args.llama_cpp_dir} && cmake -B build && cmake --build build --config Release -j $(nproc)")
        return

    # Step 1: Merge LoRA adapter into base model
    print(f"=== Step 1/3: Merging LoRA adapter into base model ===")
    print(f"  Base model: {base_model}")
    print(f"  Adapter:    {adapter_path}")
    print(f"  Merged dir: {merged_path}")

    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    print(f"Loading base model {base_model}...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model, dtype=torch.bfloat16, trust_remote_code=True
    )
    tokenizer = AutoTokenizer.from_pretrained(str(adapter_path), trust_remote_code=True)

    print(f"Loading LoRA adapter from {adapter_path}...")
    model = PeftModel.from_pretrained(model, str(adapter_path))

    print("Merging...")
    model = model.merge_and_unload()

    merged_path.mkdir(parents=True, exist_ok=True)
    print(f"Saving merged model to {merged_path}...")
    model.save_pretrained(str(merged_path), safe_serialization=True)
    tokenizer.save_pretrained(str(merged_path))

    # Free GPU memory
    del model
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Step 2: Convert to GGUF (f16)
    print(f"\n=== Step 2/3: Converting to GGUF (f16) ===")
    f16_gguf = merged_path / f"{model_tag}.f16.gguf"
    subprocess.run(
        [sys.executable, str(convert_script), str(merged_path),
         "--outfile", str(f16_gguf), "--outtype", "f16"],
        check=True,
    )

    # Step 3: Quantize
    print(f"\n=== Step 3/3: Quantizing to {args.quant} ===")
    gguf_output_dir.mkdir(parents=True, exist_ok=True)
    quantized_gguf = gguf_output_dir / f"{model_tag}.{args.quant}.gguf"
    subprocess.run(
        [str(llama_quantize), str(f16_gguf), str(quantized_gguf), args.quant],
        check=True,
    )

    # Create Ollama Modelfile
    modelfile_content = f"""FROM {quantized_gguf}
PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER stop <|im_end|>

SYSTEM Olet nimettyjen entiteettien tunnistaja (NER). Poimi tekstistä kaikki nimetyt entiteetit ja palauta JSON-lista."""

    modelfile_path = gguf_output_dir / f"Modelfile.{model_tag}"
    modelfile_path.write_text(modelfile_content)

    print(f"\n=== Conversion complete ===")
    print(f"GGUF:      {quantized_gguf}")
    print(f"Modelfile: {modelfile_path}")
    print(f"\nTo import into Ollama:")
    print(f"  ollama create {model_tag} -f {modelfile_path}")
    print(f"  ollama run {model_tag}")


if __name__ == "__main__":
    main()
