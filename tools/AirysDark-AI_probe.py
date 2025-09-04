#!/usr/bin/env python3
"""
AirysDark-AI_probe.py
Figures out the most likely build command for a given project type,
so the workflow can run the *right* command before invoking the AI fixer.

Usage (GitHub Actions):
  - name: Probe build command
    id: probe
    run: |
      python3 tools/AirysDark-AI_probe.py --type "${{ matrix.type || inputs.type || 'android' }}"
    shell: bash

This prints a line: BUILD_CMD=...  (GitHub Actions step output).
"""

import argparse, os, re, subprocess, sys, json, shlex
from pathlib import Path

ROOT = Path(".").resolve()

def sh(cmd, cwd=None, check=False, capture=True, env=None):
    if capture:
        p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        if check and p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout)
        return p.stdout, p.returncode
    else:
        p = subprocess.run(cmd, cwd=cwd, shell=True, env=env)
        return "", p.returncode

def find_first(globs):
    for g in globs:
        for p in ROOT.glob(g):
            return p
    return None

def find_all(glob_pat):
    return list(ROOT.glob(glob_pat))

def print_output_var(name, val):
    # GitHub Actions compatible
    print(f"{name}={val}")

# ---------- Probers ----------

def probe_android():
    """
    Strategy:
      1) find gradlew(s) → pick the one whose settings.gradle(.kts) defines modules
      2) query tasks: ./gradlew -q tasks --all
      3) prefer assembleDebug / :app:assembleDebug / bundleDebug / assembleRelease / build
    """
    # Find gradle wrappers
    gradlews = []
    if (ROOT / "gradlew").exists():
        gradlews.append(ROOT / "gradlew")
    for p in ROOT.glob("**/gradlew"):
        if p not in gradlews:
            gradlews.append(p)

    if not gradlews:
        # fallback to generic
        return "./gradlew assembleDebug --stacktrace"

    def parse_modules(settings_path: Path):
        if not settings_path or not settings_path.exists():
            return []
        txt = settings_path.read_text(errors="ignore")
        # include(":app", ":mobile")  OR include ':app', ':feature:home'
        incs = re.findall(r'include\s*\((.*?)\)', txt, flags=re.S)
        mods = []
        for raw in incs:
            parts = re.split(r'[,\s]+', raw.strip())
            for p in parts:
                p = p.strip().strip('"\'')
                if p.startswith(":"):
                    mods.append(p[1:])
        # includeBuild(...) also exists; ignore for now
        return list(dict.fromkeys(mods))  # unique preserve order

    def is_app_module(dirp: Path):
        # detect com.android.application
        for fname in ("build.gradle", "build.gradle.kts"):
            f = dirp / fname
            if f.exists():
                t = f.read_text(errors="ignore")
                if "com.android.application" in t:
                    return True
        return False

    # Rank wrappers: prefer ones with settings + app module nearby
    ranked = []
    for g in gradlews:
        d = g.parent
        settings = None
        for sname in ("settings.gradle", "settings.gradle.kts"):
            sp = d / sname
            if sp.exists():
                settings = sp
                break
        modules = parse_modules(settings) if settings else []
        has_app = any(is_app_module(d / m.replace(":", "/")) for m in modules)
        ranked.append((g, settings is not None, has_app, modules))

    # sort: settings present & has_app first
    ranked.sort(key=lambda x: (not x[1], not x[2]))
    g, _, _, modules = ranked[0]
    g.chmod(0o755)

    # Try to ask gradle for tasks
    tasks_out, _ = sh(f"./{g.name} -q tasks --all", cwd=g.parent)
    # Candidates in order of preference
    candidates = [
        "assembleDebug",
        "bundleDebug",
        "assembleRelease",
        "bundleRelease",
        "build",
    ]
    module_candidates = []
    # from settings
    for m in modules:
        module_candidates.extend([
            f":{m}:assembleDebug",
            f":{m}:bundleDebug",
            f":{m}:assembleRelease",
            f":{m}:bundleRelease",
        ])
    # also add common guesses
    for guess in ("app", "mobile", "android"):
        module_candidates.extend([
            f":{guess}:assembleDebug",
            f":{guess}:bundleDebug",
            f":{guess}:assembleRelease",
            f":{guess}:bundleRelease",
        ])

    def task_exists(name: str):
        # Gradle prints task names in the task list; simple contains check
        return re.search(rf"(^|\s){re.escape(name)}(\s|$)", tasks_out) is not None

    # choose best task
    for t in candidates:
        if task_exists(t):
            return f"cd {shlex.quote(str(g.parent))} && ./gradlew {t} --stacktrace"

    for t in module_candidates:
        if task_exists(t):
            return f"cd {shlex.quote(str(g.parent))} && ./gradlew {t} --stacktrace"

    # Last resort: run assembleDebug and let Gradle error tell us more
    return f"cd {shlex.quote(str(g.parent))} && ./gradlew assembleDebug --stacktrace"

