#!/usr/bin/env bash
# ===========================================================================
# Grid sweep over the two levers that the MEASUREMENT says matter:
#   * restitution  -- a polygonal hull loses energy at every facet-edge impact;
#                     an elastic impact loses less.  The manifest's own range is
#                     [0.05, 0.35], so values inside it are physical for this can.
#   * initial speed -- the slip transient is worst at low speed.
# Reports travel, speed ratio, relchg, slip ratio and VALID for each cell.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, copy, json
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1001
base_cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
asset = am.get("gso_whey_protein_vanilla")
ms = mm.get("replicad_apartment", require_files=True)

def measure(cfg, seed=seed):
    scen = create_scenario(cfg)
    v = next(x for x in variants_from_config(cfg) if x.multiplier == 1.0)
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    pos = np.asarray([s.position for s in res.trajectory], float)
    vel = np.asarray([s.linear_velocity for s in res.trajectory], float)
    om = np.asarray([s.angular_velocity for s in res.trajectory], float)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    d = vel[0, :2] / max(np.linalg.norm(vel[0, :2]), 1e-12)
    ax = np.array([-d[1], d[0], 0.0])
    oa = om @ ax
    vr = sp / smp.support_height
    mid = slice(len(sp)//4, 3*len(sp)//4)
    slip = float(np.nanmean(np.where(vr > 1e-9, oa/vr, np.nan)[mid]))
    return dict(
        v0=float(sp[0]), vend=float(sp[-1]),
        travel=float(np.linalg.norm(pos[-1]-pos[0])),
        relchg=float(rep.metrics.get("max_speed_relative_change", -1)),
        slip=slip, rest=float(smp.restitution), mu=float(smp.friction),
        zmin=float(pos[:,2].min()), zmax=float(pos[:,2].max()),
        valid=bool(rep.valid), reasons=list(rep.reasons),
        ext_ratio=float(rep.metrics.get("trajectory_extent_object_ratio", -1)),
    )

print("GS rest   scale   v0      v_end   travel  relchg  slip   ext    VALID")
best = None
for rest in (0.05, 0.145, 0.25, 0.35):
    for scale in (1.0, 2.0, 3.0, 4.0):
        cfg = copy.deepcopy(base_cfg)
        cfg["physics"] = {**cfg["physics"],
                          "restitution_range": [rest, rest],
                          "travel_object_extent_range": [4.0*scale, 7.0*scale]}
        try:
            m = measure(cfg)
        except Exception as e:
            print(f"GS {rest:.3f}  {scale:.1f}    ERROR {type(e).__name__}: {str(e)[:80]}")
            continue
        print(f"GS {rest:.3f}  {scale:.1f}    {m['v0']:.4f}  {m['vend']:.4f}  "
              f"{m['travel']:.4f}  {m['relchg']:.4f}  {m['slip']:.3f}  "
              f"{m['ext_ratio']:.2f}   {m['valid']} {m['reasons']}")
        key = (m['relchg'], -m['slip'])
        if m['valid'] and (best is None or key < best[0]):
            best = (key, rest, scale, m)
if best:
    print(f"GS BEST rest={best[1]} scale={best[2]} {json.dumps(best[3], default=str)}")
else:
    print("GS BEST none valid")
print("GS DONE")
PY
echo "RC GRID DONE"
