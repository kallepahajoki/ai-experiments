#!/usr/bin/env python3
"""
LoRA finetune Qwen 3.5 for Finnish NER using Unsloth.

Targets: qwen3.5:0.8b, qwen3.5:2b, qwen3.5:4b
Hardware: RTX 4090 (24GB VRAM), QLoRA 4-bit

Usage:
    python train.py --model 0.8b --epochs 3
    python train.py --model 4b --epochs 2
"""

import argparse
from pathlib import Path

MODEL_MAP = {
    "0.8b": "Qwen/Qwen3.5-0.8B",
    "2b":   "Qwen/Qwen3.5-2B",
    "4b":   "Qwen/Qwen3.5-4B",
}

BATCH_SIZE_MAP = {
    "0.8b": 4,
    "2b":   2,
    "4b":   1,
}


def main():
    parser = argparse.ArgumentParser(description="Finetune Qwen for Finnish NER")
    parser.add_argument("--model", choices=["0.8b", "2b", "4b"], required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    args = parser.parse_args()

    model_name = MODEL_MAP[args.model]
    output_path = Path(args.output_dir) / f"qwen3.5-{args.model}-fi-ner"
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Finetuning {model_name} for Finnish NER")
    print(f"LoRA rank: {args.lora_rank}, LR: {args.learning_rate}")
    print(f"Output: {output_path}")

    # ── Load model with Unsloth ──
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
        dtype=None,  # auto-detect
    )

    # ── Apply LoRA ──
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_rank,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=args.lora_rank,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        max_seq_length=args.max_seq_length,
    )

    # ── Load data ──
    from datasets import load_dataset

    dataset = load_dataset(
        "json",
        data_files={
            "train": f"{args.data_dir}/train.jsonl",
            "eval": f"{args.data_dir}/eval.jsonl",
        },
    )

    # ── Tokenize using chat template ──
    def format_example(example):
        messages = example["messages"]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        return {"text": text}

    dataset = dataset.map(format_example)

    # ── Train ──
    from trl import SFTTrainer, SFTConfig

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        args=SFTConfig(
            output_dir=str(output_path),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=BATCH_SIZE_MAP[args.model],
            gradient_accumulation_steps=8,
            warmup_steps=50,
            learning_rate=args.learning_rate,
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=100,
            save_strategy="epoch",
            fp16=True,
            max_seq_length=args.max_seq_length,
            dataset_text_field="text",
        ),
    )

    print("Starting training...")
    trainer.train()

    # ── Save adapter ──
    adapter_path = output_path / "adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    print(f"Adapter saved to {adapter_path}")


if __name__ == "__main__":
    main()
