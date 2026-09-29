"""Print the tail of a server-side log file, avoiding quoting problems."""

import sys
from pathlib import Path

p = Path(sys.argv[1])
n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
print(f"=== {p} ({len(lines)} lines, showing last {n}) ===")
for line in lines[-n:]:
    print(line)
