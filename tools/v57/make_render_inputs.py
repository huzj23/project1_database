"""Assemble the V5.7 render config, trajectory and binding for the solved arc.

WHY THE TRAJECTORY IS PASSED THROUGH UNCHANGED
----------------------------------------------
`render.py` already performs the world conversion itself, per object, as

    T_WV(t) = T_WB(t) @ inverse(T_WB(0)) @ T_WV(0)

capturing `T_WV(0)` from the scene as authored and never recomputing it. So this tool must NOT pre-convert
positions into world space: doing that and then letting the renderer apply its own conversion would apply
the rigid motion twice, and the boxes would fly off at roughly double the solved travel.

What this tool therefore emits is the solver's own body-frame rows, verbatim, plus the binding that names
which Blender object each body id drives, plus the approved camera. The frame contract stays in exactly one
place -- `render.py` -- which is the same code path the earlier verified round used.

Checks it does perform, because they are cheap and catch the errors that a pass-through would otherwise
hide: every solver body id must be bound to an object that the preview actually created, the row counts
must agree, and the requested frame count must be covered by the recording.

Usage:
    python tools/v57/make_render_inputs.py --solve tmp/v57/arc_local --preview <preview_build.json> \
        --out <run dir> --camera C3 --blend <runtime blend>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solve", required=True, help="directory holding arc_result.json")
    ap.add_argument("--preview", required=True, help="preview_build.json naming the created objects")
    ap.add_argument("--out", required=True)
    ap.add_argument("--camera", required=True, choices=["C1", "C2", "C3"])
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--res", default="1280x720")
    ap.add_argument("--spp", type=int, default=16)
    ap.add_argument("--blend", required=True, help="runtime blend the renderer will open")
    A = ap.parse_args()

    solve = json.loads((Path(A.solve) / "arc_result.json").read_text(encoding="utf-8"))
    prev = json.loads(Path(A.preview).read_text(encoding="utf-8"))
    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = solve["trajectory_rows"]
    created = {c["body"]: c for c in prev["created"]}

    # --- verification that the pass-through is actually complete ---------------------------------
    missing = [b for b in rows if int(b) not in created]
    if missing:
        raise SystemExit(f"FATAL: solver bodies {missing} have no object in the preview build")
    counts = {b: len(r) for b, r in rows.items()}
    if len(set(counts.values())) != 1:
        raise SystemExit(f"FATAL: bodies disagree on row count: {counts}")
    n_rows = next(iter(counts.values()))
    if n_rows < A.frames:
        raise SystemExit(f"FATAL: the solve recorded {n_rows} frames but {A.frames} were requested; "
                         f"the video would run past the simulation")

    traj = {b: r for b, r in rows.items()}
    # The trigger is a real simulated body and is animated, so it must be in the trajectory. `run_chain`
    # records it under `trigger_info_row` rather than in `trajectory_rows`, and it is bound as body -1.
    # Omitting it left a bound body with no rows, which the gate correctly refused.
    trig_rows = solve["simulation"].get("trigger_info_row")
    if trig_rows:
        if len(trig_rows) != n_rows:
            raise SystemExit(f"FATAL: the trigger recorded {len(trig_rows)} rows but the boxes recorded "
                             f"{n_rows}; the renderer keys every body on the same grid")
        traj["-1"] = trig_rows
    # The renderer reads `["bodies"]` off this file, so the rows are wrapped under that key. The solver's own
    # `trajectory_rows` is left as written by the solver -- this file is a render input, not a second copy of
    # the solve, and keeping the two separate means the solve record cannot be silently reshaped by a
    # render-side change.
    (out / "trajectory.json").write_text(json.dumps({"bodies": traj}, indent=2), encoding="utf-8")

    # --- binding: body id -> the objects that exist in the runtime blend --------------------------
    binding = {}
    for bid, c in sorted(created.items()):
        binding[str(bid)] = {"objects": [c["name"]], "collision_obj": c["name"],
                             "asset_id": c["asset_id"],
                             "note": "object created by tools/v57/preview_arc.py in the collision frame"}
    (out / "binding.json").write_text(json.dumps(binding, indent=2), encoding="utf-8")

    # --- camera, from the approved candidate -----------------------------------------------------
    cam = prev["cameras"][A.camera]
    if cam.get("status") != "CLEAR":
        raise SystemExit(f"FATAL: camera {A.camera} status is {cam.get('status')}, not CLEAR")
    rx, ry = (int(v) for v in A.res.lower().split("x"))
    cfg = {
        "scene_id": "hidden_alley_arc_v57",
        "runtime_blend": str(Path(A.blend).resolve()),
        "frame_count": A.frames,
        "video_fps": A.fps,
        "trajectory": str((out / "trajectory.json").resolve()),
        "binding": binding,
        "resolution": [rx, ry],
        "samples": A.spp,
        "camera": {
            "name": "v57_camera",
            "eye_m": cam["eye"],
            "aim_m": cam["aim"],
            "lens_mm": cam["spec"]["lens"],
            "sensor_width_mm": 36.0,
            "frame": 0,
            "note": (f"candidate {A.camera}: azimuth {cam['spec']['az']} deg off the chain chord, "
                     f"elevation {cam['spec']['dep']} deg, distance {cam['spec']['dist_used']} m, "
                     f"measured span {cam['spec']['span_achieved']:.3f} of frame width. "
                     f"Approved by the user from the 1280x720 preview render."),
        },
    }
    (out / "render_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    print(f"wrote trajectory.json ({len(traj)} bodies x {n_rows} rows), binding.json, render_config.json")
    print(f"  camera {A.camera}: eye {[round(v, 3) for v in cam['eye']]} "
          f"aim {[round(v, 3) for v in cam['aim']]} lens {cam['spec']['lens']} mm "
          f"span {cam['spec']['span_achieved']:.3f}")
    print(f"  {A.frames} frames at {A.fps} fps = {A.frames / A.fps:.3f} s, {A.res} at {A.spp} spp")
    print(f"  trajectory is the solver's body-frame rows, unconverted: render.py applies "
          f"T_WV(t) = T_WB(t) @ inv(T_WB(0)) @ T_WV(0) itself")
    print("")
    print("  binding:")
    for bid, spec in sorted(binding.items(), key=lambda kv: int(kv[0])):
        print(f"    body {bid:>3s} -> {spec['objects'][0]:28s} {spec['asset_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
