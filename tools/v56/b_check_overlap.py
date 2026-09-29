"""Check whether the 0.02h control was invalid because the two proxies already touched.

At gap 0.02h the striker rotated only ~6-7 deg for two assets, which looks like a capability failure
but is more likely a setup artefact: the collision hulls are slightly larger than the visual meshes,
so at a gap of only 5.5 mm the two bodies may already be in contact before the trigger. The
`settle_contacts_between_a_and_b` field (measured before any trigger) settles it from the data
rather than by argument, and the hull's effective half-thickness is derived from the recorded
contact distance.
"""

from __future__ import annotations

import json
from pathlib import Path

TMP = Path(r"D:\workspace\project1_database\tmp")
phys = json.loads((TMP / "box_physics_test.json").read_text(encoding="utf-8"))

print("=" * 104)
print("Did the two boxes already touch BEFORE the trigger? (settle_contacts_between_a_and_b)")
print(f"\n  {'asset':42s} {'case':18s} {'gap_mm':>8s} {'gap/ownT':>9s} {'preContacts':>12s} "
      f"{'A_tip':>7s} {'contact':>7s} {'B_topl':>6s}")
for aid in phys["summary"]:
    for c in phys["cases"]:
        if c.get("striker") != aid or c.get("target") != aid:
            continue
        if c.get("case") not in ("two_box", "two_box_reach_control"):
            continue
        t = c["striker_thickness_m"]
        pre = c.get("settle_contacts_between_a_and_b")
        print(f"  {aid:42s} {c['case'][:18]:18s} {c['gap_m']*1000:8.2f} "
              f"{c['gap_m']/t:9.3f} {str(pre):>12s} {c['striker_max_tilt_deg']:7.2f} "
              f"{str(c['contact_between_a_and_b_made']):>7s} {str(c['target_toppled']):>6s}")

print("\n" + "=" * 104)
print("Effective hull half-thickness implied by the recorded pre-trigger contact, vs the mesh:")
print("  if the hulls touched at gap g, then sum of the two half-thicknesses = gap + ... ")
for aid in phys["summary"]:
    for c in phys["cases"]:
        if (c.get("striker") == aid and c.get("target") == aid
                and c.get("case") == "two_box_reach_control"):
            t = c["striker_thickness_m"]
            g = c["gap_m"]
            pre = c.get("settle_contacts_between_a_and_b")
            print(f"  {aid:42s} mesh thickness {t*1000:8.3f} mm  gap {g*1000:6.2f} mm  "
                  f"pre-trigger contacts {pre}")

print("\n" + "=" * 104)
print("Where the gap sweep sits in absolute terms (mm) and as a multiple of own thickness:")
print(f"  {'asset':42s} {'t_mm':>8s} " + " ".join(f"{f:>10.2f}" for f in (0.15, 0.25, 0.35)))
for aid, s in phys["summary"].items():
    t = s["dims_m_t_w_h"][0]
    h = s["dims_m_t_w_h"][2]
    vals = " ".join(f"{f*h*1000:10.2f}" for f in (0.15, 0.25, 0.35))
    print(f"  {aid:42s} {t*1000:8.3f} {vals}")
print("  (own thickness shown so the gap can be read as a fraction of the box's own dimension too)")
