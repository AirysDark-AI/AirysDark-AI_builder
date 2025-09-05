# 🤖 AirysDark-AI Build Automation

**Self-adapting GitHub Actions pipeline** that detects, probes, builds, and fixes projects — automatically.

Targets supported: **Android, Linux, CMake, Node, Python, Rust, .NET, Maven, Flutter, Go, Bazel, SCons, Ninja**.

<p align="center">
  <a href="../../actions/workflows/AirysDark-AI_detector.yml">
    <img alt="Detector status" src="https://img.shields.io/github/actions/workflow/status/AirysDark/${REPO}/AirysDark-AI_detector.yml?label=Detector">
  </a>
  <a href="../../actions/workflows/AirysDark-AI_prob.yml">
    <img alt="Probe status" src="https://img.shields.io/github/actions/workflow/status/AirysDark/${REPO}/AirysDark-AI_prob.yml?label=Probe">
  </a>
  <a href="../../actions/workflows/AirysDark-AI_build.yml">
    <img alt="Build status" src="https://img.shields.io/github/actions/workflow/status/AirysDark/${REPO}/AirysDark-AI_build.yml?label=Build">
  </a>
  <a href="../../actions/workflows/AirysDark-AI_android.yml">
    <img alt="Android status" src="https://img.shields.io/github/actions/workflow/status/AirysDark/${REPO}/AirysDark-AI_android.yml?label=Android">
  </a>
</p>

> Replace `${OWNER}` and `${REPO}` above (or remove the badges).

---

## ✨ What you get

- **Detector (Step 1)**  
  Deep-scans the repo (all subfolders + file contents) to identify build systems.  
  Writes:
  - `tools/airysdark_ai_scan.json` (types + evidence + folder hints)
  - `pr_body_detect.md` (PR summary)
  - `.github/workflows/AirysDark-AI_prob.yml` (**single** manual-run probe workflow)

- **Probe (Step 2)**  
  Reads the scan, explores the repo, proposes a build command, and drafts a build workflow.  
  - For **Android**, generates `AirysDark-AI_android.yml` (self-contained loop)  
  - For others, generates `AirysDark-AI_build.yml` (generic build + AI fixer)

- **Build (Step 3)**  
  Runs the drafted workflow, captures logs, uploads artifacts.  
  On failure, compiles **llama.cpp** and runs **TinyLlama GGUF** to help `AirysDark-AI_builder.py` suggest minimal fixes and **opens a PR** with the patch.

- **Android special path**  
  Self-contained loop `tools/AirysDark-AI_android.py` (no external fetch during Android run).  
  You can **toggle** logic:
  ```yaml
  env:
    ANDROID_LOGIC: "on"   # "on" = android.py loop; "off" = generic builder.py fallback
  ```

- **Secure tokens**  
  - `BOT_TOKEN` → opens PRs (fine-grained PAT recommended)  
  - `KB_PUSH_TOKEN` → (optional) push “knowledge base” logs/collections to your repo  
  - Separation reduces risk of mass revocations.

---

## 🚀 Quickstart

### 0) Secrets & variables

In your repo **Settings → Secrets and variables → Actions**:

- **Secrets**
  - `BOT_TOKEN` → Fine-grained PAT, repo content: read/write, pull requests: read/write (PR creation)
  - `KB_PUSH_TOKEN` → Fine-grained PAT, repo content: read/write (KB pushes; optional)
  - `OPENAI_API_KEY` → (optional) lets probe draft workflows with OpenAI

- **Variables** (optional)
  - `OPENAI_MODEL` → e.g. `gpt-4o-mini`

> Fine-grained PAT scopes: **Repository permissions** → Contents: Read/Write, Pull requests: Read/Write.

---

### 1) Add the bootstrap detector workflow

Create **`.github/workflows/AirysDark-AI_detector.yml`**:

```yaml
name: AirysDark-AI - Detector (bootstrap)

on:
  workflow_dispatch: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  detect:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout (no credentials)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # IMPORTANT: Only the detector fetches tools.tar
      - name: Fetch tools.tar (ONLY here)
        run: |
          set -euxo pipefail
          mkdir -p tools
          curl -fL "https://raw.githubusercontent.com/AirysDark-AI/AirysDark-AI_builder/main/tools/tools.tar" -o /tmp/tools.tar
          tar -xvf /tmp/tools.tar -C tools
          ls -la tools

      - name: Run detector (generates PROB yml + logs)
        run: |
          set -euxo pipefail
          python3 tools/AirysDark-AI_detector.py

      - name: Build PR body
        run: |
          set -euxo pipefail
          echo "### AirysDark-AI: detector results" > pr_body.md
          echo "" >> pr_body.md
          if [ -f tools/airysdark_ai_scan.json ]; then
            echo "**Detected build types:**" >> pr_body.md
            python3 - <<'PY' >> pr_body.md
import json, sys
from pathlib import Path
p = Path("tools/airysdark_ai_scan.json")
j = json.loads(p.read_text(errors="ignore")) if p.exists() else {}
for t in j.get("types", []):
    print(f"- {t}")
PY
          else
            echo "_No scan JSON found._" >> pr_body.md
          fi
          echo "" >> pr_body.md
          echo "**Next steps:**" >> pr_body.md
          echo "1. Edit \`.github/workflows/AirysDark-AI_prob.yml\` and set **env.TARGET** (e.g. \`android\`, \`linux\`, \`cmake\`)." >> pr_body.md
          echo "2. Merge this PR." >> pr_body.md
          echo "3. From Actions, manually run **AirysDark-AI - Probe (LLM builds workflow)**." >> pr_body.md

      - name: Stage detector outputs
        id: diff
        run: |
          set -euxo pipefail
          git add -A
          if git diff --cached --quiet; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Open PR with PROB workflow
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.BOT_TOKEN }}
          branch: ai/airysdark-ai-prob
          commit-message: "chore: add AirysDark-AI_prob.yml + tools (bootstrap)"
          title: "AirysDark-AI: add single PROB workflow + tools"
          body-path: pr_body.md
          labels: automation, ci
```

