# AirysDark-AI — Polished Detector Workflows

This update improves the detector-generated workflows with:
- `workflow_call` (so other repos can reuse them)
- First-run safety for Android (auto-generate Gradle wrapper if missing)
- Caching:
  - Gradle caches
  - llama.cpp build cache
  - TinyLlama GGUF model cache
- Slightly higher AI attempt count and larger log tails

**Usage**
1) Commit `tools/AirysDark-AI_detector.py`.
2) Run the bootstrap workflow that calls it (or run the script locally).
3) It will generate `.github/workflows/AirysDark-AI_<type>.yml` per detected type.

Secrets needed in the repo (for the generated workflows):
- `BOT_TOKEN` (bot PAT: Contents write, Pull requests write)
- optional `OPENAI_API_KEY` (OpenAI first; fallback to llama.cpp)
