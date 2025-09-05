#!/usr/bin/env python3
"""
AirysDark-AI_builder.py
AI auto-fix script to be used by generated build workflows after a failed build.

Design:
- No external fetching or model setup here (the workflow does that).
- Calls the centralized requester (AirysDark-AI_Request.py) to talk to OpenAI (fallback llama.cpp).
- Reads existing build.log (or runs the build once if missing), asks the AI for a unified diff,
  applies it to the working tree, and writes .pre_ai_fix.patch for inspection.
- Does NOT commit: the workflow's PR step takes care of staging/committing/opening PRs.

Env:
  BUILD_CMD                    # the command that failed (string)
  AI_BUILDER_ATTEMPTS=3        # how many attempts (ask AI again if needed)
  MAX_PROMPT_TOKENS=2500       # passed through to requester via env (optional)
  PROVIDER / FALLBACK_PROVIDER # 'openai' (primary) → 'llama' (fallback), etc.
  OPENAI_API_KEY / OPENAI_MODEL / MODEL_PATH etc. handled by requester

Outputs (files):
  .pre_ai_fix.patch                 # the patch we applied
  tools/airysdark_ai_builder_out.txt   # raw AI response (for debugging)
"""

import os
import sys
import subprocess
import pathlib
import tempfile
import re
from typing import Optional

PROJECT_ROOT = pathlib.Path(os.getenv("PROJECT_ROOT", ".")).resolve()
BUILD_CMD = os.getenv("BUILD_CMD", "").strip()
MAX_ATTEMPTS = int(os.getenv("AI_BUILDER_ATTEMPTS", "3"))
AI_LOG_TAIL = int(os.getenv("AI_LOG_TAIL", "120"))

TOOLS_DIR = PROJECT_ROOT / "tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

AI_OUT_PATH = TOOLS_DIR / "airysdark_ai_builder_out.txt"
BUILD_LOG = PROJECT_ROOT / "build.log"
PATCH_SNAPSHOT = PROJECT_ROOT / ".pre_ai_fix.patch"

# ------------- import requester (filename has hyphens, so use importlib) -------------
def _load_requester():
    import importlib.util
    req_path = PROJECT_ROOT / "tools" / "AirysDark-AI_Request.py"
    if not req_path.exists():
        raise RuntimeError(f"Missing requester: {req_path} (detector/probe should fetch it)")
    spec = importlib.util.spec_from_file_location("airysdark_ai_request", str(req_path))
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod

# ------------- helpers -------------
def sh(cmd: str, cwd: Optional[pathlib.Path] = None, check: bool = False, capture: bool = True) -> str:
    p = subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT), shell=True, text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, output=(p.stdout or ""))
    return p.stdout if capture else ""

def ensure_git_repo():
    if not (PROJECT_ROOT / ".git").exists():
        # minimal local repo so git apply works cleanly
        sh('git init', check=False, capture=False)
        sh('git config user.name "airysdark-ai"', check=False)
        sh('git config user.email "airysdark-ai@local"', check=False)
        sh('git add -A', check=False)
        sh('git commit -m "bootstrap repo for ai builder" || true', check=False)

def repo_tree(max_files: int = 120) -> str:
    out = sh("git ls-files || true")
    files = [ln for ln in (out or "").splitlines() if ln.strip()]
    return "\n".join(files[:max_files]) if files else "(no tracked files)"

def recent_diff(max_chars: int = 3000) -> str:
    # last 5 commits diff; if none, empty
    diff = sh("git diff --unified=2 -M -C HEAD~5..HEAD || true")
    return diff[-max_chars:] if diff else "(no recent git diff)"

def log_tail(lines: int = AI_LOG_TAIL) -> str:
    if not BUILD_LOG.exists():
        return "(no build log)"
    data = BUILD_LOG.read_text(errors="ignore").splitlines()
    if not data:
        return "(empty build log)"
    start = max(0, len(data) - int(lines))
    return "\n".join(data[start:])

