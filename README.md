# AirysDark-AI — Universal Builder

## Overview
**AirysDark-AI Builder** is a **universal AI autobuilder** for GitHub Actions.

- Detects the build system automatically (`Android/Gradle`, `CMake`, `Node`, `Python`, `Rust`, `Dotnet`, `Maven`, `Flutter`, `Go`, or fallback `unknown`).
- Generates per-project workflows (`.github/workflows/AirysDark-AI_<type>.yml`).
- Each workflow:
  - Runs the build
  - Captures `build.log`
  - On failure, runs **AI fix attempts**:
    - OpenAI (if `OPENAI_API_KEY` is set)
    - Fallback to **llama.cpp + TinyLlama GGUF**
  - Applies patches, retries build
  - Uploads logs + patches
  - Opens a PR if changes succeed

This is a **multi-purpose, self-healing CI system**.

---

## Step 1: Add the detector script
Commit `tools/AirysDark-AI_detector.py` from this package to your repo.

---

## Step 2: Add the bootstrap workflow
Create this file in your repo: `.github/workflows/AirysDark-AI_detector.yml`

```yaml
name: AirysDark-AI_detector

on:
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  bootstrap:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: pip install requests pyyaml

      - name: Generate workflows + autobuilder script
        run: python3 tools/AirysDark-AI_detector.py

      - name: Create PR with generated workflows
        uses: peter-evans/create-pull-request@v6
        with:
          branch: ai/autobuilder-bootstrap
          title: "AI Autobuilder: bootstrap (multi-purpose)"
          commit-message: "chore: generate AI autobuilder workflows + script (multi-purpose)"
          body: |
            This PR was created by the bootstrap workflow.
            - Detects project type (android / cmake / node / python / rust / dotnet / maven / flutter / go / unknown)
            - Generates a matching CI workflow with build capture
            - Adds AI autobuilder (OpenAI → llama fallback) and TinyLlama GGUF fetch
          labels: automation, ci
```

---

## Step 3: Run the detector
- Go to the **Actions** tab in your repo.
- Run **AirysDark-AI_detector** (workflow_dispatch).
- It will generate one or more files in `.github/workflows/`, for example:
  - `AirysDark-AI_python.yml`
  - `AirysDark-AI_cmake.yml`
- The job will open a **PR** with the generated workflows + builder script.

---

## Step 4: Direct it to your project
By default, the detector assumes the project is in the **repo root**.

If your build files live in a subdirectory (e.g. `backend/` or `android/`), edit the generated workflow and set:

```yaml
jobs:
  build:
    defaults:
      run:
        working-directory: backend
```

This ensures all commands run inside that folder.

---

## Step 5: Add secrets
In your repo → Settings → Secrets and variables → Actions:

- `BOT_TOKEN` → a GitHub PAT (from a bot account or your own) with:
  - **Contents: write**
  - **Pull requests: write**
- `OPENAI_API_KEY` → optional, improves AI quality vs TinyLlama fallback

---

## Done!
Now you have **self-healing CI**: whenever a build fails, the AI attempts fixes, commits patches, and opens PRs.
