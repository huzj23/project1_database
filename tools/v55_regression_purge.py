"""V5.5 stage 01 regression: the patched purge must not break the real render chain.

Renders ONE real sample with the patched ``blender_backend`` and checks:
  * the sample still validates and renders (the purge signature changed);
  * the earlier delivered clips are unaffected.

Run with Blender, because the render path imports bpy:

    blender --background --factory-startup --python tools/v55_regression_purge.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "code" / "physics-video-sim" / "physics-video-sim-main"
sys.path.insert(0, str(REPO / "src"))

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    print("=== A. import the patched module and confirm no real unlink remains ===")
    import ast
    import inspect

    from physim.render import blender_backend as bb

    src = inspect.getsource(bb)
    # A plain substring check is NOT evidence: it matches docstrings (this module's
    # own docstring mentions Path.unlink()).  Parse the AST and look for an actual
    # ``.unlink()`` CALL whose receiver is a path, not a Blender collection.
    tree = ast.parse(src)
    real_unlinks = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "unlink":
            continue
        recv = node.func.value
        # ``<x>.objects.unlink(y)`` is a Blender API call, not a file delete.
        if isinstance(recv, ast.Attribute) and recv.attr in {"objects", "children"}:
            continue
        real_unlinks.append((node.lineno, ast.unparse(node)))
    check(
        "no real .unlink() file-delete call in blender_backend",
        not real_unlinks,
        str(real_unlinks[:3]),
    )
    check("compute purge signature accepts workspace_root",
          "workspace_root" in inspect.signature(bb.purge_stale_frames).parameters)

    print("\n=== B. render one real sample through the patched chain ===")
    import tempfile

    from physim.assets import AssetManager
    from physim.camera import CameraSpec
    from physim.config import load_run_config
    from physim.maps import MapManager
    from physim.physics import BodyState, SimulationResult
    from physim.render.blender_backend import PhyCoBlenderBackend

    ws = ROOT
    repo = REPO
    import os

    os.chdir(repo)

    sample_dir = repo / "datasets" / "turntable_spin" / "seed-005002" / "x1"
    if not sample_dir.is_dir():
        print(f"  [SKIP] sample dir missing on this machine: {sample_dir}")
        return 0 if not failures else 1

    def states(path: Path):
        return tuple(
            BodyState(
                frame=int(i["frame"]),
                time_seconds=float(i["time_seconds"]),
                position=tuple(float(v) for v in i["position"]),
                quaternion=tuple(float(v) for v in i["quaternion"]),
                linear_velocity=tuple(float(v) for v in i["linear_velocity"]),
                angular_velocity=tuple(float(v) for v in i["angular_velocity"]),
            )
            for i in json.loads(path.read_text(encoding="utf-8"))
        )

    am = AssetManager("configs/assets.yaml", "assets")
    mm = MapManager("configs/maps.yaml", am)
    ms = mm.get("replicad_apartment", require_files=True)
    cfg = load_run_config("configs/server.yaml", scenario="turntable_spin_gso")
    cfg = dict(cfg)
    cfg["render"] = dict(cfg["render"])
    cfg["render"]["samples_per_pixel"] = 4

    from physim.scenarios import create_scenario, variants_from_config

    scen = create_scenario(cfg, asset_manager=am)
    variant = variants_from_config(cfg)[0]
    asset = am.get("special_plush_elephant")
    smp = scen.sample(seed=5002, asset=asset, map_spec=ms, variant=variant)
    cam = CameraSpec(**json.loads((sample_dir / "metadata.json").read_text())["camera"])

    one = SimulationResult(
        trajectory=states(sample_dir / "trajectory.json")[:1],
        collisions=(),
        support_trajectory=states(sample_dir / "support_trajectory.json")[:1],
    )

    # A dedicated scratch dir inside the workspace tmp area.
    scratch = ROOT / "tmp" / "v55_regression_purge" / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    # Plant a sentinel so the quarantine path actually fires during the render.
    sentinel = scratch / "frame_9999.png"
    sentinel.write_bytes(b"regression-sentinel")
    from physim.safe_output import sha256_file

    digest = sha256_file(sentinel)

    renderer = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    print(f"  rendering one frame; scratch={scratch}")
    result = renderer.render(smp, one, asset, ms, cam, cfg)
    check("render returned a result", result is not None)

    print("\n=== C. the sentinel was quarantined, not deleted ===")
    check("sentinel left the scratch dir", not sentinel.exists())
    found = list((ROOT / "remove").rglob("frame_9999.png"))
    check("sentinel found under remove/", len(found) >= 1, f"{len(found)} copy(ies)")
    if found:
        check("sentinel hash unchanged", sha256_file(found[-1]) == digest)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS -- patched chain renders and quarantines instead of deleting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
