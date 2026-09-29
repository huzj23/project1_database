"""V5.5 stage 05: the bottle's real silhouette, measured densely, and what it implies.

Every attempt so far has been designed against a wrong picture of this bottle, so this script
measures it once, properly, and states the consequence.

Two measurement errors are being corrected:

  * the stage-05 design used `r_max` = 63.55 mm, the largest RADIAL distance over all heights. But
    a vertically falling box contacts the surface whose reach toward the approach direction first
    equals the offset, and the reach in a GIVEN direction is what matters, not the radial maximum;
  * an earlier profile returned 0.000 mm for most height bands because it used the proxy's 208
    VERTICES, which leaves most bands empty. Sampling points ON THE TRIANGLES is dense at every
    height.

The script prints, for the bottle in its settled pose, the reach in +y per height band, the height
at which the widest point occurs, and whether the top cap is narrower than the flank. Those three
numbers decide whether a vertical drop can ever produce a tipping moment: if the cap is as wide as
the flank, a box falling from above lands on the cap (a flat, non-tipping contact) and only a
genuine side impact can tip the bottle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

CODE = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/"
            "physics-video-sim-main/src")
sys.path.insert(0, str(CODE))

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
WORK = OUT / "geometry"
FLOOR_Z = 0.510600


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def sample_triangles(V, F, n=40, seed=7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    u = rng.random((len(F), n))
    v = rng.random((len(F), n))
    flip = u + v > 1.0
    u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
    w = 1.0 - u - v
    pts = (a[:, None, :] * u[:, :, None] + b[:, None, :] * v[:, :, None]
           + c[:, None, :] * w[:, :, None])
    return pts.reshape(-1, 3)


def main() -> int:
    # Use stage 03's FINAL acceptance record, which is the one whose `all_pass` is true. The older
    # `proxy_decision.json` names `hull` for the two glasses while the final record names `vhacd`,
    # and for an OPEN CUP 03 section 4 disqualifies the closed hull -- so measuring against the
    # legacy entry would profile the wrong geometry. For glass_b the difference is decisive: the
    # hull's cap reach equals its widest reach, so the band between them is degenerate and no side
    # strike can be aimed at all, which is exactly what the first search observed.
    fin = json.loads((SCENES / "proxy_acceptance_final.json").read_text(encoding="utf-8"))
    legacy = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    decision = {}
    for n in ("bottle_assembly", "glass_a", "glass_b"):
        ch = fin["props"][n]["chosen"]
        decision[n] = {"chosen": ch, "recentre_offset_m": legacy[n]["recentre_offset_m"],
                       "triangles": fin["props"][n]["candidates"][ch]["triangles"],
                       "allowed": fin["props"][n]["allowed"]}
        if legacy[n]["chosen"] != ch:
            print(f"  note: {n}: proxy_decision.json says '{legacy[n]['chosen']}', the final "
                  f"acceptance record says '{ch}' -> using '{ch}'")
    WORK.mkdir(parents=True, exist_ok=True)
    summary = {}
    print("=" * 96)
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        d = decision[name]
        vs, fs, off = [], [], 0
        for f in sorted((PROPS / name / d["chosen"]).glob("*.obj")):
            v, fc = load_obj(f)
            vs.append(v)
            fs.append(fc + off)
            off += len(v)
        V, F = np.vstack(vs), np.vstack(fs)
        restore = -np.asarray(d["recentre_offset_m"], float)
        origin = np.array([restore[0], restore[1], FLOOR_Z - V.min(axis=0)[2]])
        W = V + origin
        pts = sample_triangles(V, F) + origin

        z_lo, z_hi = pts[:, 2].min(), pts[:, 2].max()
        # The support footprint: the lowest 2 mm of the mesh.
        base = pts[pts[:, 2] <= z_lo + 0.002]
        axis = np.array([base[:, 0].mean(), base[:, 1].mean()])
        base_r = float(np.max(np.hypot(base[:, 0] - axis[0], base[:, 1] - axis[1])))

        NB = 60
        edges = np.linspace(z_lo, z_hi, NB + 1)
        prof = []
        for i in range(NB):
            sel = (pts[:, 2] >= edges[i]) & (pts[:, 2] <= edges[i + 1])
            if not sel.any():
                continue
            dx = pts[sel, 0] - axis[0]
            dy = pts[sel, 1] - axis[1]
            prof.append({
                "z_mid": float(0.5 * (edges[i] + edges[i + 1])),
                "z_lo": float(edges[i]), "z_hi": float(edges[i + 1]),
                "n": int(sel.sum()),
                "r_max": float(np.max(np.hypot(dx, dy))),
                "reach_plus_y": float(dy.max()), "reach_minus_y": float(-dy.min()),
                "reach_plus_x": float(dx.max()), "reach_minus_x": float(-dx.min()),
            })
        r_max = max(p["r_max"] for p in prof)
        widest = max(prof, key=lambda p: p["r_max"])
        # The cap: the top band. Its reach is what a vertically falling box meets first.
        cap = prof[-1]
        r_at = {}
        for z in (z_lo + 0.02, z_lo + 0.05, z_hi - 0.02, z_hi - 0.005):
            b = min(prof, key=lambda p: abs(p["z_mid"] - z))
            r_at[f"z={z:.4f}"] = b["reach_plus_y"]
        summary[name] = {
            "axis_xy": axis.tolist(), "base_z": float(z_lo), "top_z": float(z_hi),
            "height_m": float(z_hi - z_lo), "max_radial_m": float(r_max),
            "widest_z_m": float(widest["z_mid"]),
            "cap_reach_plus_y_m": float(cap["reach_plus_y"]),
            "cap_band_z_m": [float(cap["z_lo"]), float(cap["z_hi"])],
            "base_footprint_radius_m": base_r,
            "reach_plus_y_at": {k: float(v) for k, v in r_at.items()},
            "profile": prof,
        }
        print(f"\n=== {name} (proxy {d['chosen']}, {len(V)} v / {len(F)} t) ===")
        print(f"  axis ({axis[0]:.6f}, {axis[1]:.6f})  base {z_lo:.5f}  top {z_hi:.5f}  "
              f"height {z_hi-z_lo:.4f} m")
        print(f"  max radial {r_max*1000:.3f} mm at z={widest['z_mid']:.5f}; "
              f"base footprint radius {base_r*1000:.3f} mm")
        print(f"  TOP CAP band z {cap['z_lo']:.5f}..{cap['z_hi']:.5f}: "
              f"reach(+y) {cap['reach_plus_y']*1000:.3f} mm, r_max {cap['r_max']*1000:.3f} mm")
        print(f"  -> the cap is "
              f"{'AS WIDE AS' if cap['reach_plus_y'] > 0.9*widest['reach_plus_y'] else 'NARROWER THAN'} "
              f"the widest flank "
              f"({cap['reach_plus_y']*1000:.1f} vs {widest['reach_plus_y']*1000:.1f} mm)")
        print(f"\n     z_mid   reach+y  reach-y  reach+x  reach-x    r_max")
        for p in prof[::2]:
            print(f"   {p['z_mid']:8.5f} {p['reach_plus_y']*1000:8.2f} "
                  f"{p['reach_minus_y']*1000:8.2f} {p['reach_plus_x']*1000:8.2f} "
                  f"{p['reach_minus_x']*1000:8.2f} {p['r_max']*1000:8.2f}")

    (OUT / "prop_geometry_dense.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'prop_geometry_dense.json'}")

    print("\n" + "=" * 96)
    print("=== CONSEQUENCE FOR THE STRIKE ===")
    b = summary["bottle_assembly"]
    print(f"  the bottle's cap reach(+y) is {b['cap_reach_plus_y_m']*1000:.2f} mm and its widest "
          f"reach(+y) is ")
    w = max(p["reach_plus_y"] for p in b["profile"])
    print(f"  {w*1000:.2f} mm, a difference of only {(w-b['cap_reach_plus_y_m'])*1000:.2f} mm.")
    print("  A box released above the top therefore meets the CAP over almost the whole offset")
    print("  range, and a flat cap contact cannot tip the bottle. The leverage must come from the")
    print("  box's leading EDGE catching the flank below the cap, which needs the offset to sit in")
    print("  the narrow band between the cap reach and the widest reach, AND the box to arrive")
    print("  with real speed rather than resting against the surface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
