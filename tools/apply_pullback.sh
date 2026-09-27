#!/usr/bin/env bash
# The material hook works (disc R/B 0.99 -> 1.98 vs frozen 1.99), but my probe used
# guessed attribute names and got <<NO ATTRIBUTE>>.  Find the REAL field names so the
# documentation is accurate, then apply the pulled-back camera (k=1.5) to both
# turntable configs so the red-wood clips can be rendered.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== AssetSpec fields mentioning material/pbr ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys, dataclasses
sys.path.insert(0, "src")
from physim.assets import AssetSpec, AssetManager
names = [f.name for f in dataclasses.fields(AssetSpec)]
hits = [n for n in names if "pbr" in n.lower() or "material" in n.lower()]
print(f"  material-ish fields: {hits}")
for n in hits:
    f = [x for x in dataclasses.fields(AssetSpec) if x.name == n][0]
    print(f"    {n:28s} default={f.default!r}")
am = AssetManager("configs/assets.yaml", "assets")
a = am.get("turntable")
for n in hits:
    print(f"  turntable.{n} = {getattr(a, n, '?')!r}")
b = am.get("gso_sootheze_cold_therapy_elephant")
for n in hits:
    print(f"  elephant.{n}  = {getattr(b, n, '?')!r}  (must be empty/None)")
PY

echo
echo "=== apply camera pull-back k=1.5 to BOTH turntable configs ==="
"$WS/tools/conda_env/bin/python" - "$PWD" <<'PY'
import re, sys, os
LOOK = (0.4140, 0.1750, 0.8084)
D = (0.9340-0.4140, -0.4850-0.1750, 1.1784-0.8084)
K = 1.50
new = tuple(round(LOOK[i] + D[i]*K, 4) for i in range(3))
print(f"  look_at  = {LOOK}")
print(f"  new cam  = {new}  (distance {sum(d*d for d in D)**0.5*K:.4f} m)")
for f in ("configs/scenarios/turntable_carry_gso.yaml",
          "configs/scenarios/turntable_spin_gso.yaml"):
    s = open(f).read()
    if not os.path.isfile(f + ".pre_pullback"):
        open(f + ".pre_pullback", "w").write(s)
    s2, n1 = re.subn(r"^(\s*position:\s*)\[[^\]]*\]",
                     lambda m: f"{m.group(1)}[{new[0]}, {new[1]}, {new[2]}]",
                     s, count=1, flags=re.M)
    if n1 != 1:
        raise SystemExit(f"FATAL: position not substituted in {f} (n={n1})")
    open(f, "w").write(s2)
    print(f"  {f}: position -> {new}  (backup .pre_pullback)")
    # show the camera block
    for line in s2.splitlines():
        if any(k in line for k in ("policy:", "position:", "look_at:", "focal_length_mm:")):
            print(f"      {line.strip()}")
PY

echo
echo "=== YAML still parses ==="
"$WS/tools/conda_env/bin/python" -u -c "
import sys, yaml
sys.path.insert(0,'src')
for f in ('configs/scenarios/turntable_carry_gso.yaml','configs/scenarios/turntable_spin_gso.yaml'):
    c = yaml.safe_load(open(f))
    cam = c['camera']
    print(f'  {f}: policy={cam[\"policy\"]} pos={cam[\"position\"]} look={cam[\"look_at\"]}')
    from physim.config import load_run_config
" 2>&1 | tail -5
