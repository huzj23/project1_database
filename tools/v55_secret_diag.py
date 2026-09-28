"""V5.5: diagnose WHICH candidate token is matching, without printing the secret.

The first pass flagged 39 files including a vendored TensorFlow module, which strongly
suggests the candidate set contains ordinary words (e.g. a bare line in key.txt or a
hostname) rather than only real secrets.  This prints, for each candidate, only its
LENGTH and a masked fingerprint, plus how many files it matches -- enough to separate a
true credential from a false positive without ever revealing the value.
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

candidates: dict[str, str] = {}  # token -> how it was derived
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

print(f"candidate tokens derived: {len(candidates)}")
print()
print(f"{'idx':>3} {'len':>4} {'fingerprint':<20} {'files':>6}  derivation")
print("-" * 70)

files = []
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.name == "key.txt":
        continue
    files.append(path)

for idx, (token, how) in enumerate(sorted(candidates.items(), key=lambda kv: -len(kv[0])), 1):
    fp = hashlib.sha256(token.encode()).hexdigest()[:16]
    hits = 0
    for path in files:
        try:
            if token in path.read_text(encoding="utf-8", errors="replace"):
                hits += 1
        except Exception:
            pass
    print(f"{idx:>3} {len(token):>4} {fp:<20} {hits:>6}  {how}")

print()
print("Interpretation: a genuine credential should be a long, high-entropy token matching")
print("very few files (ideally zero outside key.txt).  A token matching many files, or one")
print("that is a short ordinary word, is a false positive of this scan.")
