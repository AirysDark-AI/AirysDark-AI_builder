#!/usr/bin/env python3
# AirysDark-AI_detector.py — DETECT ONLY (generates a single PROB workflow)
#
# - Deep scans the repo (every folder/file; skips .git)
# - Classifies: android, linux, cmake, node, python, rust, dotnet, maven, flutter, go, bazel, scons, unknown
# - Writes artifacts for probe use (tools/*)
# - Generates exactly ONE workflow: .github/workflows/AirysDark-AI_prob.yml
#   This workflow:
#     * is manual (workflow_dispatch with a required "target" input)
#     * FIRST runs tools/AirysDark-AI_prob.py to create rich repo reports
#     * THEN runs the per-target probe step (Android is live; others are stubs)
#
import os, json, pathlib, datetime

ROOT  = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
TOOLS = ROOT / "tools"
WF    = ROOT / ".github" / "workflows"
TOOLS.mkdir(parents=True, exist_ok=True)
WF.mkdir(parents=True, exist_ok=True)

# ---- CMake flavor classifier ----
ANDROID_HINTS = (
    "android", "android_abi", "android_platform", "ndk", "cmake_android",
    "gradle", "externalnativebuild", "find_library(log)", "log-lib", "loglib"
)
DESKTOP_HINTS = (
    "add_executable", "pkgconfig", "find_package(", "threads", "pthread",
    "x11", "wayland", "gtk", "qt", "set(cmake_system_name linux"
)

def read_text_safe(p: pathlib.Path) -> str:
    try:
        return p.read_text(errors="ignore")
    except Exception:
        return ""

def cmakelists_flavor(cm_txt: str) -> str:
    t = cm_txt.lower()
    if any(h in t for h in ANDROID_HINTS): return "android"
    if any(h in t for h in DESKTOP_HINTS): return "desktop"
    return "desktop"

def deep_scan():
    hits = {
        "android_gradle": [],  # gradlew / build.gradle* / settings.gradle*
        "cmakelists": [],
        "make_like": [],       # Makefile / meson.build / build.ninja / *.mk
        "node": [],
        "python": [],
        "rust": [],
        "dotnet": [],
        "maven": [],
        "flutter": [],
        "go": [],
        "bazel": [],
        "scons": [],
    }
    cmake_flavors = []
    folder_hints = set()

    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs: dirs.remove(".git")
        r = pathlib.Path(root)
        for part in r.relative_to(ROOT).parts:
            if part:
                folder_hints.add(part.lower())
        for fn in files:
            low = fn.lower()
            rel = (r / fn).relative_to(ROOT)
            if low == "gradlew" or low.startswith("build.gradle") or low.startswith("settings.gradle"):
                hits["android_gradle"].append(str(rel))
            if low == "cmakelists.txt":
                hits["cmakelists"].append(str(rel))
                cmake_flavors.append({"path": str(rel), "flavor": cmakelists_flavor(read_text_safe(r / fn))})
            if low in ("makefile","gnumakefile","meson.build","build.ninja") or low.endswith(".mk"):
                hits["make_like"].append(str(rel))
            if low == "package.json":
                hits["node"].append(str(rel))
            if low in ("pyproject.toml","setup.py"):
                hits["python"].append(str(rel))
            if low == "cargo.toml":
                hits["rust"].append(str(rel))
            if low.endswith(".sln") or low.endswith(".csproj") or low.endswith(".fsproj"):
                hits["dotnet"].append(str(rel))
            if low == "pom.xml":
                hits["maven"].append(str(rel))
            if low == "pubspec.yaml":
                hits["flutter"].append(str(rel))
            if low == "go.mod":
                hits["go"].append(str(rel))
            if low in ("workspace","workspace.bazel","module.bazel") or fn in ("BUILD","BUILD.bazel"):
                hits["bazel"].append(str(rel))
            if low in ("sconstruct","sconscript"):
                hits["scons"].append(str(rel))

    # Folder-name hints
    if "android" in folder_hints:
        hits["android_gradle"].append("folder-hint:android")
    if "linux" in folder_hints:
        hits["make_like"].append("folder-hint:linux")

    return hits, cmake_flavors, sorted(folder_hints)

