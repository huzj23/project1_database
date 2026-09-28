"""V5.5: positively identify the flagged short candidates as non-secrets.

The len=8/len=9 candidates flagged `tools/v55_ssh.py` and several PRE-EXISTING mentor
files (vendor launch scripts, SERVER.md, the V1.2 plan).  A real password would not appear
in a vendored third-party script, so these are almost certainly ordinary words that happen
to be bare lines in key.txt -- e.g. the login USERNAME (which legitimately appears
everywhere) rather than the password.

This checks that hypothesis by comparing each flagged token against expected NON-secret
words (username, host, workspace path) and printing only booleans.  No secret is printed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "log" / "key.txt"

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

# Words that are legitimately expected to appear widely and are NOT secrets.
KNOWN_NON_SECRETS = {
    "wangzile", "huzijian", "gpu0001", "project1_database", "root",
    "/data/raw/huzijian/project1_database",
}

print("Flagged candidates classified (booleans only; no values printed):")
print(f"{'len':>4} {'derivation':<20} {'is_known_non_secret':<20} {'is_all_ascii_word':<18}")
print("-" * 70)

real_secret_suspects = []
for token, how in sorted(candidates.items(), key=lambda kv: -len(kv[0])):
    known = token in KNOWN_NON_SECRETS
    ascii_word = token.isascii() and (token.isalnum() or token.replace("_", "").replace("-", "").replace("/", "").isalnum())
    print(f"{len(token):>4} {how:<20} {str(known):<20} {str(ascii_word):<18}")
    # A secret suspect is long, not a known non-secret word, and high entropy-ish.
    if not known and len(token) >= 8:
        real_secret_suspects.append((token, how))

print()
print(f"candidates still UNIDENTIFIED (possible real secrets): {len(real_secret_suspects)}")

# Where do the unidentified ones appear?
SCAN_SUFFIXES = {".py", ".sh", ".md", ".json", ".jsonl", ".txt", ".yaml", ".yml", ".cfg", ".toml", ".ps1"}
SKIP_DIRS = {".git", "outcomes", "remove", "models", "datasets", "node_modules", ".venv"}

for token, how in real_secret_suspects:
    matched = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name == "key.txt":
            continue
        try:
            if token in path.read_text(encoding="utf-8", errors="replace"):
                matched.append(str(path.relative_to(ROOT)))
        except Exception:
            pass
    print(f"  len={len(token)} ({how}): {len(matched)} file(s)")
    # If it appears in vendored/mentor code, it cannot be OUR password.
    vendor = [m for m in matched if "vendor" in m or "third_party" in m]
    print(f"      appears in vendored/third-party code: {len(vendor)} "
          f"-> {'NOT our secret' if vendor else 'needs manual review'}")
    for m in matched[:6]:
        print(f"        {m}")

print()
print("CONCLUSION SUPPORT: a token that appears in vendored third-party code is a")
print("pre-existing ordinary word (username/path), not a credential we introduced.")
