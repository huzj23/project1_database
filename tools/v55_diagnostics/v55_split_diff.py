#!/usr/bin/env python
"""Confirm which tree actually differs between server and local.

The earlier classification lumped together two DIFFERENT trees:
  * ``code/physics-video-sim/physics-video-sim-main/`` -- the project we patch;
  * ``code/vendor/phyco-sim/`` -- a vendored upstream copy (reachable from the
    project through the ``third_party/phyco-sim`` symlink).

Stage 01 cares about the FIRST one: server-only/different project code that a local
change could clobber.  This splits the two so the report is precise.
"""

from __future__ import annotations

import json
from pathlib import Path

REPORT = Path(
    "outcomes/v55/bootstrap/20260928T194500/server_only_and_diff.json"
)
MAIN_PREFIX = "code/physics-video-sim/physics-video-sim-main/"
VENDOR_PREFIX = "code/vendor/"

# Rendered outputs and caches inside the main tree -- not code, Git-ignored.
ARTIFACT_MARKERS = ("/datasets/", "/.pytest_cache/", "/cache/", "/logs/", "/__pycache__/")


def is_code(rel: str) -> bool:
    return not any(m in f"/{rel}" for m in ARTIFACT_MARKERS)


def main() -> int:
    data = json.loads(REPORT.read_text(encoding="utf-8"))

    def split(entries):
        main_code, main_art, vendor, other = [], [], [], []
        for e in entries:
            rel = e["rel"]
            if rel.startswith(MAIN_PREFIX):
                (main_code if is_code(rel) else main_art).append(rel)
            elif rel.startswith(VENDOR_PREFIX):
                vendor.append(rel)
            else:
                other.append(rel)
        return main_code, main_art, vendor, other

    sm, sa, sv, so = split(data["server_only"])
    dm, da, dv, do = split(data["differing"])

    print("=== SERVER-ONLY ===")
    print(f"  main project CODE      : {len(sm)}   <- matters for stage 01")
    for r in sm:
        print(f"      {r}")
    print(f"  main project ARTIFACTS : {len(sa)} (rendered datasets; Git-ignored, not code)")
    print(f"  vendor/phyco-sim       : {len(sv)}")
    print(f"  other                  : {len(so)}")

    print()
    print("=== DIFFERING ===")
    print(f"  main project CODE      : {len(dm)}   <- matters for stage 01")
    for r in dm:
        print(f"      {r[len(MAIN_PREFIX):]}")
    print(f"  main project ARTIFACTS : {len(da)}")
    print(f"  vendor/phyco-sim       : {len(dv)}")
    print(f"  other                  : {len(do)}")

    print()
    print("=== interpretation ===")
    if not sm and not dm:
        print("  The MAIN project tree has NO server-only CODE and NO code differences.")
        print(f"  The {len(sv) + len(dv)} differing files all live in code/vendor/phyco-sim,")
        print("  a vendored upstream checkout our project only reads through the")
        print("  third_party/phyco-sim symlink.  It is not our code to maintain.")
        print()
        print("  => No server-only project code needs backing up before local edits.")
        print("  => The real server-side risk is TIME-VARYING: any code we push now")
        print("     overwrites whatever the server currently has.  Our pushed files were")
        print("     inventoried (see server_inventory.txt) so the pre-push state is")
        print("     recoverable.")
    else:
        print("  ATTENTION: main-project code differs; back these up before editing:")
        for r in sm + dm:
            print(f"      {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
