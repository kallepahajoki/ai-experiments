#!/usr/bin/env python3
"""
Evaluation script for the fine-tuned model.

Tests whether the model can produce a correct next.config.js fix
for the ai-toolkit/forge build error.

Evaluation criteria:
1. Build passes after applying the model's fix
2. Uses webpack externals (not resolve.fallback)
3. Includes transitive dependencies (pg, pgpass, split2)

Usage:
    # Test with base model
    python eval/eval_on_project.py --model Qwen/Qwen3.5-27B

    # Test with fine-tuned adapter
    python eval/eval_on_project.py --model Qwen/Qwen3.5-27B --adapter output/final

    # Test with local Ollama model
    python eval/eval_on_project.py --ollama --model qwen3.5:27b

    # Skip build test (just check output quality)
    python eval/eval_on_project.py --no-build --model Qwen/Qwen3.5-27B
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# The prompt we'll send to the model (same format as training data)
SYSTEM_PROMPT = """You are an expert software engineer. When given a coding task, analyze the problem carefully, explain your reasoning, then provide the fix. Focus on correctness - use the right mechanism for the problem, not just something that silences the error."""

# Loaded from the real project
EVAL_PROMPT = None  # Set in main()


def load_eval_prompt() -> str:
    """Build the evaluation prompt from the real project files."""
    project_root = Path(__file__).parent.parent
    context_file = project_root / "data" / "real_project_context.json"

    with open(context_file) as f:
        ctx = json.load(f)

    build_error = """  ▲ Next.js 14.2.15
  - Environments: .env.local
  - Experiments (use with caution):
    · instrumentationHook

   Creating an optimized production build ...
Failed to compile.

./lib/calendar/caldav.ts:9:1
Module not found: Can't resolve 'crypto'
  7 | import { createDAVClient, DAVClient, DAVCalendar, DAVCalendarObject } from 'tsdav';
  8 | import ICAL from 'ical.js';
> 9 | import { randomUUID } from 'crypto';
    | ^
 10 | import { CalendarProvider, CalendarEvent, FreeBusyQuery } from './types';

Import trace for requested module:
./lib/calendar/unified.ts
./lib/signal/router.ts
./instrumentation.ts

./lib/calendar/token-store.ts:12:1
Module not found: Can't resolve 'crypto'
 10 | */
 11 |
