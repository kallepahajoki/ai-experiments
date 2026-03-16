#!/usr/bin/env python3
"""
LoRA finetune Qwen 3.5 for Finnish NER using Unsloth.

Targets: qwen3.5:0.8b, qwen3.5:2b, qwen3.5:4b, qwen3.5:9b
Hardware: RTX 4090 (24GB VRAM), QLoRA 4-bit

Usage:
    python train.py --model 0.8b --epochs 3
    python train.py --model 4b --epochs 2
    python train.py --model 0.8b --epochs 3 --resume          # resume from checkpoint
    python train.py --model 0.8b --epochs 3 --time-limit 6    # stop after 6 hours
"""

import argparse
import time
from pathlib import Path

from transformers import TrainerCallback

MODEL_MAP = {
    "0.8b": "Qwen/Qwen3.5-0.8B",
    "2b":   "Qwen/Qwen3.5-2B",
    "4b":   "Qwen/Qwen3.5-4B",
    "9b":   "Qwen/Qwen3.5-9B",
}

BATCH_SIZE_MAP = {
    "0.8b": 16,
    "2b":   4,
    "4b":   2,
    "9b":   1,
}


def fmt_duration(seconds: float) -> str:
    """Format seconds as e.g. '2h 13m' or '45m 12s'."""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


class ProgressCallback(TrainerCallback):
    """Print progress, ETA, and speed every N steps."""

    def __init__(self, print_every: int = 50):
        self.print_every = print_every
        self.start_time = None
        self.start_step = 0

    def on_train_begin(self, args, state, control, **kwargs):
        self.start_time = time.time()
        self.start_step = state.global_step  # non-zero when resuming

    def on_step_end(self, args, state, control, **kwargs):
        step = state.global_step
        total = state.max_steps
        if step % self.print_every != 0 or self.start_time is None:
            return

        elapsed = time.time() - self.start_time
        steps_done = step - self.start_step
        if steps_done <= 0:
            return

        steps_remaining = total - step
        speed = steps_done / elapsed
        eta_seconds = steps_remaining / speed
        pct = step / total * 100
        epoch = state.epoch or 0

        print(f"[{pct:5.1f}%] Step {step}/{total} | "
              f"Epoch {epoch:.1f} | "
              f"{speed:.2f} step/s | "
              f"Elapsed {fmt_duration(elapsed)} | "
              f"ETA {fmt_duration(eta_seconds)}")


class TimeLimitCallback(TrainerCallback):
    """Stop training after a time budget (hours). Saves checkpoint before stopping."""

    def __init__(self, max_hours: float):
        self.max_seconds = max_hours * 3600
        self.start_time = time.time()

    def on_step_end(self, args, state, control, **kwargs):
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_seconds:
            print(f"\n⏰ Time limit reached ({self.max_seconds/3600:.1f}h). "
                  f"Saving checkpoint and stopping. Resume with --resume.")
            control.should_save = True
            control.should_training_stop = True
        return control


def main():
    parser = argparse.ArgumentParser(description="Finetune Qwen for Finnish NER")
    parser.add_argument("--model", choices=["0.8b", "2b", "4b", "9b"], required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--resume", action="store_true",
                        help="Resume training from latest checkpoint")
    parser.add_argument("--time-limit", type=float, default=None,
                        help="Stop training after this many hours (saves checkpoint)")
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

    callbacks = [ProgressCallback(print_every=50)]
    if args.time_limit is not None:
        callbacks.append(TimeLimitCallback(args.time_limit))

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"].select(range(min(2000, len(dataset["eval"])))),
        args=SFTConfig(
            output_dir=str(output_path),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=BATCH_SIZE_MAP[args.model],
            gradient_accumulation_steps=4,
            warmup_steps=50,
            learning_rate=args.learning_rate,
            logging_steps=25,
            eval_strategy="steps",
            eval_steps=500,
            save_strategy="steps",
            save_steps=500,
            save_total_limit=3,
            fp16=False,
            bf16=True,
            max_seq_length=args.max_seq_length,
            packing=True,
            dataset_text_field="text",
        ),
        callbacks=callbacks,
    )

    # ── Find checkpoint if resuming ──
    resume_checkpoint = None
    if args.resume:
        # Check if adapter already exists (training completed previously)
        adapter_path = output_path / "adapter"
        if adapter_path.exists():
            print(f"✅ Training already complete — adapter exists at {adapter_path}")
            print("Delete it if you want to retrain.")
            return

        checkpoints = sorted(output_path.glob("checkpoint-*"),
                             key=lambda p: int(p.name.split("-")[-1]))
        if checkpoints:
            resume_checkpoint = str(checkpoints[-1])
            print(f"Resuming from {resume_checkpoint}")
        else:
            print("No checkpoint found, starting from scratch")

    print("Starting training...")
    result = trainer.train(resume_from_checkpoint=resume_checkpoint)

    # ── Check if training completed all epochs ──
    total_steps = trainer.state.max_steps
    completed_steps = trainer.state.global_step
    training_complete = completed_steps >= total_steps

    if training_complete:
        print(f"\n✅ Training complete ({completed_steps}/{total_steps} steps, "
              f"{args.epochs} epochs). No need to resume.")
        # Save adapter only when fully done
        adapter_path = output_path / "adapter"
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        print(f"Adapter saved to {adapter_path}")
    else:
        print(f"\n⏸️  Training paused at step {completed_steps}/{total_steps}. "
              f"Run with --resume to continue.")


if __name__ == "__main__":
    main()
