"""Source and configuration hashes for the run, so the delivered video can be traced to exact inputs.

WHY
---
The plan asks the delivery to include source and configuration hashes. The point is reproducibility: given
the video, someone should be able to identify the exact solver, config and physics inputs that produced it,
and confirm nothing was edited afterwards. A hash of the wrong thing is worse than none, so what is hashed
here is split into three groups and the distinction is recorded:

  * `code`   -- the tools that were actually invoked for this run;
  * `config` -- the run's own inputs: site, camera, binding, render config;
  * `physics` -- the solve record and the trajectory the render was driven from.

The PNG frames and the MP4 are NOT hashed here: they are large, and their own manifest (`video.mp4` plus the
decode check) is the record for them. The blend files are excluded for the same reason, and because they are
binary and regenerable from the above.

Usage:
    python tools/v57/make_hashes.py --run outcomes/v57/domino_arc/arc03 --out <run>/hashes.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CODE = [
    "tools/v56/b2_chain.py",
    "tools/v56/render.py",
    "tools/v56/box_visual.py",
    "tools/v57/arc_solve.py",
    "tools/v57/preview_arc.py",
    "tools/v57/scan_sites.py",
    "tools/v57/clearance_check.py",
    "tools/v57/gate_penetration.py",
    "tools/v57/make_render_inputs.py",
    "tools/v57/measure_actual.py",
    "tools/v57/compare_poses.py",
    "tools/v57/scene_roles.py",
    "tools/v57/run_pipeline.ps1",
]
CONFIG = [
    "tools/v57/site_arc03.json",
]
RUN_CONFIG = [
    "render_config.json", "binding.json", "preview_build.json", "camera.json",
    "scene_roles.json",
]
# The physics and gate records this run actually produces. Listing files that only an abandoned diagnostic
# path emitted would print a column of MISSING and imply the delivery is incomplete when it is not.
# `clearance_full.json` and `clearance_replay.json` ARE this round's penetration evidence; the latter is run
# on the final animated `replay.blend`, which is what section 1 of the plan requires.
RUN_PHYSICS = [
    "arc_result.json", "trajectory.json", "clearance_full.json", "clearance_replay.json",
    "video_verification.json", "render_timings_all.json",
]


def sha(p: Path) -> dict:
    h = hashlib.sha256()
    n = 0
    with p.open("rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            n += len(b)
    return {"sha256": h.hexdigest(), "bytes": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    A = ap.parse_args()
    run = Path(A.run)
    if not run.is_absolute():
        run = ROOT / run

    out = {"run": str(run), "groups": {}}
    for label, items, base in (("code", CODE, ROOT), ("config", CONFIG, ROOT),
                               ("run_config", RUN_CONFIG, run), ("physics", RUN_PHYSICS, run)):
        g = {}
        for rel in items:
            p = base / rel
            if p.is_file():
                g[rel] = sha(p)
            else:
                # Recorded explicitly rather than omitted: a missing expected input is information, and
                # silently dropping it would make the manifest look complete when it is not.
                g[rel] = {"missing": True}
        out["groups"][label] = g

    # A single combined digest over the code group, so "the code did not change" is one comparable value.
    cat = "".join(out["groups"]["code"][k]["sha256"] for k in sorted(out["groups"]["code"])
                  if "sha256" in out["groups"]["code"][k])
    out["code_combined_sha256"] = hashlib.sha256(cat.encode()).hexdigest()

    Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    Path(A.out).write_text(json.dumps(out, indent=2), encoding="utf-8")

    for label, g in out["groups"].items():
        print(f"{label}:")
        for k in sorted(g):
            v = g[k]
            if "sha256" in v:
                print(f"  {v['sha256'][:16]}  {v['bytes']:>12,d}  {k}")
            else:
                print(f"  {'MISSING':16s}  {'':>12s}  {k}")
    print(f"\ncode_combined_sha256 {out['code_combined_sha256']}")
    print(f"wrote {A.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