> 12 | import {
    | ^
 13 |   createCipheriv,
 14 |   createDecipheriv,
 15 |   randomBytes,

Import trace for requested module:
./lib/calendar/unified.ts
./lib/signal/router.ts
./instrumentation.ts

./lib/signal/adapter.ts:1:1
Module not found: Can't resolve 'net'
> 1 | import { createConnection, connect, Socket } from 'net';
    | ^
  2 | import { EventEmitter } from 'events';

Import trace for requested module:
./instrumentation.ts

./lib/signal/clients.ts:9:1
Module not found: Can't resolve 'fs/promises'
> 9 | import fs from 'fs/promises';
    | ^
 10 | import path from 'path';

Import trace for requested module:
./lib/signal/router.ts
./instrumentation.ts

./lib/signal/clients.ts:10:1
Module not found: Can't resolve 'path'
  9 | import fs from 'fs/promises';
> 10 | import path from 'path';
    | ^

Import trace for requested module:
./lib/signal/router.ts
./instrumentation.ts

> Build failed because of webpack errors"""

    return f"""I'm getting build errors in my Next.js project. The project uses an instrumentation hook to start a Signal messenger adapter as a background process. The signal adapter and calendar integration use Node.js built-in modules.

Here's the output of `npm run build`:

```
{build_error}
```

Here's my current next.config.js:
```javascript
{ctx['files']['next.config.js']}
```

Here's the instrumentation.ts that's in the import trace:
```typescript
{ctx['files']['instrumentation.ts']}
```

The project also has `pg` (PostgreSQL) as a dependency, used in `lib/calendar/token-store.ts` for encrypted credential storage. The `token-store.ts` imports both `crypto` and `pg`.

How do I fix the build error?"""


def score_response(response: str) -> dict:
    """Score the model's response for correctness."""
    scores = {
        "uses_externals": False,
        "avoids_fallback": True,
        "includes_crypto": False,
        "includes_net": False,
        "includes_fs": False,
        "includes_path": False,
        "includes_events": False,
        "includes_pg": False,
        "includes_pgpass": False,
        "includes_split2": False,
        "checks_isServer": False,
        "spreads_existing": False,
    }

    lower = response.lower()

    # Check for externals (correct approach)
    if "config.externals" in response or "externals:" in response:
        scores["uses_externals"] = True

    # Check for fallback (wrong approach)
    if "resolve.fallback" in response or "fallback:" in lower:
        # If it's mentioned as wrong, that's ok
        if "don't" in lower or "incorrect" in lower or "wrong" in lower or "avoid" in lower:
            scores["avoids_fallback"] = True
        else:
            scores["avoids_fallback"] = False

    # Check for required modules
    for module, key in [
        ("crypto", "includes_crypto"),
        ("net", "includes_net"),
        ("fs", "includes_fs"),
        ("path", "includes_path"),
        ("events", "includes_events"),
        ("pg", "includes_pg"),
        ("pgpass", "includes_pgpass"),
        ("split2", "includes_split2"),
    ]:
        # Look for the module in a string context (quoted)
        if f"'{module}'" in response or f'"{module}"' in response:
            scores[key] = True

    # Check for isServer guard
    if "isServer" in response:
        scores["checks_isServer"] = True

    # Check for spreading existing externals
    if "...(config.externals" in response or "...config.externals" in response:
        scores["spreads_existing"] = True

    # Calculate overall score
    total = sum(1 for v in scores.values() if v)
    max_score = len(scores)
    scores["total"] = total
    scores["max"] = max_score
    scores["percentage"] = round(total / max_score * 100, 1)

    # Critical pass/fail
    scores["critical_pass"] = (
        scores["uses_externals"]
        and scores["avoids_fallback"]
        and scores["checks_isServer"]
        and scores["includes_pg"]
    )

    return scores


def extract_config_from_response(response: str) -> str | None:
    """Try to extract a next.config.js code block from the response."""
    # Look for javascript code blocks
    pattern = r"```(?:javascript|js)?\s*\n(.*?)```"
    matches = re.findall(pattern, response, re.DOTALL)

    for match in matches:
        if "nextConfig" in match or "module.exports" in match or "export default" in match:
            return match.strip()

    return None


def test_build(config_content: str, project_path: str) -> dict:
    """Apply the config and run npm run build to test if it passes."""
    config_path = os.path.join(project_path, "forge", "next.config.js")
    config_mjs_path = os.path.join(project_path, "forge", "next.config.mjs")

    # Backup original
    backup_path = config_path + ".backup"
    backup_mjs_path = config_mjs_path + ".backup" if os.path.exists(config_mjs_path) else None

    try:
        if os.path.exists(config_path):
            shutil.copy2(config_path, backup_path)
        if backup_mjs_path:
            shutil.copy2(config_mjs_path, backup_mjs_path)

        # Write the model's config
        # Determine if it's ESM or CJS
        if "export default" in config_content:
            target = config_mjs_path
            # Remove .js version if exists
            if os.path.exists(config_path):
                os.rename(config_path, config_path + ".disabled")
        else:
            target = config_path
            # Remove .mjs version if exists
            if os.path.exists(config_mjs_path):
                os.rename(config_mjs_path, config_mjs_path + ".disabled")

        with open(target, "w") as f:
            f.write(config_content)

        # Run the build
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=os.path.join(project_path, "forge"),
            capture_output=True,
            text=True,
            timeout=120,
        )

        return {
            "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }

    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "passed": False, "stdout": "", "stderr": "Build timed out"}
    except Exception as e:
        return {"exit_code": -1, "passed": False, "stdout": "", "stderr": str(e)}
    finally:
        # Restore originals
        if os.path.exists(backup_path):
            shutil.move(backup_path, config_path)
        if backup_mjs_path and os.path.exists(backup_mjs_path):
            shutil.move(backup_mjs_path, config_mjs_path)
        # Restore any .disabled files
        for p in [config_path + ".disabled", config_mjs_path + ".disabled"]:
            if os.path.exists(p):
                shutil.move(p, p.replace(".disabled", ""))


def run_inference_ollama(model: str, prompt: str, system: str) -> str:
    """Run inference via Ollama API."""
    import urllib.request

    url = os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/api/chat"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 4096},
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
        return data["message"]["content"]


