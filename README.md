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

---

## 3) Full code: `AirysDark-AI_universal.yml`

This is the reusable workflow that other repos call with `uses:`:

```yaml
name: AirysDark-AI — Universal (reusable)

on:
  workflow_dispatch:
  push:
  pull_request:
  workflow_call:
    inputs:
      project_dir:
        description: "Subdirectory of the project to build ('.' by default)"
        required: false
        type: string
        default: "."
      build_cmd:
        description: "Override build command (optional)"
        required: false
        type: string

permissions:
  contents: write
  pull-requests: write

jobs:
  universal:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install requests

      - name: Detect & choose build command
        id: buildcmd
        run: |
          set -euo pipefail
          cd "${{ inputs.project_dir }}"
          if [ -n "${{ inputs.build_cmd }}" ]; then
            CMD="${{ inputs.build_cmd }}"
          else
            if [ -f "gradlew" ] || ls **/build.gradle* **/settings.gradle* >/dev/null 2>&1; then
              chmod +x gradlew || true
              CMD="./gradlew assembleDebug --stacktrace"
            elif [ -f "CMakeLists.txt" ] || ls **/CMakeLists.txt >/dev/null 2>&1; then
              CMD="cmake -S . -B build && cmake --build build -j"
            elif [ -f "package.json" ]; then
              CMD="npm ci && npm run build --if-present"
            elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
              CMD="pip install -e . && pytest || python -m pytest"
            elif [ -f "Cargo.toml" ]; then
              CMD="cargo build --locked --all-targets --verbose"
            elif ls *.sln **/*.csproj **/*.fsproj >/dev/null 2>&1; then
              CMD="dotnet restore && dotnet build -c Release"
            elif [ -f "pom.xml" ]; then
              CMD="mvn -B package --file pom.xml"
            elif [ -f "pubspec.yaml" ]; then
              CMD="flutter build apk --debug"
            elif [ -f "go.mod" ]; then
              CMD="go build ./..."
            else
              CMD="echo 'No build system detected' && exit 1"
            fi
          fi
          echo "BUILD_CMD=cd $PWD && $CMD" >> "$GITHUB_OUTPUT"
          echo "Using: $CMD"

      - name: Build (capture)
        id: build
        run: |
          set -euxo pipefail
          CMD="${{ steps.buildcmd.outputs.BUILD_CMD }}"
          set +e; bash -lc "$CMD" | tee build.log; EXIT=$?; set -e
          echo "EXIT_CODE=$EXIT" >> "$GITHUB_OUTPUT"
          [ -s build.log ] || echo "(no build output captured)" > build.log
          exit 0
        continue-on-error: true

      - name: Attempt AI auto-fix (OpenAI → llama fallback)
        if: always() && steps.build.outputs.EXIT_CODE != '0'
        env:
          PROVIDER: openai
          FALLBACK_PROVIDER: llama
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}
          MODEL_PATH: models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
          AI_BUILDER_ATTEMPTS: "3"
          BUILD_CMD: ${{ steps.buildcmd.outputs.BUILD_CMD }}
        run: python3 tools/AirysDark-AI_builder.py || true
```

---

## ✅ Summary
- Run **AirysDark-AI_detector** → generates per-type workflows via PR.  
- Use **AirysDark-AI_universal** → reusable workflow for any repo.  
- Point `uses:` to your builder repo, and set `project_dir` / `build_cmd` as needed.  
- Add `BOT_TOKEN` secret (+ optional `OPENAI_API_KEY`) for automation.
