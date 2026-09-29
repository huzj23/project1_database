"""Does the marginal small-gap failure follow from the trigger being close to critical?

The contact-speed comparison did NOT cleanly separate failures from successes (one success struck at
1.36 rad/s while one failure struck at 1.61 rad/s), so "the strike was too slow" is not a sufficient
explanation on its own. The other variable is the TRIGGER: at omega0 = 2.0 rad/s the striker is
barely above its own critical tipping speed for the thicker boxes, so it arrives at the target with
little rotational energy left regardless of the gap.

This checks the energy budget instead of the speed: the striker's kinetic energy AT FIRST CONTACT is
compared with the energy needed to raise the TARGET's centre of mass to its balance point. A failure
should then correspond to (available energy at contact) < (target's tipping barrier). That is a
physical criterion rather than a curve-fit, and it is evaluated from the recorded numbers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

TMP = Path(r"D:\workspace\project1_database\tmp")
chain = json.loads((TMP / "b_chain.json").read_text(encoding="utf-8"))
phys = json.loads((TMP / "box_physics_test.json").read_text(encoding="utf-8"))

spec = phys["spec"]
G = 9.81
DENSITY = 200.0

print("=" * 112)
print("ENERGY BUDGET at first contact: striker KE available vs the target's tipping barrier")
print("  barrier = m g (hypot(t,h) - h) / 2, the work needed to raise the target's COM over its edge")
print(f"\n  {'striker':10s} {'gap':>5s} {'w0':>5s} {'massA':>8s} {'omega@c':>8s} "
      f"{'KE_at_c_J':>10s} {'barrier_J':>10s} {'KE/barrier':>11s} {'B_topl':>6s}")

rows = []
for r in chain["contact_speed"]:
    aid = r["striker"]
    s = spec[aid]
    t, h = s["thickness_m"], s["height_m"]
    m_a = DENSITY * s["hull_volume_m3"]
    m_b = m_a                                   # same-asset pairs here
    # Rotational KE about the pivot edge: I_edge = m L^2 / 3, L = hypot(t, h)
    L = math.hypot(t, h)
    I_edge = m_a * L * L / 3.0
    w_c = r["striker_omega_at_first_contact_rad_s"]
    ke = 0.5 * I_edge * w_c * w_c if w_c is not None else None
    barrier = m_b * G * (L - h) / 2.0
    ratio = (ke / barrier) if (ke is not None and barrier > 0) else None
    rows.append({**r, "mass_A_kg": m_a, "KE_at_contact_J": ke, "target_barrier_J": barrier,
                 "KE_over_barrier": ratio})
    print(f"  {aid.split('_')[0][:10]:10s} {r['gap_fraction']:5.2f} {r['omega0_rad_s']:5.1f} "
          f"{m_a:8.4f} {str(w_c):>8s} {ke:10.5f} {barrier:10.5f} "
          f"{ratio if ratio else 0:11.3f} {str(r['target_toppled']):>6s}")

fails = [x for x in rows if not x["target_toppled"]]
succ = [x for x in rows if x["target_toppled"]]
print(f"\n  failures  : KE/barrier {[round(x['KE_over_barrier'],3) for x in fails]}")
print(f"  successes : KE/barrier min {min(x['KE_over_barrier'] for x in succ):.3f}, "
      f"max {max(x['KE_over_barrier'] for x in succ):.3f}")

# But note KE at contact ignores that the striker keeps rotating and pushing; the honest test is
# whether the ratio SEPARATES the two groups.
mx_fail = max(x["KE_over_barrier"] for x in fails) if fails else None
mn_succ = min(x["KE_over_barrier"] for x in succ)
print(f"\n  max KE/barrier among failures : {mx_fail:.3f}")
print(f"  min KE/barrier among successes: {mn_succ:.3f}")
print(f"  ratio separates the groups    : {bool(mx_fail is not None and mx_fail < mn_succ)}")
print("  (if it does not separate, the marginal failure is a threshold effect with overlap, and the")
print("   honest reading is that at omega0=2.0 and a SMALL gap the strike is borderline rather than")
print("   that a specific single mechanism explains it)")

# Trigger margin: how far above critical each trigger is.
print("\n" + "=" * 112)
print("TRIGGER MARGIN vs the marginal failures (w_crit from b_tipping_math)")
print(f"  {'asset':42s} {'w_crit':>8s} {'w0=2.0':>8s} {'ratio':>7s} {'w0=3.0':>8s} {'ratio':>7s}")
for aid, s in spec.items():
    t, h = s["thickness_m"], s["height_m"]
    L = math.hypot(t, h)
    w_crit = math.sqrt(3 * G * (L - h) / (L * L))
    print(f"  {aid:42s} {w_crit:8.4f} {2.0:8.2f} {2.0/w_crit:7.2f} {3.0:8.2f} {3.0/w_crit:7.2f}")
print("\n  every marginal failure occurred at omega0 = 2.0, which is only 1.06-1.36x w_crit for the")
print("  two thicker boxes and 2.2x for the thin Ouija box -- and Ouija indeed never failed. So the")
print("  failures track the trigger's proximity to critical, not the gap alone.")

out = {
    "note": __doc__.strip().splitlines()[0],
    "rows": rows,
    "max_KE_over_barrier_among_failures": mx_fail,
    "min_KE_over_barrier_among_successes": mn_succ,
    "energy_ratio_separates": bool(mx_fail is not None and mx_fail < mn_succ),
    "failure_trigger_margins_above_w_crit": {
        aid: {"w_crit_rad_s": round(math.sqrt(3 * G * (
            math.hypot(s["thickness_m"], s["height_m"]) - s["height_m"])
            / math.hypot(s["thickness_m"], s["height_m"]) ** 2), 4),
            "ratio_at_omega0_2": round(2.0 / math.sqrt(3 * G * (
                math.hypot(s["thickness_m"], s["height_m"]) - s["height_m"])
                / math.hypot(s["thickness_m"], s["height_m"]) ** 2), 3)}
        for aid, s in spec.items()},
}
Path(r"D:\workspace\project1_database\outcomes\v56\mixed_box_domino").mkdir(parents=True,
                                                                            exist_ok=True)
Path(r"D:\workspace\project1_database\outcomes\v56\mixed_box_domino\b_energy.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8")
print("\nwritten: outcomes/v56/mixed_box_domino/b_energy.json (local)")
