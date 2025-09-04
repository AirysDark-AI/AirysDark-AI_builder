#!/usr/bin/env python3
"""
AirysDark-AI_probe.py — deep repo scan to pick the right BUILD_CMD
Prints exactly: BUILD_CMD=<command>
"""

import os, re, shlex, subprocess, sys
from pathlib import Path
from typing import List, Tuple, Optional
from collections import Counter

ROOT = Path(".").resolve()

def run(cmd: str, cwd: Optional[Path] = None, capture: bool = True):
    if capture:
        p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.stdout, p.returncode
    else:
        p = subprocess.run(cmd, cwd=cwd, shell=True)
        return "", p.returncode

def scan_all_files() -> List[Tuple[str, Path]]:
    out = []
    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            p = Path(root) / f
            try:
                rel = p.relative_to(ROOT)
            except Exception:
                rel = p
            out.append((f.lower(), rel))
    return out

def prefer_shortest(paths: List[Path]) -> Optional[Path]:
    if not paths:
        return None
    return sorted(paths, key=lambda p: len(Path(str(p)).parts))[0]

def print_output_var(name: str, val: str):
    print(f"{name}={val}")

# -------- Linux (Make/Meson/only .mk) --------
def probe_linux(files: List[Tuple[str, Path]]) -> Optional[str]:
    names = [n for n, _ in files]
    paths = [p for _, p in files]

    # Prefer a real Makefile or GNUmakefile
    makefiles = [p for (n, p) in files if n in ("makefile", "gnumakefile")]
    mf = prefer_shortest(makefiles)
    if mf:
        if str(mf.parent) == ".":
            return "make -j"
        return f'make -C "{mf.parent}" -j'

    # Meson/Ninja
    mesons = [p for (n, p) in files if n == "meson.build"]
    mb = prefer_shortest(mesons)
    if mb:
        d = mb.parent
        return f'(cd "{d}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'

    # If we only have *.mk files, try best-effort:
    mk_paths = [p for (n, p) in files if str(p).lower().endswith(".mk")]
    if mk_paths:
        # pick the directory with the highest count of .mk as a likely build root
        cnt = Counter(str(p.parent) for p in mk_paths)
        likely_dir = Path(sorted(cnt.items(), key=lambda kv: (-kv[1], len(Path(kv[0]).parts)))[0][0])
        # Try a plain make there (many top-level makefiles are generated or include .mk dynamically)
        return f'make -C "{likely_dir}" -j'

    return None

# -------- The rest of the probers (unchanged) --------
def is_app_module(dirp: Path) -> bool:
    for fn in ("build.gradle", "build.gradle.kts"):
        f = dirp / fn
        if f.exists():
            try:
                t = f.read_text(errors="ignore")
                if "com.android.application" in t:
                    return True
            except Exception:
                pass
    return False

def parse_settings_modules(settings_path: Optional[Path]) -> List[str]:
    if not settings_path or not settings_path.exists():
        return []
    try:
        txt = settings_path.read_text(errors="ignore")
    except Exception:
        return []
    mods = []
    for raw in re.findall(r'include\s*\((.*?)\)', txt, flags=re.S):
        for p in re.split(r'[,\s]+', raw.strip()):
            s = p.strip().strip('"\'')

            if s.startswith(":"):
                mods.append(s[1:])
    for raw in re.findall(r'include\s+([^\n]+)', txt):
        for p in raw.split(","):
            s = p.strip().strip('"\'')

            if s.startswith(":"):
                mods.append(s[1:])
    out, seen = [], set()
    for m in mods:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out

def run_tasks_list(gradlew: Path) -> str:
    out, _ = run(f"./{gradlew.name} -q tasks --all", cwd=gradlew.parent)
    return out

def task_exists(tasks_out: str, name: str) -> bool:
    return re.search(rf"(^|\s){re.escape(name)}(\s|$)", tasks_out) is not None

def probe_android(files: List[Tuple[str, Path]]) -> Optional[str]:
    gradlews = [p for (n, p) in files if n == "gradlew"]
    if not gradlews and (ROOT / "gradlew").exists():
        gradlews = [Path("gradlew")]
    if not gradlews:
        return "./gradlew assembleDebug --stacktrace"

    ranked = []
    for g in gradlews:
        d = (ROOT / g).parent
        settings = None
        for sname in ("settings.gradle", "settings.gradle.kts"):
            sp = d / sname
            if sp.exists():
                settings = sp
                break
        modules = parse_settings_modules(settings)
        has_app = any(is_app_module(d / m.replace(":", "/")) for m in modules)
        ranked.append((g, settings is not None, has_app))
    ranked.sort(key=lambda x: (not x[1], not x[2], len(Path(str(x[0])).parts)))
    g = ranked[0][0]
    g_abs = (ROOT / g)
    try: os.chmod(g_abs, 0o755)
    except Exception: pass

    tasks_out = run_tasks_list(g_abs)
    base = shlex.quote(str(g_abs.parent))
    for t in ["assembleDebug","bundleDebug","assembleRelease","bundleRelease","build"]:
        if task_exists(tasks_out, t):
            return f"cd {base} && ./gradlew {t} --stacktrace"
    for guess in ("app","mobile","android"):
        for t in ["assembleDebug","bundleDebug","assembleRelease","bundleRelease"]:
            if task_exists(tasks_out, f":{guess}:{t}"):
                return f"cd {base} && ./gradlew :{guess}:{t} --stacktrace"
    return f"cd {base} && ./gradlew assembleDebug --stacktrace"

