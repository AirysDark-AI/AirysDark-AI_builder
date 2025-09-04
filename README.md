# AirysDark-AI — Universal Builder

A universal, self-healing CI system for GitHub Actions.  
It auto-detects your project type, runs builds, and if the build fails, an AI proposes a minimal patch, applies it, re-runs, and opens a PR.

---

## 📦 What’s inside
- `tools/AirysDark-AI_detector.py`  
  Scans your repo (Gradle/Android, CMake, Node, Python, Rust, Dotnet, Maven, Flutter, Go, or unknown) and generates `.github/workflows/AirysDark-AI_<type>.yml` per detection.
- `tools/AirysDark-AI_builder.py`  
  Attempts automatic fixes (OpenAI first if `OPENAI_API_KEY` is set; fallback to local llama.cpp with TinyLlama).
- `.github/workflows/AirysDark-AI_detector.yml`  
  A **bootstrap** workflow you can run to generate the per-type workflows via the detector.
- `.github/workflows/AirysDark-AI_universal.yml`  
  A **reusable** workflow callers can use directly from other repos.
- `examples/caller_workflow.yml`  
  Example caller workflow for other repos.

---

# 🚀 Quick Setup (Copy/Paste)

## 1) Bootstrap generator workflow (creates per-type workflows)
Create: **`.github/workflows/AirysDark-AI_detector.yml`**

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
          branch: ai/airysdark-ai-bootstrap
          title: "AirysDark-AI: bootstrap (multi-purpose)"
          commit-message: "chore: generate AirysDark-AI workflows + script (multi-purpose)"
          body: |
            This PR was created by the bootstrap workflow.
            - Detects project type (android / cmake / node / python / rust / dotnet / maven / flutter / go / unknown)
            - Generates a matching CI workflow with build capture
            - Adds AirysDark-AI autobuilder (OpenAI → llama fallback) and TinyLlama GGUF fetch
          labels: automation, ci
```

✅ What it does:
- Runs the **detector** (`tools/AirysDark-AI_detector.py`)
- Generates `.github/workflows/AirysDark-AI_<type>.yml` based on your project
- Opens a PR with the generated workflows + builder script

🔑 Required repo **secrets**:
- `BOT_TOKEN` — GitHub PAT (with **Contents: write** and **Pull requests: write**)
- *(optional)* `OPENAI_API_KEY` — to use OpenAI before the llama.cpp fallback

👉 Run this from your repo’s **Actions** tab → **AirysDark-AI_detector**.

---

## 2) Reusable autobuilder workflow (use from *other* repos)
Create in your **project repo that wants to use AirysDark-AI**:  
**`.github/workflows/autobuilder.yml`**

```yaml
name: Project Autobuilder (AirysDark-AI Reusable)

on:
  workflow_dispatch:
  push:
  pull_request:

jobs:
  autobuild:
    # 👇 Point this to your published builder repo
    uses: AirysDark/AirysDark-AI_Builder/.github/workflows/AirysDark-AI_universal.yml@main
    secrets: inherit
    with:
      # Project location in THIS repo:
      # "." for root, or a subfolder like "android" / "backend" / "app"
      project_dir: "."

      # Optional: force a specific build command (otherwise auto-detected)
      # build_cmd: "npm ci && npm run build --if-present"
```

### 🔗 How to “point the builder to your repo”
- The `uses:` line tells GitHub to **call the universal workflow** from your published builder repo.  
Examples:
```yaml
uses: AirysDark/AirysDark-AI_Builder/.github/workflows/AirysDark-AI_universal.yml@main
uses: AirysDark/AirysDark-AI_Builder/.github/workflows/AirysDark-AI_universal.yml@v1
uses: AirysDark/AirysDark-AI_Builder/.github/workflows/AirysDark-AI_universal.yml@<commit-sha>
```

- The `project_dir` input tells the builder **where in your repo** the project lives:
  - Root: `project_dir: "."`
  - Subfolder: `project_dir: "android"` or `project_dir: "backend"`

- To override auto-detection, set `build_cmd` explicitly:
```yaml
with:
  project_dir: "backend"
  build_cmd: "pip install -e . && pytest"
```

🔑 Secrets needed in the calling repo:
- `BOT_TOKEN` — PAT with **Contents: write**, **Pull requests: write**
- *(optional)* `OPENAI_API_KEY`

---

## 3) Optional: Using the generated per-type workflows
If you ran the detector, it will generate files like:
- `.github/workflows/AirysDark-AI_python.yml`
- `.github/workflows/AirysDark-AI_cmake.yml`
- `.github/workflows/AirysDark-AI_android.yml`

You can run those directly from Actions too.  
They already trigger `tools/AirysDark-AI_builder.py` on failures and open PRs with the proposed patches.

---

## ✅ Summary
- Run **AirysDark-AI_detector** → generates per-type workflows via PR.
- Use **AirysDark-AI_universal** → reusable workflow for any repo.
- Point `uses:` to your builder repo, and set `project_dir` / `build_cmd` as needed.
- Add `BOT_TOKEN` secret (+ optional `OPENAI_API_KEY`) for automation.
