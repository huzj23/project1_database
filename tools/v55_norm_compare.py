#!/usr/bin/env python
"""Prove the server-vs-local code differences are line-ending-only.

Stage 01 must know whether the server holds code we would clobber.  A raw sha256
comparison wrongly flags every CRLF file, because the local tree is a Windows
checkout (CRLF) while the server is Linux (LF).

This re-hashes each differing file AFTER normalising CRLF -> LF and reports:

  * ``content-equal``    -- differs only by line endings; no real divergence
  * ``really-different`` -- genuine content difference; must be reviewed

Reports per tree (main project vs vendored) so the conclusion is unambiguous.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

LOCAL_WS = Path(__file__).resolve().parent.parent
REPORT = LOCAL_WS / "outcomes/v55/bootstrap/20260928T194500/server_only_and_diff.json"

MAIN_PREFIX = "code/physics-video-sim/physics-video-sim-main/"
VENDOR_PREFIX = "code/vendor/"
ARTIFACT_MARKERS = ("/datasets/", "/.pytest_cache/", "/cache/", "/logs/", "/__pycache__/")


def norm_sha256(path: Path) -> str:
    """sha256 of the file with CRLF normalised to LF."""
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def is_code(rel: str) -> bool:
    return not any(m in f"/{rel}" for m in ARTIFACT_MARKERS)


def main() -> int:
    data = json.loads(REPORT.read_text(encoding="utf-8"))

    groups: dict[str, dict[str, list[str]]] = {
        "main_code": {"content-equal": [], "really-different": [], "missing": []},
        "vendor": {"content-equal": [], "really-different": [], "missing": []},
        "artifact": {"content-equal": [], "really-different": [], "missing": []},
    }

    for e in data["differing"]:
        rel = e["rel"]
        local = LOCAL_WS / rel
        if not local.is_file():
            key = "missing"
        elif norm_sha256(local) == e["server_sha256"]:
            key = "content-equal"
        else:
            key = "really-different"

        if rel.startswith(MAIN_PREFIX):
            bucket = "main_code" if is_code(rel) else "artifact"
        elif rel.startswith(VENDOR_PREFIX):
            bucket = "vendor"
        else:
            bucket = "main_code"
        groups[bucket][key].append(rel)

    print("=== normalised comparison (CRLF -> LF) ===")
    total_really = 0
    for name, buckets in groups.items():
        eq, diff, miss = (
            buckets["content-equal"],
            buckets["really-different"],
            buckets["missing"],
        )
        total_really += len(diff)
        print(f"\n  [{name}]")
        print(f"    content-equal (line-endings only) : {len(eq)}")
        print(f"    REALLY different                  : {len(diff)}")
        print(f"    missing locally                   : {len(miss)}")
        for r in diff[:20]:
            print(f"        DIFF {r}")
        for r in miss[:10]:
            print(f"        MISS {r}")

    print()
    print("=== conclusion ===")
    main_diff = groups["main_code"]["really-different"]
    if total_really == 0:
        print("  ALL differences are line-ending only.")
        print("  The server holds NO project code that differs in content from local.")
        print("  => Nothing to back up for content reasons; a local push cannot")
        print("     clobber a divergent server-side implementation.")
    else:
        print(f"  {total_really} file(s) differ in CONTENT and must be reviewed.")
        if main_diff:
            print("  Including main-project code:")
            for r in main_diff:
                print(f"      {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