def probe_cmake(files: List[Tuple[str, Path]]) -> Optional[str]:
    cmakes = [p for (n, p) in files if n == "cmakelists.txt"]
    first = prefer_shortest(cmakes)
    if not first: return None
    outdir = f'build/{str(first.parent).replace("/", "_")}'
    return f'cmake -S "{first.parent}" -B "{outdir}" && cmake --build "{outdir}" -j'

def probe_node(files: List[Tuple[str, Path]]) -> Optional[str]:
    pkgs = [p for (n, p) in files if n == "package.json"]
    if not pkgs: return None
    def has_build_script(pkg_path: Path) -> bool:
        try: txt = (ROOT / pkg_path).read_text(errors="ignore")
        except Exception: return False
        return re.search(r'"scripts"\s*:\s*{[^}]*"build"\s*:', txt, flags=re.S) is not None
    with_build = [p for p in pkgs if has_build_script(p)]
    chosen = prefer_shortest(with_build) or prefer_shortest(pkgs)
    return f'cd "{chosen.parent}" && npm ci && npm run build --if-present'

def probe_python(files: List[Tuple[str, Path]]) -> Optional[str]:
    pyprojects = [p for (n, p) in files if n == "pyproject.toml"]
    setups     = [p for (n, p) in files if n == "setup.py"]
    chosen = prefer_shortest(pyprojects) or prefer_shortest(setups)
    if not chosen: return None
    d = chosen.parent
    return f'cd "{d}" && pip install -e . && (pytest || python -m pytest || true)'

def probe_rust(files: List[Tuple[str, Path]]) -> Optional[str]:
    cargos = [p for (n, p) in files if n == "cargo.toml"]
    chosen = prefer_shortest(cargos)
    if not chosen: return None
    return f'cd "{chosen.parent}" && cargo build --locked --all-targets --verbose'

def probe_dotnet(files: List[Tuple[str, Path]]) -> Optional[str]:
    slns = [p for (n, p) in files if str(p).lower().endswith(".sln")]
    if slns:
        chosen = prefer_shortest(slns)
        return f'dotnet restore "{chosen}" && dotnet build "{chosen}" -c Release'
    csfs = [p for (n, p) in files if str(p).lower().endswith((".csproj",".fsproj"))]
    chosen = prefer_shortest(csfs)
    if chosen:
        return f'dotnet restore "{chosen}" && dotnet build "{chosen}" -c Release'
    return None

def probe_maven(files: List[Tuple[str, Path]]) -> Optional[str]:
    poms = [p for (n, p) in files if n == "pom.xml"]
    chosen = prefer_shortest(poms)
    if not chosen: return None
    return f'mvn -B package --file "{chosen}"'

def probe_flutter(files: List[Tuple[str, Path]]) -> Optional[str]:
    pubs = [p for (n, p) in files if n == "pubspec.yaml"]
    chosen = prefer_shortest(pubs)
    if not chosen: return None
    return f'cd "{chosen.parent}" && flutter build apk --debug'

def probe_go(files: List[Tuple[str, Path]]) -> Optional[str]:
    mods = [p for (n, p) in files if n == "go.mod"]
    chosen = prefer_shortest(mods)
    if not chosen: return None
    return f'cd "{chosen.parent}" && go build ./...'

def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--type":
        print("Usage: AirysDark-AI_probe.py --type <android|cmake|linux|node|python|rust|dotnet|maven|flutter|go|unknown>")
        return 2
    ptype = sys.argv[2].strip().lower()
    files = scan_all_files()

    dispatch = {
        "android": probe_android,
        "cmake":   probe_cmake,
        "linux":   probe_linux,
        "node":    probe_node,
        "python":  probe_python,
        "rust":    probe_rust,
        "dotnet":  probe_dotnet,
        "maven":   probe_maven,
        "flutter": probe_flutter,
        "go":      probe_go,
        "unknown": lambda _f: "echo 'No build system detected' && exit 1",
    }

    func = dispatch.get(ptype)
    cmd = func(files) if func else "echo 'Unknown type' && exit 1"

    if not cmd:
        if ptype == "linux":
            cmd = "echo 'No Makefile / meson.build found (only .mk includes?)' && exit 1"
        elif ptype == "cmake":
            cmd = "echo 'No CMakeLists.txt found' && exit 1"
        else:
            cmd = "echo 'No build system detected' && exit 1"

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())