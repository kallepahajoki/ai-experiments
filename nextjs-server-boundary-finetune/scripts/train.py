#!/usr/bin/env python3
"""
LoRA fine-tuning script for Qwen 3.5.

Uses Unsloth for efficient loading of Qwen 3.5's hybrid architecture
(linear attention + full attention layers with Mamba-style SSM).

Trains the model to fix Next.js server-side module resolution errors
using the correct webpack externals approach.

Usage:
    # A100 80GB (27B model) — recommended
    python scripts/train.py --config configs/a100_80gb.yaml

    # RTX 4090 (9B model) — local fallback
    python scripts/train.py --config configs/qlora_4090.yaml
"""

from unsloth import FastLanguageModel  # must be first — patches trl/transformers/peft

import argparse
import json
import os
from pathlib import Path

import yaml
from datasets import Dataset
from transformers import TrainingArguments
from trl import SFTConfig, SFTTrainer


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_dataset_from_jsonl(path: str) -> Dataset:
    """Load chat-format JSONL into a HuggingFace Dataset."""
    examples = []
    with open(path) as f:
        for line in f:
            examples.append(json.loads(line))
    return Dataset.from_list(examples)


def main():
    parser = argparse.ArgumentParser(description="LoRA fine-tune Qwen 3.5")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/qlora_4090.yaml",
        help="Path to training config YAML",
    )
    args = parser.parse_args()

    # Load config
    project_root = Path(__file__).parent.parent
    config_path = project_root / args.config
    config = load_config(str(config_path))

    model_name = config["model"]["name"]
    max_seq_length = config["model"].get("max_seq_length", 4096)
    load_in_16bit = config["model"].get("load_in_16bit", True)

    print(f"Loading model: {model_name}")

    # Load model with Unsloth (handles hybrid architecture)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        load_in_4bit=not load_in_16bit,
        load_in_16bit=load_in_16bit,
        full_finetuning=False,
    )

    # Apply LoRA
    lora_cfg = config["lora"]
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_cfg["r"],
        target_modules=lora_cfg["target_modules"],
        lora_alpha=lora_cfg["alpha"],
        lora_dropout=lora_cfg["dropout"],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # Load datasets
    data_dir = project_root / "data"
    train_dataset = load_dataset_from_jsonl(str(data_dir / "train.jsonl"))
    val_dataset = load_dataset_from_jsonl(str(data_dir / "val.jsonl"))

    print(f"Training examples: {len(train_dataset)}")
    print(f"Validation examples: {len(val_dataset)}")

    # Training arguments
    train_cfg = config["training"]
    output_dir = str(project_root / config.get("output_dir", "output"))

    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=train_cfg["epochs"],
        per_device_train_batch_size=train_cfg["batch_size"],
        per_device_eval_batch_size=train_cfg["batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        learning_rate=train_cfg["learning_rate"],
        weight_decay=train_cfg["weight_decay"],
        warmup_ratio=train_cfg["warmup_ratio"],
        lr_scheduler_type=train_cfg["lr_scheduler"],
        logging_steps=train_cfg["logging_steps"],
        eval_strategy="steps",
        eval_steps=train_cfg["eval_steps"],
        save_strategy="steps",
        save_steps=train_cfg["save_steps"],
        save_total_limit=train_cfg["save_total_limit"],
        bf16=train_cfg.get("bf16", True),
        fp16=False,
        gradient_checkpointing=train_cfg.get("gradient_checkpointing", True),
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_grad_norm=train_cfg.get("max_grad_norm", 0.3),
        optim=train_cfg.get("optimizer", "paged_adamw_8bit"),
        report_to=train_cfg.get("report_to", "none"),
        dataloader_pin_memory=False,
        remove_unused_columns=False,
        max_seq_length=max_seq_length,
    )

    # Format chat messages into tokenized text
    def formatting_func(examples):
        return [
            tokenizer.apply_chat_template(msgs, tokenize=False)
            for msgs in examples["messages"]
        ]

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        formatting_func=formatting_func,
    )

    # Train
    print("Starting training...")
    trainer.train()

    # Save final adapter
    final_dir = os.path.join(output_dir, "final")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    print(f"Saved final adapter to {final_dir}")


if __name__ == "__main__":
    main()
