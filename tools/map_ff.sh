#!/usr/bin/env bash
# Which free_fall seeds are 自由落体 (#3) and which are 抛体 (#4)?
# Both write into datasets/free_fall/ because projectile is a free_fall config
# variant, so the distinction must come from the recorded config.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, json, os
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
print(f"  {'sample':34s} {'scenario':14s} {'h_speed':>8s} {'asset':44s}")
for d in sorted(glob.glob(REPO + "/datasets/free_fall/seed-*/x1")):
    rel = d.replace(REPO + "/datasets/", "")
    cfgp = os.path.join(d, "config.yaml")
    hs = "-"
    if os.path.isfile(cfgp):
        import yaml
        try:
            c = yaml.safe_load(open(cfgp))
            pr = (c.get("physics") or {})
            hs = pr.get("horizontal_speed_range") or pr.get("horizontal_speed") or "-"
        except Exception as e:
            hs = f"err"
    m = os.path.join(d, "metadata.json")
    aid = sc = "?"
    if os.path.isfile(m):
        j = json.load(open(m))
        sc = j.get("scenario")
        a = j.get("asset") or {}
        aid = a.get("asset_id") or a.get("id") or str(list(a.keys()))
    print(f"  {rel:34s} {str(sc):14s} {str(hs):>8s} {str(aid):44s}")

print()
print("  --- config.yaml scenario block, seed-003001 vs seed-004001 ---")
for s in ("003001", "004001"):
    p = f"{REPO}/datasets/free_fall/seed-{s}/x1/config.yaml"
    if os.path.isfile(p):
        import yaml
        c = yaml.safe_load(open(p))
        print(f"    seed-{s}: scenario={c.get('scenario')} "
              f"asset_ids={c.get('selection',{}).get('asset_ids')}")
        print(f"      physics={ {k:v for k,v in (c.get('physics') or {}).items() if 'speed' in k or 'angle' in k} }")
PY

echo
echo "=== material subagent progress (any new modules?) ==="
ls -la src/physim/render/ | sed 's/^/  /'
echo "  --- material refs in asset.yaml ---"
grep -n 'material' -A 4 assets/objects/turntable/asset.yaml | sed 's/^/  /' || echo "  none yet"
echo "  --- model.obj/mtl restored? ---"
echo "    usemtl lines: $(grep -c '^usemtl' assets/objects/turntable/visual/model.obj)"
echo "    mtl size: $(wc -c < assets/objects/turntable/visual/model.mtl)"
echo "  --- ttp2/matcmp logs ---"
tail -3 "$WS/tmp/matcmp.log" 2>/dev/null | sed 's/^/    /'