def run_inference_transformers(model_name: str, adapter_path: str | None, prompt: str, system: str) -> str:
    """Run inference via Unsloth + peft."""
    import torch
    from unsloth import FastLanguageModel
    from peft import PeftModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=4096,
        load_in_4bit=False,
        load_in_16bit=True,
        full_finetuning=False,
    )

    if adapter_path:
        print(f"Loading LoRA adapter from {adapter_path}")
        model = PeftModel.from_pretrained(model, adapter_path)

    FastLanguageModel.for_inference(model)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    input_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors="pt").to(model.device)
    inputs = {"input_ids": input_ids}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=4096,
            temperature=0.1,
            do_sample=True,
            top_p=0.95,
        )

    # Decode only the new tokens
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def main():
    parser = argparse.ArgumentParser(description="Evaluate model on Next.js server boundary fix")
    parser.add_argument("--model", type=str, required=True, help="Model name (HF or Ollama)")
    parser.add_argument("--adapter", type=str, default=None, help="Path to LoRA adapter (for HF models)")
    parser.add_argument("--ollama", action="store_true", help="Use Ollama for inference")
    parser.add_argument("--no-build", action="store_true", help="Skip the actual build test")
    parser.add_argument("--project-path", type=str, default=None,
                        help="Path to ai-toolkit project (default: ../ai-toolkit relative to this repo)")
    parser.add_argument("--response-file", type=str, default=None,
                        help="Read response from file instead of running inference")
    parser.add_argument("--save-response", type=str, default=None,
                        help="Save model response to file")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    eval_prompt = load_eval_prompt()

    print("=" * 60)
    print("Next.js Server Boundary Fix - Model Evaluation")
    print("=" * 60)
    print(f"Model: {args.model}")
    if args.adapter:
        print(f"Adapter: {args.adapter}")
    print()

    # Get model response
    if args.response_file:
        print(f"Loading response from {args.response_file}")
        with open(args.response_file) as f:
            response = f.read()
    elif args.ollama:
        print("Running inference via Ollama...")
        response = run_inference_ollama(args.model, eval_prompt, SYSTEM_PROMPT)
    else:
        print("Running inference via transformers...")
        response = run_inference_transformers(args.model, args.adapter, eval_prompt, SYSTEM_PROMPT)

    if args.save_response:
        with open(args.save_response, "w") as f:
            f.write(response)
        print(f"Saved response to {args.save_response}")

    print("\n" + "=" * 60)
    print("MODEL RESPONSE:")
    print("=" * 60)
    print(response[:3000])
    if len(response) > 3000:
        print(f"\n... ({len(response) - 3000} more characters)")

    # Score the response
    print("\n" + "=" * 60)
    print("SCORING:")
    print("=" * 60)
    scores = score_response(response)

    for key, value in scores.items():
        if key in ("total", "max", "percentage", "critical_pass"):
            continue
        status = "PASS" if value else "FAIL"
        print(f"  {status:4s}  {key}")

    print(f"\n  Score: {scores['total']}/{scores['max']} ({scores['percentage']}%)")
    print(f"  Critical pass: {'YES' if scores['critical_pass'] else 'NO'}")

    # Try to extract and test the config
    config = extract_config_from_response(response)
    if config:
        print(f"\n  Extracted config ({len(config)} chars)")

        if not args.no_build:
            project_path = args.project_path
            if not project_path:
                project_path = str(project_root.parent / "ai-toolkit")

            if os.path.exists(os.path.join(project_path, "forge", "package.json")):
                print("\n" + "=" * 60)
                print("BUILD TEST:")
                print("=" * 60)
                build_result = test_build(config, project_path)
                print(f"  Build {'PASSED' if build_result['passed'] else 'FAILED'}")
                if not build_result["passed"]:
                    # Show relevant error
                    output = build_result["stderr"] or build_result["stdout"]
                    error_lines = [l for l in output.split("\n") if "error" in l.lower() or "Module not found" in l]
                    for line in error_lines[:5]:
                        print(f"    {line.strip()}")
                scores["build_passed"] = build_result["passed"]
            else:
                print(f"\n  Skipping build test: project not found at {project_path}")
    else:
        print("\n  Could not extract next.config.js from response")

    # Write results
    results_dir = project_root / "eval" / "results"
    results_dir.mkdir(exist_ok=True)

    model_slug = args.model.replace("/", "_").replace(":", "_")
    adapter_slug = "_finetuned" if args.adapter else "_base"
    results_file = results_dir / f"{model_slug}{adapter_slug}.json"

    with open(results_file, "w") as f:
        json.dump({
            "model": args.model,
            "adapter": args.adapter,
            "scores": scores,
            "response_length": len(response),
        }, f, indent=2)

    print(f"\n  Results saved to {results_file}")

    # Exit code based on critical pass
    sys.exit(0 if scores["critical_pass"] else 1)


if __name__ == "__main__":
    main()
