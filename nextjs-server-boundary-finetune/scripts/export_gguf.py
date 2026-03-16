#!/usr/bin/env python3
"""Export fine-tuned LoRA adapter as GGUF for Ollama."""

from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    "output/final",
    max_seq_length=4096,
    load_in_4bit=False,
    load_in_16bit=True,
    full_finetuning=False,
)

print("Exporting to GGUF Q5_K_M...")
model.save_pretrained_gguf("output/gguf", tokenizer, quantization_method="q5_k_m")
print("Done! GGUF saved to output/gguf/")
