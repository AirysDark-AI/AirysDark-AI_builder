#!/usr/bin/env python3
"""
AirysDark-AI_prob.py
Reads detector outputs, then performs a deep repo probe:
- Scans every folder and file
- Records file structure, extensions, file sizes
- Reads text files (partial preview) when possible
- Generates JSON + LOG reports under tools/
"""
import os, pathlib, json, datetime

ROOT  = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
TOOLS = ROOT / "tools"
TOOLS.mkdir(parents=True, exist_ok=True)

REPORT_JSON = TOOLS / "airysdark_ai_prob_report.json"
REPORT_LOG  = TOOLS / "airysdark_ai_prob_report.log"

def read_text_preview(p: pathlib.Path, max_bytes=4096):
    try:
        raw = p.read_bytes()[:max_bytes]
        try:
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return raw.decode("latin1", errors="ignore")
    except Exception:
        return ""

def deep_scan():
    structure = []
    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs: dirs.remove(".git")
        r = pathlib.Path(root)
        rel = str(r.relative_to(ROOT)) or "."
        entry = {"dir": rel, "files": []}
        for fn in files:
            path = r / fn
            try: size = path.stat().st_size
            except Exception: size = -1
            ext = pathlib.Path(fn).suffix.lower()
            info = {"name": fn, "ext": ext, "size": size, "preview": ""}
            if size >= 0 and size <= 200*1024 and ext in (
                ".txt",".md",".gradle",".kts",".xml",".json",".py",".java",
                ".c",".cpp",".h",".hpp",".cmake",".toml",".yml",".yaml"
            ):
                info["preview"] = read_text_preview(path)
            entry["files"].append(info)
        structure.append(entry)
    return structure

def main():
    scan_log = (TOOLS / "airysdark_ai_scan.log").read_text(errors="ignore") if (TOOLS / "airysdark_ai_scan.log").exists() else ""
    scan_json = {}
    if (TOOLS / "airysdark_ai_scan.json").exists():
        try: scan_json = json.loads((TOOLS / "airysdark_ai_scan.json").read_text(errors="ignore"))
        except Exception: scan_json = {}

    structure = deep_scan()
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    report = {"timestamp": ts, "detector_log": scan_log, "detector_json": scan_json, "structure": structure}

    REPORT_JSON.write_text(json.dumps(report, indent=2))
    with REPORT_LOG.open("w", encoding="utf-8") as f:
        f.write(f"[{ts}] AirysDark-AI probe report\n")
        f.write("Detected types: " + ", ".join(scan_json.get("types", [])) + "\n\n")
        f.write("Directory structure:\n")
        for entry in structure:
            f.write(f"- {entry['dir']}/\n")
            for file in entry["files"]:
                f.write(f"   {file['name']} (ext={file['ext']}, size={file['size']})\n")
        f.write("\n--- End of probe ---\n")

    print(f"✅ Wrote {REPORT_JSON}")
    print(f"✅ Wrote {REPORT_LOG}")

if __name__ == "__main__":
    main()