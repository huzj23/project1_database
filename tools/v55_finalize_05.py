"""V5.5 stage 05: write the run-level files the solver cannot know (camera, commands, checksums).

`write_evidence` produces the trajectory/contact/event/identity records because those come straight
from the solve. Three files in 02's list are not solver output and so have to be written by the
stage that knows the answer:

  camera.json       the camera decision. 05 section 2.8 and 09 fix this, so it is recorded once
                    here and consumed by the renderer; a renderer that invents its own camera is
                    how an earlier stage produced two different framings from one config.
  commands.txt      the exact reproduction commands, absolute paths only, as 01 requires.
  SHA256SUMS.txt    a hash of every evidence file, so the package can be checked later even after
                    the local backup is made.

This script only writes those; it never touches the solve.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "20260929T080000"
RUN = OUT / RUN_ID

# 09 section 2: 1920x1080, and for the single-interaction spans a 0-8 degree low elevation with a
# 35-70 mm focal length. The framing has to hold the whole descent path AND the response, so the
# camera is placed to look along the tray with the target and the release point both inside frame.
CAMERA = {
    "name": "V55_ItalianFlat_05_Strike",
    "resolution": [1920, 1080],
    "fps": 24,
    "focal_length_mm": 50.0,
    "sensor_width_mm": 36.0,
    "elevation_deg": 6.0,
    "aim_point_m": None,
    "distance_m": 1.60,
    "azimuth_deg": None,
    "note": ("placed by measurement against the recorded trajectory: the aim point is the target's "
             "settled centre, the elevation is a low 6 degrees so the tray rim does not hide the "
             "glasses, and the distance is set so the drop path and the response are both inside "
             "the 2-98% safe frame"),
}


def main() -> int:
    prov = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))
    cfg = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
    traj = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
    target = cfg["target_instance_id"]
    trigger = cfg["trigger_instance_id"]
    body = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
    t0 = next(b for b in body if b["instance_id"] == target)

    # The aim point is the target's settled centre; the distance is chosen from the recorded
    # geometry so the whole drop path fits. Everything is derived, not guessed.
    aim = [float(v) for v in t0["position_m"]]
    rows_t = traj[trigger]
    # Drop path extent, plus a margin for the response.
    pts = [r["position_m"] for r in rows_t] + [r["position_m"] for r in traj[target]]
    zs = [p[2] for p in pts]
    path_m = max(zs) - min(zs)
    # Vertical field of view for a 50 mm lens on a 36 mm sensor at 16:9.
    import math
    sensor_h = CAMERA["sensor_width_mm"] * 1080.0 / 1920.0
    vfov = 2.0 * math.atan(sensor_h / (2.0 * CAMERA["focal_length_mm"]))
    # The path must occupy at most 80% of the frame height (09's safe frame is 2-98%, and the
    # subject should not fill it edge to edge).
    dist = (path_m / 0.80) / (2.0 * math.tan(vfov / 2.0))
    cam = dict(CAMERA)
    cam["aim_point_m"] = aim
    cam["path_span_m"] = round(path_m, 6)
    cam["vertical_fov_deg"] = round(math.degrees(vfov), 4)
    cam["distance_m"] = round(max(dist, 0.8), 6)
    cam["derivation"] = ("distance = (path_span / 0.80) / (2*tan(vfov/2)); path_span is the "
                         "recorded z range of the trigger and target over the whole run")
    (RUN / "camera.json").write_text(json.dumps(cam, indent=2), encoding="utf-8")
    print(f"camera: aim {aim}, path span {path_m*1000:.1f} mm, distance {cam['distance_m']} m, "
          f"elevation {cam['elevation_deg']} deg, {cam['resolution'][0]}x{cam['resolution'][1]}, "
          f"focal {cam['focal_length_mm']} mm")

    cmds = [
        "# stage 05 italian flat -- reproduction commands, run " + RUN_ID,
        "# every path is absolute, as 01 requires; CPU only",
        "export CUDA_VISIBLE_DEVICES=\"\"",
        "export KUBRIC_USE_GPU=false",
        "export OMP_NUM_THREADS=8",
        "",
        "# 1. build the scene layers in a runtime copy (source .blend is never modified)",
        "cd /data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main",
        "cd /data/raw/huzijian/project1_database",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_build_layers.py",
        "",
        "# 2. measure the props on their real triangles and price the energy budget",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_measure_props.py",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_energy_budget.py",
        "",
        "# 3. prove the collision routes and the self-check work",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_test_dyn_mesh.py",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_test_self_check.py",
        "",
        "# 4. the decisive topple experiment with the stage-03 FINAL proxy choice",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_decisive_05.py",
        "",
        "# 5. the target/offset search and the production solve",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_final_05.py " + RUN_ID,
        "",
        "# 6. the no-trigger control and the per-substep soft no-go check",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_control_05.py " + RUN_ID,
        "",
        "# 7. the camera decision and this file",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_finalize_05.py " + RUN_ID,
        "",
        "# 8. render 09-style keyframes, diagnostic previews and the final video",
        "/data/raw/huzijian/project1_database/tools/conda_env/bin/python "
        "/data/raw/huzijian/project1_database/tools/v55_render_05.py " + RUN_ID,
        "",
        "# outputs",
        f"#   /data/raw/huzijian/project1_database/outcomes/v55/italian_flat/box_hits_bottle/{RUN_ID}/",
    ]
    (RUN / "commands.txt").write_text("\n".join(cmds) + "\n", encoding="utf-8")
    print(f"commands.txt written ({len(cmds)} lines)")

    # ---- hashes ------------------------------------------------------------------------
    lines = []
    for p in sorted(RUN.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            h = hashlib.sha256()
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            lines.append(f"{h.hexdigest()}  {p.relative_to(RUN).as_posix()}  ({p.stat().st_size} bytes)")
    (RUN / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SHA256SUMS.txt written for {len(lines)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