def decide_types(hits, cmake_flavors):
    types = set()
    if hits["android_gradle"]:
        types.add("android")
    if hits["cmakelists"]:
        types.add("cmake")
        if any(x["flavor"] == "desktop" for x in cmake_flavors):
            types.add("linux")
    if hits["make_like"]:
        types.add("linux")
    if hits["node"]:
        types.add("node")
    if hits["python"]:
        types.add("python")
    if hits["rust"]:
        types.add("rust")
    if hits["dotnet"]:
        types.add("dotnet")
    if hits["maven"]:
        types.add("maven")
    if hits["flutter"]:
        types.add("flutter")
    if hits["go"]:
        types.add("go")
    if hits["bazel"]:
        types.add("bazel")
    if hits["scons"]:
        types.add("scons")
    if not types:
        types.add("unknown")
    order = ["android","linux","cmake","node","python","rust","dotnet","maven","flutter","go","bazel","scons","unknown"]
    return [t for t in order if t in types]

def write_artifacts(hits, cmake_flavors, folder_hints, types):
    # human summary for PR body
    summary = []
    summary.append(f"[{datetime.datetime.utcnow().isoformat()}Z] AirysDark-AI detector scan")
    summary.append("Detected build types: " + ", ".join(types))
    summary.append("")
    def add(label, key):
        if hits[key]:
            summary.append(f"- {label}: {len(hits[key])}")
    add("Android Gradle files", "android_gradle")
    add("CMake files", "cmakelists")
    add("Make/Meson/Ninja signals", "make_like")
    add("Node projects", "node")
    add("Python projects", "python")
    add("Rust projects", "rust")
    add(".NET projects", "dotnet")
    add("Maven projects", "maven")
    add("Flutter projects", "flutter")
    add("Go projects", "go")
    add("Bazel signals", "bazel")
    add("SCons signals", "scons")
    log = summary[:] + ["", "Detailed file hits:"]
    for k, arr in hits.items():
        if arr:
            log.append(f"{k}:")
            for p in arr:
                log.append(f"  - {p}")
    if cmake_flavors:
        log.append("")
        log.append("cmake_flavors:")
        for x in cmake_flavors:
            log.append(f"  - {x['path']} -> {x['flavor']}")

    (TOOLS / "airysdark_ai_detector_summary.txt").write_text("\n".join(summary))
    (TOOLS / "airysdark_ai_scan.log").write_text("\n".join(log))
    (TOOLS / "airysdark_ai_detected.json").write_text(json.dumps({"types": types}, indent=2))
    (TOOLS / "airysdark_ai_scan.json").write_text(json.dumps({
        "types": types,
        "hits": hits,
        "cmake_flavors": cmake_flavors,
        "folder_hints": folder_hints,
    }, indent=2))
    (TOOLS / "airysdark_ai_probe_inputs.json").write_text(json.dumps({
        "types": types,
        "android_gradle_paths": hits["android_gradle"][:200],
        "cmakelists_paths": hits["cmakelists"][:200],
        "make_like_paths": hits["make_like"][:200],
    }, indent=2))