> **Reminder:** Only the detector downloads `tools.tar`. All later workflows assume `tools/` is present in the repo.

---

### 2) Configure & run the Probe

After the Detector PR is open:

1. Edit **`.github/workflows/AirysDark-AI_prob.yml`** → set the target:
   ```yaml
   env:
     TARGET: "android"  # or linux, cmake, node, python, rust, dotnet, maven, flutter, go
   ```
2. Merge the PR from Step 1.
3. In **Actions**, run:
   ```
   AirysDark-AI - Probe (LLM builds workflow)
   ```
   The probe writes:
   - Non-Android: `.github/workflows/AirysDark-AI_build.yml`
   - Android: `.github/workflows/AirysDark-AI_android.yml`
   and opens a PR with details.

---

### 3) Run the Build (or Android) workflow

- Merge the Probe PR.  
- From Actions, run:
  - `AirysDark-AI - Build (<target>)` **or**
  - `AirysDark-AI - Android (generated)`
- On failure:
  - Generic path: compiles **llama.cpp**, downloads **TinyLlama GGUF**, runs `AirysDark-AI_builder.py`, and opens a PR if it patched files.
  - Android path: runs the **self-contained loop** in `AirysDark-AI_android.py` (append-only logs, iterative updates).

---

## 🧩 Android logic toggle

Inside `.github/workflows/AirysDark-AI_android.yml` you can switch the fix strategy:

```yaml
env:
  ANDROID_LOGIC: "on"  # "on" = use tools/AirysDark-AI_android.py (self-contained loop)
                       # "off" = disable android.py loop & allow generic builder.py fallback (not recommended)
```

When `ANDROID_LOGIC: "on"`:
- `AirysDark-AI_android.py` runs exclusively.  
- **Do not** invoke `AirysDark-AI_builder.py` in the same workflow (to avoid conflicts).

When `ANDROID_LOGIC: "off"`:
- The Android workflow will skip `android.py` logic and let the generic builder path run.

---

## 🔐 Token strategy (recommended)

- **`BOT_TOKEN` (Fine-grained PAT)** → used only for **PR creation**  
  Repo permissions → *Contents: Read/Write*, *Pull requests: Read/Write*.

- **`KB_PUSH_TOKEN` (Fine-grained PAT)** → used only for **pushing KB/log artifacts** (optional)  
  Repo permissions → *Contents: Read/Write*.

Separation of duties lowers the chance of PAT auto-revocation due to bursty runs.

---

## 📂 What goes in `tools/`

These are installed by the detector via `tools.tar` and then committed:

- `AirysDark-AI_detector.py` — Step 1: scan + PROB generator  
- `AirysDark-AI_prob.py` — Step 2: deep probe + build workflow generation (AI optional)  
- `AirysDark-AI_builder.py` — Generic AI auto-fixer used in non-Android builds  
- `AirysDark-AI_android.py` — Android self-contained loop (probe+fix+iterate)  
- `AirysDark-AI_Request.py` — shared helper for LLM requests (used where applicable)  
- `airysdark_ai_scan.json` — detector output (overwritten each run)  
- `airysdark_ai_prob_report.json / .log` — probe reports (append-only log)

> Workflows after detector **must not** re-fetch tools; they rely on repo-committed copies.

---

## 🧠 Philosophy

> *Don’t just fail fast — learn fast.*  
AirysDark-AI acts like a bot teammate:
- Detects your build shape
- Tries a sensible command
- If it fails, explains, proposes small patches, and tries again
- It **never deletes logs** — it accumulates knowledge

---

## ❓FAQ

**Q: The Probe generated Android workflow. Can I still use the generic builder?**  
A: Yes — set `ANDROID_LOGIC: "off"` inside `AirysDark-AI_android.yml`. This will disable the Android loop and allow the generic builder path.

**Q: Where do patches land?**  
A: If any changes are staged after a run, a PR is opened using `peter-evans/create-pull-request@v6` with `BOT_TOKEN`.

**Q: Can it push knowledge/log files to a separate repo or branch?**  
A: Yes — wire `KB_PUSH_TOKEN` in your workflows where you want KB pushes.

---

## 🔮 Roadmap

- Smarter “learning” KB (cluster recurring failures → auto-recipes)
- Matrix probe to test multiple plausible build commands
- UI dashboard (GH Pages) to browse probe/build history

---

## 🧾 License

MIT (include a LICENSE file if you haven’t already).
