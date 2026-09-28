"""V5.5: verify no credential or token leaked into any tracked/committable file.

Reads log/key.txt, extracts every whitespace-separated token that looks like a password
or host credential, and greps the repository for those literals.  Prints only COUNTS and
file paths -- never the secret itself -- so this output is safe to log.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "log" / "key.txt"

SKIP_DIRS = {".git", "outcomes", "remove", "models", "datasets", "node_modules", ".venv"}
SCAN_SUFFIXES = {".py", ".sh", ".md", ".json", ".jsonl", ".txt", ".yaml", ".yml", ".cfg", ".toml", ".ps1"}

if not KEY.is_file():
    print("key.txt absent -- nothing to compare against")
    raise SystemExit(0)

raw = KEY.read_text(encoding="utf-8", errors="replace")
lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
print(f"key.txt: {len(lines)} non-empty lines")

# Collect every plausible secret token: the LAST whitespace token of any line that
# mentions ssh/scp, plus anything after a literal 密码 marker.
secrets: set[str] = set()
for line in lines:
    parts = line.split()
    if not parts:
        continue
    if "密码" in line:
        secrets.add(parts[-1])
    if parts[0] in ("ssh", "scp") and len(parts) >= 2:
        secrets.add(parts[-1])
    # A bare high-entropy token line.
    if len(parts) == 1 and len(parts[0]) >= 8 and not parts[0].startswith("#"):
        secrets.add(parts[0])

secrets = {s for s in secrets if len(s) >= 6 and not s.startswith(("ssh", "http", "-"))}
print(f"candidate secret tokens: {len(secrets)} (lengths only: "
      f"{sorted({len(s) for s in secrets})})")

hits = 0
scanned = 0
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.name == "key.txt":
        continue
    scanned += 1
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for secret in secrets:
        if secret in text:
            print(f"  LEAK: {path.relative_to(ROOT)}")
            hits += 1

print(f"scanned {scanned} files; secret hits: {hits}")

# Also look for token-shaped strings.
token_re = re.compile(r"hf_[A-Za-z0-9]{20,}")
token_hits = 0
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for _ in token_re.finditer(text):
        print(f"  TOKEN: {path.relative_to(ROOT)}")
        token_hits += 1

print(f"HF-token-shaped hits: {token_hits}")

# Confirm key.txt itself is ignored by git.
gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8", errors="replace")
print(f"key.txt ignored by .gitignore: {'log/key.txt' in gitignore or 'key.txt' in gitignore}")
print("RESULT: " + ("CLEAN" if (hits == 0 and token_hits == 0) else "SECRETS PRESENT"))
