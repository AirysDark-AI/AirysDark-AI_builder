# AirysDark-AI — Universal Builder

A universal, self-healing CI system for GitHub Actions.  
It auto-detects your project type, runs builds, and if the build fails, an AI proposes a minimal patch, applies it, re-runs, and opens a PR.

---

## 📂 Repo structure (starter)
```
AirysDark-AI_Builder/
├── tools/
│   ├── AirysDark-AI_builder.py        # AI auto-fix script (stub in this starter; replace with your real script)
│   └── AirysDark-AI_detector.py       # Detector + workflow generator (stub in this starter; replace with your real script)
├── .github/
│   └── workflows/
│       ├── AirysDark-AI_detector.yml  # Bootstrap generator workflow
│       └── AirysDark-AI_universal.yml # Universal reusable workflow
├── examples/
│   └── caller_workflow.yml            # Example caller workflow for other repos
└── README.md
```

> **Note:** The two scripts in `tools/` here are **stubs** so you can push and wire up CI immediately. Replace them with your actual scripts when ready.

---

## 🔑 Required GitHub Secrets (repo → Settings → Secrets and variables → Actions)
- `BOT_TOKEN` → a GitHub Personal Access Token (PAT) with:
  - `contents: write`
  - `pull_requests: write`
- *(optional)* `OPENAI_API_KEY` → to try OpenAI before the llama.cpp fallback (improves quality/speed).

---

## 🚀 Quick Setup

### 1) Run the bootstrap workflow (generates per-type workflows via PR)
Create: **.github/workflows/AirysDark-AI_detector.yml** (already included)

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

Run from **Actions → AirysDark-AI_detector**. It will open a PR with the generated workflows once your real detector is in place.

---

### 2) Reusable autobuilder for any project repo
Create in the *project* repo: **.github/workflows/autobuilder.yml** (example also in `examples/`)

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
      project_dir: "."     # "." for repo root, or "android"/"backend"/"app" for subfolder
      # build_cmd: "npm ci && npm run build --if-present"   # optional override
```

**Pointing the AI to your repo**  
- The `uses:` line references the **universal workflow in this repo**.  
  - Branch: `@main`
  - Tag: `@v1`
  - Commit SHA: `@<commit-sha>`
- The `project_dir` input tells the workflow where in the caller repo the project lives.
- Set `build_cmd` if you want to override auto-detection.

**Secrets in the *calling* repo:**  
- `BOT_TOKEN` (+ optional `OPENAI_API_KEY`).

---

## 3) Full code: `.github/workflows/AirysDark-AI_universal.yml`

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

## 4) Stubs you should replace (when ready)

**tools/AirysDark-AI_builder.py**
```python
#!/usr/bin/env python3
print("AirysDark-AI_builder.py (stub): replace this with your real AI builder script.")
exit(0)
```

**tools/AirysDark-AI_detector.py**
```python
#!/usr/bin/env python3
print("AirysDark-AI_detector.py (stub): replace this with your real detector/generator script.")
exit(0)
```

> After replacing the stubs with your real scripts, the workflows will build and the AI fix step will run.

---

## ✅ Summary
- Add `BOT_TOKEN` (+ optional `OPENAI_API_KEY`) as secrets.
- Run **AirysDark-AI_detector** to generate per-type workflows via PR.
- Use **AirysDark-AI_universal** from other repos with `uses:` + `project_dir`.
- Replace the two **stub** scripts in `tools/` with your actual implementations.
