"""Solve the V5.7 domino ARC on the real surveyed pavement, reusing the verified chain solver.

WHY THIS IS A SEPARATE ENTRY POINT
----------------------------------
`b2_chain.py` places a STRAIGHT chain: `build_placement` advances a single `x` coordinate and every box has
`yaw_deg = 0`. V5.7 requires a visibly curved C-shaped arc, and the boxes must rotate about the arc tangent
rather than about world X, so the placement geometry genuinely differs. Everything else -- the proxy assets,
the measured collision margin, the settle-and-verify step, the trigger, the toppling classification -- is
reused unchanged through `b2_chain`'s own functions, because those were verified in the previous round and
re-deriving them would discard working evidence.

WHAT IT DOES
------------
  * builds an arc placement from a measured site (centre, chord angle, radius) whose every box support was
    checked by ray cast against the declared floor;
  * runs `run_chain`-equivalent simulation through the same `World`/`place_and_settle`/trigger code;
  * verifies the settle, the centre-of-mass origin, the topple order and the no-trigger control;
  * writes a trajectory in the same schema the renderer already consumes.

The arc is expressed by giving each box its own (x, y, yaw), which the existing `World.add_box` already
supports through `baseOrientation`; the straight-line `build_placement` is the only part replaced.

Usage (on the server, inside tmux):
    python tools/v57/arc_solve.py --site site.json --out <run dir> \
        --proxies <dir> --proxy-report <json> --n 9 --arc-r 2.0 --spacing 0.155
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The solver may be staged inside a run directory (so the exact code travels with its result) while the
# shared, already-verified chain module lives in the repository's tools tree. Both locations are searched,
# the repository one first, and a clear error is raised if neither has it.
for cand in (ROOT / "tools" / "v56", Path("/data/raw/huzijian/project1_database/tools/v56")):
    if (cand / "b2_chain.py").is_file():
        sys.path.insert(0, str(cand))
        break
else:
    raise SystemExit("FATAL: b2_chain.py not found in " +
                     ", ".join(str(c / 'b2_chain.py') for c in
                               (ROOT / "tools" / "v56",
                                Path("/data/raw/huzijian/project1_database/tools/v56"))))

import b2_chain as C  # noqa: E402


def build_arc_placement(assets, order, gap_frac, site, arc_r, margin_m, target_pitch_m=None):
    """Lay `order` on a circular arc and return box records carrying their own yaw.

    The tangent yaw is the whole point: a box in a curve must be rotated to face along the path, and its
    thickness axis (the one it topples about) must align with that tangent. Leaving yaw at 0 would build a
    curved row of boxes all facing the same way, which is not a domino chain and would not transfer.

    SPACING -- two mutually exclusive modes, and the choice is recorded either way:

      * `target_pitch_m` given (the mode used for the approved preview): every pair gets the SAME
        centre-to-centre distance. The requested face gap is then `pitch - t_a/2 - t_b/2 - 2*margin`, i.e.
        the margin is subtracted so the SIMULATED centre pitch equals the approved number rather than
        drifting outboard by 2 mm. This is the mode the user approved on screen, and it also keeps the
        chain long enough (1.24 m) to hold the framing gate.
      * `target_pitch_m` None: per-pair pitch = t_a/2 + gap_frac*min(h_a,h_b) + t_b/2, the same rule the
        straight chain used.

    Both are reported, so which rule produced a given trajectory is never ambiguous.
    """
    chord = math.radians(site["chord_deg"])
    cx, cy = site["cx"], site["cy"]

    pitches = []
    for i in range(len(order) - 1):
        a = assets[order[i]]
        b = assets[order[i + 1]]
        if target_pitch_m is not None:
            # Invert gap_to_centre_pitch: choose the face gap that yields the requested CENTRE pitch.
            want_gap = target_pitch_m - a["thickness_m"] / 2.0 - b["thickness_m"] / 2.0 - 2.0 * margin_m
            gp = C.gap_to_centre_pitch(a, b, want_gap, margin_m)
            gp["pitch_mode"] = "uniform_centre_pitch"
            gp["centre_pitch_requested_m"] = target_pitch_m
        else:
            h_short = min(a["height_m"], b["height_m"])
            gp = C.gap_to_centre_pitch(a, b, gap_frac * h_short, margin_m)
            gp["pitch_mode"] = "per_pair_fraction_of_shorter_height"
        pitches.append(gp)
    cum = [0.0]
    for gp in pitches:
        cum.append(cum[-1] + gp["pitch_m"])
    total = cum[-1]

    phi0 = -total / (2.0 * arc_r)
    arc_cx = cx - arc_r * math.sin(phi0 + chord)
    arc_cy = cy + arc_r * math.cos(phi0 + chord)

    boxes, links = [], []
    for i, aid in enumerate(order):
        a = assets[aid]
        phi = phi0 + cum[i] / arc_r
        ang = chord + phi
        px = arc_cx + arc_r * math.sin(ang)
        py = arc_cy - arc_r * math.cos(ang)
        boxes.append({
            "index": i, "asset_id": aid, "asset": a,
            "x": px, "y": py,
            "z": a["height_m"] / 2.0,
            "yaw_deg": math.degrees(ang),
        })
        if i + 1 < len(order):
            b = assets[order[i + 1]]
            links.append({
                "from_index": i, "to_index": i + 1,
                "from_asset": aid, "to_asset": order[i + 1],
                "shorter_height_m": min(a["height_m"], b["height_m"]),
                "gap_fraction_of_shorter_height": gap_frac,
                "arc_step_deg": math.degrees(pitches[i]["pitch_m"] / arc_r),
                **pitches[i],
            })
    return boxes, links, {"arc_centre": [arc_cx, arc_cy], "phi0_deg": math.degrees(phi0),
                          "total_turn_deg": math.degrees(total / arc_r),
                          "chord_deg": site["chord_deg"], "chain_length_m": total,
                          "pitch_mode": pitches[0]["pitch_mode"] if pitches else None,
                          "pitch_m": [p["pitch_m"] for p in pitches]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="site json with cx, cy, chord_deg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--proxies", required=True)
    ap.add_argument("--proxy-report", required=True)
    ap.add_argument("--n", type=int, default=9)
    ap.add_argument("--arc-r", type=float, default=2.0)
    ap.add_argument("--gap-frac", type=float, default=0.25)
    ap.add_argument("--pitch-m", type=float, default=0.155,
                    help="uniform centre-to-centre pitch; this is the spacing the user approved on screen, "
                         "so the simulated chain matches the previewed one. Pass 0 to use the per-pair "
                         "fraction rule instead.")
    ap.add_argument("--trigger", default="real_box", choices=["real_box", "none"],
                    help="'real_box' topples box 0 with a fourth real asset, matching the straight chain")
    ap.add_argument("--trigger-gap", type=float, default=0.03,
                    help="face gap between the trigger and box 0, in metres")
    ap.add_argument("--trigger-factor", type=float, default=2.0)
    ap.add_argument("--density", type=float, default=C.DENSITY_DEFAULT)
    ap.add_argument("--margin-mm", type=float, default=1.0)
    ap.add_argument("--sim-s", type=float, default=6.0)
    ap.add_argument("--dt", type=float, default=1.0 / 480.0)
    ap.add_argument("--proxy-template", default="",
                    help="path template rebasing a proxy_obj onto the server's proxy dir")
    A = ap.parse_args()

    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)
    site = json.loads(Path(A.site).read_text(encoding="utf-8"))

    assets = C.load_assets(Path(A.proxy_report), Path(A.proxies) if A.proxies else None)
    if A.proxy_template:
        # The proxy report is written on Windows and read on Linux, so every proxy path is rebased onto
        # the server directory by basename. Without this the run dies on the first placement.
        for aid, a in assets.items():
            base = str(a["proxy_obj"]).replace("\\", "/").rsplit("/", 1)[-1]
            a["proxy_obj"] = A.proxy_template.replace("{basename}", base)

    # Cycle the three real assets so each appears equally often, which is what "3 distinct models, each
    # used several times" means for a 9-box chain. THE ORDER IS FIXED EXPLICITLY, and these exact names are
    # the module-level constants, because `b2_chain.THREE` is defined inside `main()` and does not exist as
    # a module attribute.
    # The order is Ouija first because that is the order in the approved preview image; leaving it to dict
    # iteration produced Cranium-first on the server, which would have simulated a different chain from the
    # one the user signed off.
    THREE = [C.ASSET_OUIJA, C.ASSET_TRIVIAL, C.ASSET_CRANIUM]
    order = [THREE[i % len(THREE)] for i in range(A.n)]
    # Trigger: a real fourth asset, the same one the straight chain used.
    trig_aid = next((k for k in assets if "LEGO" in k or "Calendar" in k), None)

    boxes, links, arc_meta = build_arc_placement(assets, order, A.gap_frac, site, A.arc_r,
                                                 A.margin_mm / 1000.0,
                                                 target_pitch_m=(A.pitch_m or None))
    print(f"arc: N={A.n} R={A.arc_r} pitch_mode={arc_meta['pitch_mode']} "
          f"turn={arc_meta['total_turn_deg']:.2f} deg length={arc_meta['chain_length_m']:.4f} m")
    print(f"  per-pair pitch: {[round(p, 4) for p in arc_meta['pitch_m']]}")
    for b in boxes:
        print(f"  box{b['index']} {b['asset_id'][:34]:34s} "
              f"({b['x']:+.4f},{b['y']:+.4f}) z {b['z']:.4f} yaw {b['yaw_deg']:+.2f}")

    result = {
        "schema": "v57.arc_solve/1",
        "site": site, "arc": arc_meta,
        "parameters": vars(A),
        "order": order,
        "n_boxes": A.n,
        "n_distinct_assets": len(set(order)),
        "assets_used": sorted(set(order)),
        "trigger_asset": trig_aid,
        "boxes": [{k: v for k, v in b.items() if k != "asset"} for b in boxes],
        "links": links,
    }

    # --- simulation, reusing the verified run_chain machinery ------------------------------------
    # A real-box trigger is a FOURTH real asset that topples box 0, matching the straight chain. The
    # trigger's own placement and spin axis are derived by `make_trigger` from box 0's yaw, so nothing
    # about the arc's direction has to be passed in here.
    trigger_spec = None
    if trig_aid and A.trigger == "real_box":
        trigger_spec = C.trigger_box_spec(
            assets, trig_aid, gap_m=A.trigger_gap,
            factor=A.trigger_factor, density=A.density)

    rec = C.run_chain(
        assets, order, [A.gap_frac] * (A.n - 1), A.density, A.margin_mm / 1000.0,
        support_z=0.0, x_start=boxes[0]["x"],
        trigger=("real_box" if trigger_spec else None), sim_s=A.sim_s, dt=A.dt,
        trajectory=True, arc_boxes=boxes, contact_log=(out / "contacts.jsonl"),
        trigger_spec=trigger_spec)

    result["simulation"] = {k: v for k, v in rec.items() if k != "trajectory_rows"}
    result["trajectory_rows"] = rec.get("trajectory_rows")
    result["boxes_toppled"] = rec.get("boxes_toppled")
    result["boxes_fallen"] = rec.get("boxes_fallen")
    result["all_toppled"] = rec.get("all_toppled")
    result["topple_order"] = rec.get("topple_order")
    result["is_sequential_chain"] = rec.get("is_sequential_chain")
    result["fatal"] = rec.get("fatal")

    print("")
    print("=== simulation ===")
    print(f"  boxes_toppled {rec.get('boxes_toppled')} / {A.n}")
    print(f"  boxes_fallen  {rec.get('boxes_fallen')} / {A.n}")
    print(f"  all_toppled   {rec.get('all_toppled')}")
    print(f"  topple_order  {rec.get('topple_order')}")
    print(f"  is_sequential_chain {rec.get('is_sequential_chain')}")
    if rec.get("fatal"):
        print(f"  FATAL: {rec['fatal']}")
    for row in rec.get("boxes", []):
        print(f"    box{row['index']} max_tilt {row['max_tilt_deg']:7.3f} deg  "
              f"tip {row['tip_angle_deg']:6.3f}  fallen {row['fallen']}  {row['final_verdict']}")

    (out / "arc_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'arc_result.json'}")
    return 0 if rec.get("all_toppled") else 3


if __name__ == "__main__":
    raise SystemExit(main())
