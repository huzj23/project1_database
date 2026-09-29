"""Measure the candidate real-box assets on the server for the domino chain (stage 08).

08 section 2 needs a thin, long, closed, stable-bottomed real package box with h/t about 3-8 and w/t
at least 1.5, where h is the standing height, t the thickness in the falling direction and w the
lateral width. Those ratios decide whether a box can be used to build a readable domino chain at all,
so this measures every candidate rather than assuming a name implies a shape.

For each asset it reads the collision mesh (or the visual mesh if no collision proxy exists) and
reports the axis-aligned dimensions plus the three ratios, then classifies the box against 08's
selection band. It also reports mesh size and whether the asset already has a collision proxy, since
08 requires every box in the chain to be a real dynamic rigid body with a proper collider.

Read-only. Writes `outcomes/v55/stage08/box_candidates.json` on the server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v55/stage08"
OUT.mkdir(parents=True, exist_ok=True)

print("=" * 100)
print(f"box candidate measurement for stage 08 domino chain")
print(f"  asset root {GSO}")

# Groups to consider. 08 wants a real package/media box: closed, flat-bottomed, thin and long.
GROUPS = {
    "pencil_case": ["Pencil_Case", "pencil"],
    "lunch_box": ["Lunch_Box"],
    "game_box": ["Cranium", "Game"],
    "lego_box": ["LEGO"],
    "snack_pack": ["Pack_n_Snack"],
    "tin_case": ["Case"],
}


def mesh_dims(path: Path) -> dict | None:
    """Dimensions of an OBJ, from its vertex extents. Avoids needing trimesh."""
    try:
        mn = [1e9] * 3
        mx = [-1e9] * 3
        n = 0
        with path.open("r", errors="replace") as fh:
            for line in fh:
                if not line.startswith("v "):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                except ValueError:
                    continue
                for i, v in enumerate((x, y, z)):
                    mn[i] = min(mn[i], v)
                    mx[i] = max(mx[i], v)
                n += 1
        if n == 0:
            return None
        return {"min": mn, "max": mx, "dims": [mx[i] - mn[i] for i in range(3)], "vertices": n}
    except Exception:
        return None


rows = []
for d in sorted(GSO.iterdir()):
    if not d.is_dir():
        continue
    coll = d / "collision_geometry.obj"
    vis = d / "visual_geometry.obj"
    src = coll if coll.is_file() else vis
    if not src.is_file():
        continue
    m = mesh_dims(src)
    if not m:
        continue
    dims = sorted(m["dims"])                    # t <= w <= h, the natural box convention
    t, w, h = dims[0], dims[1], dims[2]
    row = {
        "asset_id": d.name,
        "source": src.name,
        "has_collision_proxy": coll.is_file(),
        "collision_bytes": coll.stat().st_size if coll.is_file() else None,
        "visual_bytes": vis.stat().st_size if vis.is_file() else None,
        "dims_sorted_t_w_h_m": [round(v, 6) for v in (t, w, h)],
        "standing_height_m": round(h, 6),
        "thickness_m": round(t, 6),
        "width_m": round(w, 6),
        "h_over_t": round(h / t, 3) if t > 0 else None,
        "w_over_t": round(w / t, 3) if t > 0 else None,
        "vertices": m["vertices"],
    }
    # 08 section 2's selection band, evaluated rather than eyeballed.
    row["h_over_t_in_3_8"] = bool(row["h_over_t"] and 3.0 <= row["h_over_t"] <= 8.0)
    row["w_over_t_at_least_1_5"] = bool(row["w_over_t"] and row["w_over_t"] >= 1.5)
    row["suitable_for_domino"] = bool(row["h_over_t_in_3_8"] and row["w_over_t_at_least_1_5"]
                                      and row["has_collision_proxy"])
    rows.append(row)

rows.sort(key=lambda r: (not r["suitable_for_domino"], r["asset_id"]))
print(f"\n  {'asset_id':44s} {'coll':>5s} {'h':>8s} {'t':>8s} {'w':>8s} {'h/t':>7s} {'w/t':>6s} "
      f"{'ok':>4s}")
for r in rows:
    print(f"  {r['asset_id']:44s} {'yes' if r['has_collision_proxy'] else 'NO':>5s} "
          f"{r['standing_height_m']:8.4f} {r['thickness_m']:8.4f} {r['width_m']:8.4f} "
          f"{(r['h_over_t'] or 0):7.2f} {(r['w_over_t'] or 0):6.2f} "
          f"{'YES' if r['suitable_for_domino'] else '-':>4s}")

good = [r for r in rows if r["suitable_for_domino"]]
print(f"\n  {len(rows)} assets measured; {len(good)} satisfy 08 section 2's ratios AND have a "
      f"collision proxy")
if good:
    print(f"  suitable: {[r['asset_id'] for r in good][:12]}")
    best = min(good, key=lambda r: abs(r["h_over_t"] - 5.0))
    print(f"\n  closest to the middle of 08's band (h/t about 5): {best['asset_id']}")
    print(f"    standing height {best['standing_height_m']*1000:.1f} mm, "
          f"thickness {best['thickness_m']*1000:.1f} mm, width {best['width_m']*1000:.1f} mm")
    # 08 section 2: rough layout arithmetic with the real measured box.
    h, t = best["standing_height_m"], best["thickness_m"]
    for frac in (0.2, 0.3, 0.4):
        g = frac * h
        print(f"    gap {frac:.1f}*h = {g*1000:6.1f} mm -> 12 boxes span "
              f"{(12*t + 11*g)*1000:7.1f} mm end to end")
    print(f"    (08 section 2: total is 12*t + 11*g, plus a trigger approach and a run-out)")
    # Total chain length must fit the available clear region; report it for planning.
    for frac in (0.2, 0.3, 0.4):
        g = frac * h
        print(f"    with 0.40 m run-in and 0.60 m run-out at gap {frac:.1f}*h: "
              f"{(12*t + 11*g + 1.0):.3f} m of clear floor needed")

(OUT / "box_candidates.json").write_text(json.dumps({
    "note": ("measured dimensions of every GSO asset with a geometry file; 08 section 2 selects a "
             "thin, long, closed, flat-bottomed real package box with h/t 3-8 and w/t >= 1.5, and "
             "every chain box must have a proper collider"),
    "selection_band": {"h_over_t": [3.0, 8.0], "w_over_t_min": 1.5,
                       "requires_collision_proxy": True},
    "measured_count": len(rows), "suitable_count": len(good),
    "suitable": [r["asset_id"] for r in good],
    "assets": rows,
}, indent=2), encoding="utf-8")
print(f"\n  written: {OUT / 'box_candidates.json'}")
