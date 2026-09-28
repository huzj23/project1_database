"""Move stale V5.5 proxy artifacts into remove/ with a hash-verified manifest.

The project rule is NO DELETION anywhere. Extra proxy files accumulated in the Italian Flat
props directory across several tool iterations, and a later measurement then globbed
`*_part*.obj` and silently measured a MIXTURE of files from different runs (bottle showed 21
parts from an early run when the current run produces 3). That is a correctness hazard, not
just clutter, so the stale files are quarantined here rather than left in place.

Each file is hashed before the move and re-hashed after, so every entry is provably intact.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
REMOVE = ROOT / "remove/v55_stale_proxies"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    # Everything currently under props/ is superseded by the consolidated rebuild, which
    # writes each candidate into its own subdirectory.  Old flat files are what caused the
    # mixed-measurement bug.
    new_layout_markers = ("manifest.json",)
    candidates = []
    for p in PROPS.iterdir():
        if p.is_dir():
            continue
        if p.name in new_layout_markers:
            continue
        candidates.append(p)

    if not candidates:
        print("nothing to quarantine")
        return 0

    REMOVE.mkdir(parents=True, exist_ok=True)
    manifest = {"reason": (
        "stale proxy artifacts from earlier tool iterations; a later measurement globbed "
        "*_part*.obj and mixed files from different runs, so they are quarantined for a "
        "deterministic rebuild"), "files": []}

    print(f"=== quarantining {len(candidates)} file(s) to {REMOVE} ===")
    for src in sorted(candidates):
        before = sha256(src)
        dst = REMOVE / src.name
        if dst.exists():
            # Never overwrite: keep both by suffixing.
            i = 1
            while (REMOVE / f"{src.name}.{i}").exists():
                i += 1
            dst = REMOVE / f"{src.name}.{i}"
        shutil.move(str(src), str(dst))
        after = sha256(dst)
        intact = before == after
        manifest["files"].append({
            "original": str(src),
            "quarantined": str(dst),
            "bytes": dst.stat().st_size,
            "sha256_before": before,
            "sha256_after": after,
            "intact": intact,
        })
        print(f"  {src.name:44s} {dst.stat().st_size:>9d} B  intact={intact}")
        if not intact:
            raise SystemExit(f"FATAL: hash changed while moving {src}")

    man_path = REMOVE / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(f["bytes"] for f in manifest["files"])
    print(f"\nmoved {len(manifest['files'])} files, {total} bytes")
    print(f"all intact: {all(f['intact'] for f in manifest['files'])}")
    print(f"manifest: {man_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
