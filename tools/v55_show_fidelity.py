"""Summarise the proxy-fidelity report: where the worst first-hit deviations are."""

from __future__ import annotations

import json
from pathlib import Path

P = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat/"
         "proxy_fidelity.json")
d = json.loads(P.read_text(encoding="utf-8"))

for name, r in d.items():
    print("=" * 70)
    print(f"== {name}  visual_triangles={r['visual_triangles']}")
    for key, p in r["proxies"].items():
        print(f"   {key:9s} tri={p['triangles']:5d} "
              f"max={p['max_first_hit_deviation_m']*1000:9.4f} mm "
              f"p95={p['p95_first_hit_deviation_m']*1000:8.4f} mm "
              f"mean={p['mean_first_hit_deviation_m']*1000:7.4f} mm "
              f"holes={p['hole_rays']}")
        for label in ("downward_approaches", "horizontal_approaches", "upward_approaches"):
            s = p[label]
            mx = s.get("max_m")
            print(f"       {label:24s} rays={s.get('rays'):5d} "
                  f"max={('%.4f mm' % (mx*1000)) if mx is not None else 'n/a'}")
        print("       worst rays:")
        for w in p["worst_rays"][:5]:
            print(f"         dev={w['deviation_m']*1000:9.4f} mm {w['approach']:11s} "
                  f"cos_down={w['cos_down']:+.3f} t_vis={w['t_visual_m']:.5f} "
                  f"t_prox={w['t_proxy_m']:.5f}")
    print(f"   chosen: {r['chosen']}")
