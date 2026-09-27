#!/usr/bin/env bash
# ===========================================================================
# Find the physics rate at which the rolling can's speed is FLATTEST.
#
# After fixing the timestep (Kubric never called setTimeStep, so a finer
# step_rate silently stretched simulated time), the residual speed drift is the
# competition between two numerical effects:
#   * coarse steps INJECT energy into rolling contact  (net speed rises)
#   * the hull's faceting REMOVES energy                (net speed falls)
# They cross over somewhere between 480 and 960 Hz.  This locates the flattest
# rate by measurement and reports the full speed profile shape, so "constant
# velocity" is an observed property and not a claim.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, copy
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

seeds = [int(a) for a in sys.argv[1:]] or [1001, 1002, 1003]
base = load_run_config("configs/server.yaml", scenario="rolling_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
asset = am.get("gso_whey_protein_vanilla")
ms = mm.get("replicad_apartment", require_files=True)

def run(fps, seed):
    cfg = copy.deepcopy(base)
    cfg["timing"] = {**cfg["timing"], "physics_fps": fps}
    scen = create_scenario(cfg)
    v = next(x for x in variants_from_config(cfg) if x.multiplier == 1.0)
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    pos = np.asarray([s.position for s in res.trajectory], float)
    vel = np.asarray([s.linear_velocity for s in res.trajectory], float)
    om = np.asarray([s.angular_velocity for s in res.trajectory], float)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    d = vel[0, :2]/max(np.linalg.norm(vel[0, :2]), 1e-12)
    oa = om @ np.array([-d[1], d[0], 0.0])
    vr = sp/smp.support_height
    mid = slice(len(sp)//4, 3*len(sp)//4)
    slip = float(np.nanmean(np.where(vr > 1e-9, oa/vr, np.nan)[mid]))
    return dict(v0=float(sp[0]), vend=float(sp[-1]),
                net=float(sp[-1]/sp[0]-1.0),
                relchg=float(rep.metrics.get("max_speed_relative_change", -1)),
                slip=slip, travel=float(np.linalg.norm(pos[-1]-pos[0])),
                valid=bool(rep.valid), reasons=list(rep.reasons), sp=sp)

print("PR fps  seed   v0      v_end   net_drift  relchg  slip   travel  VALID")
summary = {}
for fps in (480, 560, 640, 720, 800, 880):
    nets, rels, slips, oks = [], [], [], 0
    for seed in seeds:
        try:
            m = run(fps, seed)
        except Exception as e:
            print(f"PR {fps:4d} {seed} ERROR {type(e).__name__}: {str(e)[:90]}")
            continue
        nets.append(abs(m["net"])); rels.append(m["relchg"]); slips.append(m["slip"])
        oks += int(m["valid"])
        print(f"PR {fps:4d} {seed} {m['v0']:.5f} {m['vend']:.5f} "
              f"{m['net']:+.4f}    {m['relchg']:.4f}  {m['slip']:.4f} "
              f"{m['travel']:.4f}  {m['valid']} {m['reasons']}")
    if nets:
        summary[fps] = (float(np.mean(nets)), float(np.mean(rels)),
                        float(np.mean(slips)), oks)
print("PR ---- summary (mean over seeds) ----")
for fps, (net, rel, slip, oks) in sorted(summary.items(), key=lambda kv: kv[1][0]):
    print(f"PR fps={fps:4d} mean_abs_net_drift={net:.4f} mean_relchg={rel:.4f} "
          f"mean_slip={slip:.4f} valid={oks}/{len(seeds)}")
best = min(summary.items(), key=lambda kv: kv[1][0]) if summary else None
print(f"PR FLATTEST fps={best[0] if best else None}")

# speed profile shape at the flattest rate
if best:
    m = run(best[0], seeds[0])
    sp = m["sp"]
    print("PR profile (every 10th frame) at fps=%d seed=%d:" % (best[0], seeds[0]))
    print("PR  " + " ".join(f"{v:.4f}" for v in sp[::10]))
print("PR DONE")
PY
echo "RC PROFILE DONE"
