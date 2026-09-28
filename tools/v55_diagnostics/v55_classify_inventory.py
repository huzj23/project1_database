#!/usr/bin/env python
"""V5.5 stage 01: classify the server-vs-local inventory into actionable groups.

01 section 6 asks specifically for SERVER-ONLY or DIFFERENT **scripts, configs,
patches and small collision assets** so they can be backed up before any local
change is pushed.  Rendered datasets, caches and third-party trees are excluded --
they are Git-ignored by design and are not code.

Usage:
    python tools/v55_classify_inventory.py <server_inventory.json> [--run-id ID]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Tree segments that are Git-ignored artifacts, not code to back up.
IGNORED_SEGMENTS = (
    "/datasets/",
    "/cache/",
    "/logs/",
    "/third_party/",
    "/__pycache__/",
    "/.git/",
    "/outcomes/",
    "/tmp/",
)

# Suffixes that represent real code/config worth diffing.
CODE_SUFFIXES = (".py", ".sh", ".yaml", ".yml", ".json", ".md", ".txt", ".urdf", ".mtl")


def interesting(rel: str) -> bool:
    if any(seg in f"/{rel}" for seg in IGNORED_SEGMENTS):
        return False
    return rel.endswith(CODE_SUFFIXES)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    args = ap.parse_args()

    data = json.loads(Path(args.report).read_text(encoding="utf-8"))
    server_only = [e for e in data["server_only"] if interesting(e["rel"])]
    differing = [e for e in data["differing"] if interesting(e["rel"])]

    print(f"report: {args.report}")
    print()
    print(f"=== SERVER-ONLY code/config files ({len(server_only)}) ===")
    print("    (exist on the server, absent locally -> back these up)")
    for e in sorted(server_only, key=lambda x: x["rel"]):
        print(f"  {e['bytes']:>9}  {e['rel']}")

    print()
    print(f"=== DIFFERING code/config files ({len(differing)}) ===")
    print("    (both sides exist with different content -> review before integrating)")
    for e in sorted(differing, key=lambda x: x["rel"]):
        print(f"  {e['rel']}")
        print(f"      server {e['server_sha256'][:16]}  local {e['local_sha256'][:16]}")

    print()
    total = len(server_only) + len(differing)
    print(f"RESULT: {total} code/config file(s) differ between server and local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