def probe_cmake():
    if (ROOT / "CMakeLists.txt").exists():
        return "cmake -S . -B build && cmake --build build -j"
    first = find_first(["**/CMakeLists.txt"])
    if first:
        d = first.parent
        outdir = f"build/{str(d).replace('/', '_')}"
        return f'cmake -S "{d}" -B "{outdir}" && cmake --build "{outdir}" -j'
    return "echo 'No CMakeLists.txt found' && exit 1"

def probe_linux():
    # Makefile root
    if (ROOT / "Makefile").exists():
        return "make -j"
    # Makefile anywhere
    mk = find_first(["**/Makefile"])
    if mk:
        return f'make -C "{mk.parent}" -j'
    # Meson/Ninja root
    if (ROOT / "meson.build").exists():
        return "(meson setup build --wipe || true); meson setup build || true; ninja -C build"
    # Meson/Ninja anywhere
    mb = find_first(["**/meson.build"])
    if mb:
        d = mb.parent
        return f'(cd "{d}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'
    return "echo 'No Makefile or meson.build found' && exit 1"

def probe_node():
    if (ROOT / "package.json").exists():
        return "npm ci && npm run build --if-present"
    p = find_first(["**/package.json"])
    if p:
        d = p.parent
        return f'cd "{d}" && npm ci && npm run build --if-present'
    return "echo 'No package.json found' && exit 1"

def probe_python():
    if (ROOT / "pyproject.toml").exists() or (ROOT / "setup.py").exists():
        return "pip install -e . && (pytest || python -m pytest || true)"
    p = find_first(["**/pyproject.toml", "**/setup.py"])
    if p:
        d = p.parent
        return f'cd "{d}" && pip install -e . && (pytest || python -m pytest || true)'
    return "echo 'No python project found' && exit 1"

def probe_rust():
    return "cargo build --locked --all-targets --verbose"

def probe_dotnet():
    return "dotnet restore && dotnet build -c Release"

def probe_maven():
    return "mvn -B package --file pom.xml"

def probe_flutter():
    return "flutter build apk --debug"

def probe_go():
    return "go build ./..."

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True,
                    choices=["android","cmake","linux","node","python","rust","dotnet","maven","flutter","go","unknown"])
    args = ap.parse_args()

    if args.type == "android": cmd = probe_android()
    elif args.type == "cmake": cmd = probe_cmake()
    elif args.type == "linux": cmd = probe_linux()
    elif args.type == "node": cmd = probe_node()
    elif args.type == "python": cmd = probe_python()
    elif args.type == "rust": cmd = probe_rust()
    elif args.type == "dotnet": cmd = probe_dotnet()
    elif args.type == "maven": cmd = probe_maven()
    elif args.type == "flutter": cmd = probe_flutter()
    elif args.type == "go": cmd = probe_go()
    else: cmd = "echo 'No build system detected' && exit 1"

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())