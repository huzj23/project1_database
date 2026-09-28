"""V5.5 stage 03 section 2: generate the missing review image for Big_Dot_Aqua_Pencil_Case.

`outcomes/v5_asset_review/objects/` holds 84 images at 1920x1440, and every already-approved
asset has one EXCEPT `Big_Dot_Aqua_Pencil_Case`.  03 section 2 requires the selection to be
verified against the actual image and forbids inferring the scanned form from the product
name, so shipping this asset without an image would leave its visual-acceptance basis empty.

Rather than excuse the gap, this renders a comparable multi-view from the asset's REAL
geometry: the visual mesh shaded, the shipped collision mesh overlaid, and an orthographic
silhouette on each axis.  That is strictly more informative than a single beauty shot for
deciding whether the proxy matches the visual.

Written into a v55 output directory, never into the existing review tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path("/data/raw/huzijian/project1_database")
ASSET = ROOT / "models/gso/Big_Dot_Aqua_Pencil_Case"
OUT = ROOT / "outcomes/v55/assets/review"
OUT.mkdir(parents=True, exist_ok=True)

VIS = ASSET / "visual_geometry.obj"
COLL = ASSET / "collision_geometry.obj"


def load(path: Path) -> trimesh.Trimesh:
    return trimesh.load(str(path), process=True, force="mesh")


def add_mesh(ax, mesh: trimesh.Trimesh, color, alpha, stride=1):
    tri = mesh.vertices[mesh.faces[::stride]]
    coll = Poly3DCollection(tri, facecolor=color, edgecolor="none", alpha=alpha)
    ax.add_collection3d(coll)


def main() -> int:
    visual = load(VIS)
    collision = load(COLL)

    vd = (visual.bounds[1] - visual.bounds[0]).tolist()
    cd = (collision.bounds[1] - collision.bounds[0]).tolist()
    print(f"visual   : {len(visual.vertices)} v / {len(visual.faces)} tri dims={[round(v,5) for v in vd]}")
    print(f"collision: {len(collision.vertices)} v / {len(collision.faces)} tri dims={[round(v,5) for v in cd]} "
          f"watertight={collision.is_watertight}")

    fig = plt.figure(figsize=(16, 12), dpi=120, facecolor="white")

    # --- three shaded views from different directions ---
    views = [
        ("front (looking -Y)", 0, -90),
        ("side (looking +X)", 20, 0),
        ("top (looking -Z)", 80, -90),
    ]
    for i, (title, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(2, 3, i, projection="3d")
        # Collision proxy drawn first in translucent orange, visible mesh in blue on top.
        add_mesh(ax, collision, "#ff7f0e", 0.35)
        add_mesh(ax, visual, "#1f77b4", 0.85, stride=3)
        center = visual.bounds.mean(axis=0)
        radius = float(np.max(visual.extents)) * 0.62
        ax.set_xlim(center[0] - radius, center[0] + radius)
        ax.set_ylim(center[1] - radius, center[1] + radius)
        ax.set_zlim(center[2] - radius, center[2] + radius)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(f"{title}\nblue=visual  orange=collision proxy", fontsize=9)
        ax.tick_params(labelsize=6)
        ax.set_xlabel("x", fontsize=7)
        ax.set_ylabel("y", fontsize=7)
        ax.set_zlabel("z", fontsize=7)

    # --- three orthographic silhouettes: does the proxy match on each axis? ---
    for i, (axis, label) in enumerate((("x", "YZ"), ("y", "XZ"), ("z", "XY")), start=4):
        ax = fig.add_subplot(2, 3, i)
        keep = [j for j in range(3) if j != "xyz".index(axis)]
        v2 = visual.vertices[:, keep]
        c2 = collision.vertices[:, keep]
        ax.scatter(v2[:, 0], v2[:, 1], s=0.4, c="#1f77b4", label="visual", alpha=0.5)
        ax.scatter(c2[:, 0], c2[:, 1], s=1.2, c="#ff7f0e", label="collision", alpha=0.6)
        # The proxy's bounding box, which is what actually contacts.
        lo, hi = collision.bounds[0][keep], collision.bounds[1][keep]
        ax.plot([lo[0], hi[0], hi[0], lo[0], lo[0]],
                [lo[1], lo[1], hi[1], hi[1], lo[1]], c="red", lw=1.0, label="proxy bbox")
        ax.set_title(f"silhouette {label} (project along {axis})", fontsize=9)
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=6)
        ax.legend(fontsize=6)

    dim_err = [abs(cd[j] - vd[j]) for j in range(3)]
    fig.suptitle(
        f"Big_Dot_Aqua_Pencil_Case  (missing from v5_asset_review, generated in V5.5)\n"
        f"visual dims {[round(v,4) for v in vd]} m   collision dims {[round(v,4) for v in cd]} m   "
        f"axis errors {[round(e,5) for e in dim_err]} m   "
        f"proxy watertight={collision.is_watertight}",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    png = OUT / "Big_Dot_Aqua_Pencil_Case_review.png"
    fig.savefig(png, dpi=120)
    plt.close(fig)
    print(f"written: {png} ({png.stat().st_size} bytes)")

    (OUT / "Big_Dot_Aqua_Pencil_Case_review.json").write_text(json.dumps({
        "asset_id": "Big_Dot_Aqua_Pencil_Case",
        "why_generated": (
            "no image exists in outcomes/v5_asset_review/objects/, so the visual-acceptance "
            "basis required by stage 03 section 2 was empty; this renders the real geometry"
        ),
        "visual": {"triangles": int(len(visual.faces)),
                   "dimensions_m": [round(v, 9) for v in vd],
                   "watertight": bool(visual.is_watertight)},
        "collision": {"triangles": int(len(collision.faces)),
                      "dimensions_m": [round(v, 9) for v in cd],
                      "watertight": bool(collision.is_watertight)},
        "axis_errors_m": [round(e, 9) for e in dim_err],
        "max_axis_error_m": round(max(dim_err), 9),
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