def generate_prob_workflow(types):
    # Choices in order, default is the first
    choices = types[:] or ["unknown"]
    default_choice = choices[0]

    yml = f"""
name: AirysDark-AI - Probe

on:
  workflow_dispatch:
    inputs:
      target:
        description: "Which build type to probe (pick before running)"
        required: true
        type: choice
        options: [{", ".join(choices)}]
        default: {default_choice}

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: ${{{{ github.workflow }}}}-${{{{{ github.ref }}}}}
  cancel-in-progress: true

jobs:
  probe:
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

      - name: Verify tools exist (added by detector PR)
        run: |
          set -euxo pipefail
          test -f tools/AirysDark-AI_prob.py
          test -f tools/AirysDark-AI_builder.py
          if [ "${{{{ github.event.inputs.target }}}}" = "android" ]; then
            test -f tools/AirysDark-AI_android.py
          fi
          ls -la tools

      - name: Run repo probe (always)
        id: run_prob
        run: |
          set -euxo pipefail
          python3 tools/AirysDark-AI_prob.py
          if [ -f tools/airysdark_ai_prob_report.json ]; then
            echo "PROB_JSON=ok" >> "$GITHUB_OUTPUT"
          else
            echo "PROB_JSON=missing" >> "$GITHUB_OUTPUT"
          fi

      - name: Upload probe report (JSON + LOG)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: airysdark-ai-probe-report
          path: |
            tools/airysdark_ai_prob_report.json
            tools/airysdark_ai_prob_report.log
          if-no-files-found: warn
          retention-days: 7

      # ===== Android (live) =====
      - name: Probe → Plan Android workflow (AI-assisted)
        if: ${{{{ github.event.inputs.target == 'android' }}}}
        id: probe_android
        run: |
          set -euxo pipefail
          python3 tools/AirysDark-AI_android.py --mode probe-ai | tee /tmp/android_plan.out
          if grep -E '^BUILD_CMD=' /tmp/android_plan.out >/dev/null; then
            CMD=$(grep -E '^BUILD_CMD=' /tmp/android_plan.out | sed 's/^BUILD_CMD=//')
            echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"
          fi

      # ===== Stubs (safe placeholders) =====
      - name: Probe Linux (stub)
        if: ${{{{ github.event.inputs.target == 'linux' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_linux.py to generate final Linux workflow PR."
          echo "Suggested baseline: make -C linux -j || make -j"

      - name: Probe CMake (stub)
        if: ${{{{ github.event.inputs.target == 'cmake' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_cmake.py to generate final CMake workflow PR."
          echo "Suggested baseline: cmake -S . -B build && cmake --build build -j"

      - name: Probe Node (stub)
        if: ${{{{ github.event.inputs.target == 'node' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_node.py."

      - name: Probe Python (stub)
        if: ${{{{ github.event.inputs.target == 'python' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_python.py."

      - name: Probe Rust (stub)
        if: ${{{{ github.event.inputs.target == 'rust' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_rust.py."

      - name: Probe .NET (stub)
        if: ${{{{ github.event.inputs.target == 'dotnet' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_dotnet.py."

      - name: Probe Maven (stub)
        if: ${{{{ github.event.inputs.target == 'maven' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_maven.py."

      - name: Probe Flutter (stub)
        if: ${{{{ github.event.inputs.target == 'flutter' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_flutter.py."

      - name: Probe Go (stub)
        if: ${{{{ github.event.inputs.target == 'go' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_go.py."

      - name: Probe Bazel (stub)
        if: ${{{{ github.event.inputs.target == 'bazel' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_bazel.py."

      - name: Probe SCons (stub)
        if: ${{{{ github.event.inputs.target == 'scons' }}}}
        run: |
          echo "TODO: add tools/AirysDark-AI_scons.py."

      - name: Probe Unknown (stub)
        if: ${{{{ github.event.inputs.target == 'unknown' }}}}
        run: |
          echo "No known build system detected. Keep iterating with the detector and handlers."
""".lstrip("\n")

    (WF / "AirysDark-AI_prob.yml").write_text(yml)

def main():
    hits, cmake_flavors, folder_hints = deep_scan()
    types = decide_types(hits, cmake_flavors)
    write_artifacts(hits, cmake_flavors, folder_hints, types)
    generate_prob_workflow(types)
    print("Detected types:", ", ".join(types))
    print(f"Wrote workflow: {WF / 'AirysDark-AI_prob.yml'}")

if __name__ == "__main__":
    main()