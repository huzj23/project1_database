"""V5.5: list WHICH files a candidate token appears in, printing no secret value.

Candidate #1 (70 chars, 6 files) and #9 (10 chars, 29 files) were flagged.  A 70-char
match could be a real leak, so the file list must be inspected.  Only paths and a masked
context label are printed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "log" / "key.txt"

SKIP_DIRS = {".git", "outcomes", "remove", "models", "datasets", "node_modules", ".venv"}
SCAN_SUFFIXES = {".py", ".sh", ".md", ".json", ".jsonl", ".txt", ".yaml", ".yml", ".cfg", ".toml", ".ps1"}

raw = KEY.read_text(encoding="utf-8", errors="replace")
lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

candidates: dict[str, str] = {}
for lineno, line in enumerate(lines, 1):
    parts = line.split()
    if not parts:
        continue
    if "密码" in line:
        candidates[parts[-1]] = f"line{lineno}:after-密码"
    if parts[0] in ("ssh", "scp") and len(parts) >= 2:
        candidates[parts[-1]] = f"line{lineno}:ssh-last"
    if len(parts) == 1 and len(parts[0]) >= 8 and not parts[0].startswith("#"):
        candidates[parts[0]] = f"line{lineno}:bare"

files = []
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.name == "key.txt":
        continue
    files.append(path)

for token, how in sorted(candidates.items(), key=lambda kv: -len(kv[0])):
    fp = hashlib.sha256(token.encode()).hexdigest()[:12]
    matched = []
    for path in files:
        try:
            if token in path.read_text(encoding="utf-8", errors="replace"):
                matched.append(path.relative_to(ROOT))
        except Exception:
            pass
    if not matched:
        continue
    # Only report tokens that are long enough to plausibly BE a secret.
    print(f"candidate len={len(token)} fp={fp} ({how}) -> {len(matched)} file(s)")
    for rel in matched[:12]:
        print(f"    {rel}")
    if len(matched) > 12:
        print(f"    ... and {len(matched) - 12} more")
    print()
