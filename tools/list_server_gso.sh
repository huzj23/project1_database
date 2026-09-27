#!/usr/bin/env bash
# Which GSO objects made it to the server, and what are their dimensions?
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

"$PY" - "$WS/models/gso" <<'PY'
import json, os, sys
root = sys.argv[1]
rows = []
for name in sorted(os.listdir(root)):
    dj = os.path.join(root, name, "data.json")
    if not os.path.isfile(dj):
        continue
    try:
        d = json.load(open(dj))
        b = d["kwargs"]["bounds"]
        dx, dy, dz = (b[1][i] - b[0][i] for i in range(3))
        rows.append((name, d["metadata"].get("category") or "-",
                     dx, dy, dz, -b[0][2], d["kwargs"].get("mass")))
    except Exception:
        pass

print(f"GSO objects on server: {len(rows)}")
print()
print("=== isotropic-ish, 8-40 cm (good single actor) ===")
for n, c, dx, dy, dz, rest, m in sorted(rows, key=lambda r: -max(r[2], r[3], r[4])):
    mx, mn = max(dx, dy, dz), min(dx, dy, dz)
    if 0.08 < mx < 0.40 and mn / mx > 0.72:
        print(f"  {n[:56]:56s} {c[:14]:14s} "
              f"{dx:.3f}x{dy:.3f}x{dz:.3f}  rest_z={rest:.3f}  m={m:.4f}")
PY
