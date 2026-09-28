#!/usr/bin/env python
"""V5.5 stage 01 section 6: compare the SERVER inventory against the LOCAL tree.

Reads ``outcomes/v55/bootstrap/<run_id>/server_inventory.txt`` and hashes the same
relative paths locally, then reports:

  * server-only files  (exist on the server, absent locally)  -> candidates to back up
  * local-only files   (exist locally, absent on the server)
  * differing files    (both exist, different sha256)

Paths in the inventory are absolute server paths; they are mapped onto the local
workspace root by replacing the server workspace prefix.

Usage:
    python tools/v55_compare_inventory.py <server_inventory.txt> [--run-id ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SERVER_WS = "/data/raw/huzijian/project1_database"
LOCAL_WS = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inventory")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    inv = Path(args.inventory)
    rows: list[tuple[int, str, str]] = []
    for line in inv.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        # Expected shape: <size>\t<sha256>\t<absolute path>
        if len(parts) != 3:
            continue
        size, sha, path = parts
        rows.append((int(size), sha, path))

    server_only: list[tuple[str, int, str]] = []
    differing: list[tuple[str, str, str]] = []

    for size, sha, path in rows:
        if not path.startswith(SERVER_WS):
            continue
        rel = path[len(SERVER_WS):].lstrip("/")
        local = LOCAL_WS / rel
        if not local.is_file():
            server_only.append((rel, size, sha))
        else:
            lsha = sha256(local)
            if lsha != sha:
                differing.append((rel, sha, lsha))

    print(f"inventory       : {inv}")
    print(f"entries parsed  : {len(rows)}")
    print(f"server-only     : {len(server_only)}")
    print(f"differing       : {len(differing)}")

    print()
    print("--- server-only files (first 40) ---")
    for rel, size, _sha in server_only[:40]:
        print(f"  {size:>10}  {rel}")
    if len(server_only) > 40:
        print(f"  ... and {len(server_only) - 40} more")

    print()
    print("--- differing files ---")
    for rel, ssha, lsha in differing:
        print(f"  {rel}")
        print(f"      server {ssha[:16]}  local {lsha[:16]}")

    out = Path(args.out) if args.out else inv.parent / "server_only_and_diff.json"
    out.write_text(
        json.dumps(
            {
                "inventory": str(inv),
                "server_only": [{"rel": r, "bytes": s, "sha256": h} for r, s, h in server_only],
                "differing": [
                    {"rel": r, "server_sha256": a, "local_sha256": b} for r, a, b in differing
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print()
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