def run_build_once_if_missing_log():
    if BUILD_LOG.exists() and BUILD_LOG.stat().st_size > 0:
        return
    if not BUILD_CMD:
        return
    # Run the build once just to capture output into build.log
    with open(BUILD_LOG, "wb") as f:
        proc = subprocess.Popen(BUILD_CMD, cwd=str(PROJECT_ROOT), shell=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert proc.stdout
        for line in proc.stdout:
            sys.stdout.buffer.write(line)
            f.write(line)
        proc.wait()

def extract_unified_diff(text: str) -> Optional[str]:
    # Strong matcher first (---/+++ with hunks)
    m = re.search(r"(?ms)^--- [^\n]+\n\+\+\+ [^\n]+\n(?:@@.*\n.*)+", text)
    if m:
        return text[m.start():].strip()
    # Weak matcher (first ---/+++ block)
    m2 = re.search(r"(?ms)^--- [^\n]+\n\+\+\+ [^\n]+\n", text)
    if m2:
        return text[m2.start():].strip()
    return None

def apply_patch(diff_text: str) -> bool:
    # snapshot the proposed diff
    PATCH_SNAPSHOT.write_text(diff_text, encoding="utf-8")
    # try apply
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".patch") as tmp:
        tmp.write(diff_text)
        tmp_path = tmp.name
    try:
        sh(f"git add -A || true", check=False)
        # keep whitespace flexible; reject files create .rej if needed
        out = sh(f"git apply --reject --whitespace=fix {tmp_path} || true")
        # If nothing actually changed, return False so workflow can skip PR
        chg = sh("git status --porcelain")
        return bool(chg.strip())
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

# ------------- main -------------
def main() -> int:
    print("== AirysDark-AI builder (unified diff fixer) ==")
    print("Project:", PROJECT_ROOT)

    ensure_git_repo()
    run_build_once_if_missing_log()

    # Prepare context for the AI
    tree = repo_tree()
    diff = recent_diff()
    tail = log_tail(AI_LOG_TAIL)

    # Load requester dynamically
    req = _load_requester()

    task = (
        "You are an automated build fixer working in a Git repository.\n"
        "Goal: return ONLY a unified diff (---/+++ with @@ hunks) that minimally fixes the build error.\n"
        "Keep edits small and safe; update build config (Gradle/CMake/etc.) only if needed. "
        "Do not change unrelated files."
    )
    context_parts = [
        "## Repository file list (truncated)\n" + tree,
        "## Recent git diff (truncated)\n" + diff,
        f"## Build command\n{BUILD_CMD or '(unknown)'}",
        f"## Build log tail (last {AI_LOG_TAIL} lines)\n{tail}",
    ]

    attempts = max(1, MAX_ATTEMPTS)
    for i in range(1, attempts + 1):
        print(f"\n-- AI attempt {i}/{attempts} --")
        try:
            out_text, maybe_diff = req.request_ai(
                task,
                context_parts=context_parts,
                want_diff=True,
                system="You are a precise CI fixer. Output only a unified diff when asked for code changes."
            )
        except Exception as e:
            print(f"AI request failed: {e}")
            continue

        # Save raw AI output for debugging
        try:
            AI_OUT_PATH.write_text(out_text, encoding="utf-8")
        except Exception:
            pass

        # Be robust: if the requester didn't parse diff, try ourselves
        diff_text = maybe_diff or extract_unified_diff(out_text or "")
        if not diff_text:
            print("AI did not return a recognizable unified diff; retrying...")
            continue

        print("Applying patch...")
        changed = apply_patch(diff_text)
        if not changed:
            print("Patch applied but no changes detected (maybe already applied or empty).")
            continue

        print("✅ Patch applied and working tree changed.")
        print(f"   Saved snapshot: {PATCH_SNAPSHOT}")
        return 0

    print("❌ No usable patch after attempts.")
    return 1


if __name__ == "__main__":
    sys.exit(main())