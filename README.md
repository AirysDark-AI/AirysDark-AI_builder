# AirysDark-AI — Universal Builder

A universal, self-healing CI system for GitHub Actions. It auto-detects your project type, runs builds, and if the build fails, an AI proposes a minimal patch, applies it, re-runs, and opens a PR.

## What’s inside
- `tools/AirysDark-AI_detector.py` — scans your repo (Gradle/Android, CMake, Node, Python, Rust, Dotnet, Maven, Flutter, Go, or unknown) and generates `.github/workflows/AirysDark-AI_<type>.yml` per detection.
- `tools/AirysDark-AI_builder.py` — attempts automatic fixes (OpenAI first if `OPENAI_API_KEY` is set; otherwise falls back to local llama.cpp with TinyLlama).
- `.github/workflows/AirysDark-AI_detector.yml` — a **bootstrap** workflow you can run to generate the per-type workflows via the detector.
- `.github/workflows/AirysDark-AI_universal.yml` — a **reusable** workflow callers can use directly from other repos.
- `examples/caller_workflow.yml` — copy/paste into *another repo* to call the reusable universal workflow here.

## Quick start (this repo)
1. Commit / push these files.
2. Add repo **secrets** (Settings → Secrets and variables → Actions):
   - `BOT_TOKEN` — GitHub PAT (Contents: write, Pull requests: write)
   - `OPENAI_API_KEY` — *(optional)* use OpenAI before llama fallback
3. Run **AirysDark-AI_detector** from Actions. It will open a PR with generated workflows like:
   - `.github/workflows/AirysDark-AI_python.yml`
   - `.github/workflows/AirysDark-AI_cmake.yml`

### Direct the build to a subfolder
If your project is not at repo root, edit the generated workflow and set:
```yaml
jobs:
  build:
    defaults:
      run:
        working-directory: backend   # or android, app, etc.
```

## Use from another repo (reusable workflow)
Add this to the *other* repo’s `.github/workflows/autobuilder.yml`:
```yaml
name: Project Autobuilder (AirysDark-AI Reusable)

on:
  workflow_dispatch:
  push:
  pull_request:

jobs:
  autobuild:
    uses: AirysDark/AirysDark-AI_Builder/.github/workflows/AirysDark-AI_universal.yml@main
    secrets: inherit
    with:
      project_dir: "."        # or "android", "backend", etc.
      # build_cmd: "custom build command (optional)"
```

This will:
- Detect your build system
- Run the build and capture logs
- On failure, run `AirysDark-AI_builder.py` (OpenAI → llama)
- Open a PR with proposed fixes if changes were applied

## Notes
- Llama.cpp and TinyLlama GGUF are cached by the generated workflows for speed.
- Android builds auto-generate a Gradle wrapper if missing (first-run safe).
- You can force local LLM only by omitting `OPENAI_API_KEY` or setting `env: PROVIDER=llama` in the AI step.
