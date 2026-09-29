"""Report the measured render cost and decide the delivery tier (V5.6 section 8).

Reads whichever cost measurements exist under `outcomes/v56/` and prints them side by side against
the section 8.2 budget formula, so the tier decision is arithmetic on measured numbers rather than an
impression. Also folds in the hard constraint that the two videos need different frame counts and
that the remaining wall-clock time is a fixed budget.

    python tools\\v56\\report_budget.py [--remaining-hours 21.0]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\workspace\project1_database")
V56 = ROOT / "outcomes/v56"

TIER_NOTES = {
    "960x540": "diagnostic only per section 8.1 -- NOT deliverable as a final video",
    "1280x720": "deliverable floor per section 8.1 (16-24 spp + fixed denoise)",
    "1600x900": "higher tier if the budget allows",
    "1920x1080": "higher tier if the budget allows",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remaining-hours", type=float, default=None)
    ap.add_argument("--a-frames", type=int, default=96)
    ap.add_argument("--b-frames", type=int, default=120)
    A = ap.parse_args()

    if A.remaining_hours is None:
        deadline = datetime(2026, 9, 30, 14, 0)
        A.remaining_hours = (deadline - datetime.now()).total_seconds() / 3600.0
    print("=" * 100)
    print(f"V5.6 section 8 budget  |  remaining {A.remaining_hours:.2f} h  |  "
          f"A={A.a_frames} frames, B={A.b_frames} frames, total {A.a_frames + A.b_frames}")

    found = []
    for p in sorted(V56.glob("**/cost_measurement.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        found.append((p, d))
    if not found:
        print("no cost measurements found")
        return 1

    print(f"\n{'measurement':44s} {'tier':16s} {'first_s':>9s} {'marg_s':>9s} {'total_h':>8s} "
          f"{'fits':>5s}")
    print("-" * 100)
    rows = []
    for p, d in found:
        rel = str(p.relative_to(V56))
        for t in d["tiers"]:
            spf = t["marginal_seconds_per_frame"]
            total = 1.25 * (A.a_frames + A.b_frames) * spf / 3600.0 + 2.0
            fits = total <= A.remaining_hours
            rows.append({"source": rel, "tier": t["tier"], "spf": spf, "first": t["first_frame_seconds"],
                         "total_h": total, "fits": fits, "res": t["resolution"], "spp": t["spp"],
                         "settings": d.get("resolution_independent_settings", {})})
            print(f"{rel:44s} {t['tier']:16s} {t['first_frame_seconds']:9.2f} {spf:9.2f} "
                  f"{total:8.2f} {'YES' if fits else 'no':>5s}")

    # Prefer the tier with the highest resolution that fits, because section 8.1 says to choose the
    # highest tier that passes on quality AND budget -- not the cheapest one.
    fitting = [r for r in rows if r["fits"]]
    print(f"\n=== section 8.1 decision ===")
    if not fitting:
        print("  NO MEASURED TIER FITS THE REMAINING TIME. Section 8.2's reduction order applies:")
        print("  disable unneeded fog/composite outputs -> reuse persistent_data -> lower spp ->")
        print("  lower resolution while keeping object pixel size -> cut to the physically necessary")
        print("  interval -> reduce B to 8-10 boxes. It may NOT become a still image, lose the")
        print("  contact segment, change the replay timeline, or reduce model/collision correctness.")
        return 1

    # Rank by pixel count (resolution), then by spp, among the fitting ones.
    fitting.sort(key=lambda r: (r["res"][0] * r["res"][1], r["spp"]), reverse=True)
    best = fitting[0]
    print(f"  highest tier that fits: {best['tier']}  ({best['res'][0]}x{best['res'][1]} at "
          f"{best['spp']} spp)")
    print(f"    measured marginal {best['spf']:.2f} s/frame, projected total {best['total_h']:.2f} h "
          f"of {A.remaining_hours:.2f} h  (headroom {A.remaining_hours - best['total_h']:+.2f} h)")
    print(f"    settings: {json.dumps(best['settings'])}")
    print()
    for r in rows:
        note = TIER_NOTES.get(r["tier"].split("x")[0] if "x" in r["tier"] else r["tier"], "")
        print(f"    {r['tier']:16s} {'FITS' if r['fits'] else 'over'}  {r['total_h']:6.2f} h  "
              f"{'<- CHOOSE' if r is best else '':10s} {note}")

    # The headroom matters more than the raw pass, because the physics is not finished and a
    # re-render of even a few frames costs hours at these rates.
    print(f"\n=== risk note ===")
    head = A.remaining_hours - best["total_h"]
    print(f"  headroom is {head:+.2f} h. At {best['spf']:.0f} s/frame, {head * 3600 / best['spf']:.0f}")
    print(f"  extra frames could be rendered in that headroom, and a single full re-render of one")
    print(f"  video would need {A.b_frames * best['spf'] / 3600:.2f} h. If headroom is below that, a")
    print(f"  re-render is NOT affordable and the first render must be correct, which raises the")
    print(f"  importance of the 5-key-image check BEFORE the full render.")

    (V56 / "budget_decision.json").write_text(json.dumps({
        "remaining_hours": A.remaining_hours, "a_frames": A.a_frames, "b_frames": A.b_frames,
        "rows": rows, "chosen": best,
        "formula": "total = 1.25 * (A_frames + B_frames) * marginal_seconds_per_frame + 2 h tail",
        "headroom_hours": head,
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {V56 / 'budget_decision.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
