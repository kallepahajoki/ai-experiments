# Ward — Improvement TODO

## Model Training Gaps

### Gate (0.8B) — False Negatives on Hard Cases
- [ ] Subtle cross-tenant data requests (no obvious destructive keywords)
- [ ] Multi-step attacks where individual steps look benign (e.g., nginx routing + external IP)
- [ ] Social engineering without typical injection patterns

### Gate (0.8B) — False Positives on Legitimate Ops
- [ ] Add training examples for safe DevOps operations with "dangerous" keywords:
  - SSL cert rotation on staging/dev
  - Docker cleanup of stopped containers
  - Dropping test/migration databases
  - Authorized pen testing
  - Employee offboarding (deactivate, not delete)
  - Credential rotation after incidents
  - Security audit data exports (own tenant)

### Thinker (4B) — Reasoning Quality
- [ ] Buried injections in long documents (procurement email failed — likely sequence length truncation at 768 tokens)
- [ ] Distinguish legitimate tool calls from injected tool calls (Atlas ingestion with vs without hidden HTML comment)
- [ ] Multi-step exfiltration patterns (internal routing mixed with external IP forwarding)
- [ ] Phishing content generation even with claimed "training" context

### Training Data Generation
- [ ] Write new hard cases (both SAFE and UNSAFE) targeting gaps above
- [ ] Generate thinking chains via Gemini Flash (OpenRouter, ~$0.0002/example)
- [ ] Consider increasing thinker max_seq_length beyond 768 for long documents
- [ ] Experiment with UNSAFE oversampling ratio for gate (currently 2x)

## Eval Improvements
- [ ] Track hard eval (eval_hard.jsonl) separately from standard eval
- [ ] Add two-stage pipeline eval: gate → thinker end-to-end accuracy
- [ ] Measure "overturn rate" and "correct overturn rate" on combined eval sets

## Deployment
- [x] Gate GGUF converted and deployed to Ollama as anvil-ward-gate-q4
- [ ] Thinker GGUF conversion and Ollama deployment as anvil-ward-thinker
- [x] Two-stage Probe integration (ward.ts + UI)
