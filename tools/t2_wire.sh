#!/usr/bin/env bash
# ===========================================================================
# T2 DAMPING WIRING: 5 small edits, no third_party changes.
#
#   1. ScenarioSample: add linear_damping / angular_damping (default 0.0, so every
#      existing scenario is byte-for-byte unaffected)
#   2. pybullet_backend.changeDynamics: pass the two coefficients
#   3. scenarios/__init__.py: register the "damping" factory entry
#   4. validation/__init__.py: add validate_damping + dispatch
#   5. install scenarios/damping.py and configs/scenarios/damping_gso.yaml
#
# Damping is a Bullet solver parameter, so the motion remains genuinely simulated:
# we set the coefficient once and Bullet integrates the exponential decay.  Probe 2
# measured the usable band: k=0.4 decays cleanly and monotonically, k>=1.2 stops
# the body immediately.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

for f in src/physim/scenarios/__init__.py src/physim/physics/pybullet_backend.py \
         src/physim/validation/__init__.py; do
  cp "$f" "$WS/tmp/$(basename $f).t2.bak"
done

echo "=== 1) ScenarioSample: add damping fields ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "src/physim/scenarios/__init__.py"
s = open(p).read()
old = """    constant_force: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:"""
new = """    constant_force: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Bullet's velocity attenuation coefficients.  Default 0.0 keeps every
    # pre-existing scenario unchanged; only the `damping` scenario sets them.
    linear_damping: float = 0.0
    angular_damping: float = 0.0

    def to_dict(self) -> dict[str, Any]:"""
assert old in s, "ScenarioSample anchor not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("  ScenarioSample extended")
PY

echo
echo "=== 2) pybullet_backend: pass the damping coefficients ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "src/physim/physics/pybullet_backend.py"
s = open(p).read()
old = """                spinningFriction=sample.spinning_friction,
                restitution=sample.restitution,
            )"""
new = """                spinningFriction=sample.spinning_friction,
                restitution=sample.restitution,
                # Velocity attenuation, integrated by the solver.  Zero for every
                # scenario that does not declare it, so this is inert elsewhere.
                linearDamping=float(getattr(sample, "linear_damping", 0.0)),
                angularDamping=float(getattr(sample, "angular_damping", 0.0)),
            )"""
assert old in s, "changeDynamics anchor not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("  changeDynamics now passes damping")
PY

echo
echo "=== 3) scenario factory: register damping ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "src/physim/scenarios/__init__.py"
s = open(p).read()
old = """    if scenario_name == "free_fall":
        from physim.scenarios.free_fall import FreeFallScenario

        return FreeFallScenario(config)
    raise KeyError(f"Unknown scenario {scenario_name!r}")"""
new = """    if scenario_name == "free_fall":
        from physim.scenarios.free_fall import FreeFallScenario

        return FreeFallScenario(config)
    if scenario_name == "damping":
        from physim.scenarios.damping import DampingScenario

        return DampingScenario(config)
    raise KeyError(f"Unknown scenario {scenario_name!r}")"""
assert old in s, "factory anchor not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("  factory registers 'damping'")
PY

echo
echo "=== 4) validator: add validate_damping + dispatch ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "src/physim/validation/__init__.py"
s = open(p).read()

validator = '''

def validate_damping(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    """Validate exponentially attenuated motion.

    Damping is exponential (v = v0 * exp(-k*t)), unlike Coulomb friction which is
    linear and reaches zero in finite time.  The checks therefore are:

      * the speed must DECREASE monotonically (a damping coefficient that fails to
        act would leave it constant; an unstable contact would make it rise)
      * the final speed must be a real fraction of the initial speed -- strictly
        between the two extremes, proving attenuation happened without the body
        simply being stopped by an impact
      * the body must stay on the support, and travel far enough to be visible
    """
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    if config.get("reject_initial_overlap", True):
        initial_bottom = float(positions[0, 2] - sample.support_height)
        if initial_bottom < float(surface.position[2]) - 0.005:
            reasons.append("initial_surface_penetration")

    object_extent = max(2.0 * sample.radius, 2.0 * sample.support_height)
    minimum_travel = max(
        float(config.get("min_travel_distance", 0.0)),
        float(config.get("min_travel_object_extent_ratio", 0.0)) * object_extent,
    )
    if metrics["travel_distance"] < minimum_travel:
        reasons.append("insufficient_travel")
    if config.get("require_supported", True) and metrics["supported_fraction"] < 0.9:
        reasons.append("not_supported")

    planar_speeds = np.linalg.norm(velocities[:, :2], axis=1)
    initial_speed = float(planar_speeds[0])
    final_speed = float(planar_speeds[-1])
    if initial_speed <= 1e-9:
        reasons.append("no_initial_motion")
        decay_ratio = 1.0
    else:
        decay_ratio = final_speed / initial_speed
        # Attenuation must actually occur.
        if decay_ratio > float(config.get("max_decay_ratio", 0.95)):
            reasons.append("insufficient_damping")
        # ...but the body must not be arrested almost immediately, which would mean
        # the coefficient is so large the motion is a stop rather than a decay.
        if decay_ratio < float(config.get("min_decay_ratio", 0.02)):
            reasons.append("over_damped")
        # Monotonic decay: allow a small tolerance for contact jitter.
        rises = np.diff(planar_speeds) > float(config.get("speed_rise_tolerance", 0.02))
        if int(np.count_nonzero(rises)) > int(config.get("max_speed_rises", 3)):
            reasons.append("non_monotonic_decay")

    # Compare against the analytic exponential the coefficient implies.  This is a
    # measurement of the solver's behaviour, not a prescribed trajectory: a large
    # deviation means damping is not the mechanism producing the motion.
    expected_ratio = float(
        np.exp(-float(getattr(sample, "linear_damping", 0.0))
               * float(result.trajectory[-1].time_seconds))
    )
    metrics["damping_decay_ratio"] = decay_ratio
    metrics["damping_expected_ratio"] = expected_ratio
    metrics["damping_ratio_error"] = abs(decay_ratio - expected_ratio)
    if config.get("max_decay_ratio_error") is not None:
        if metrics["damping_ratio_error"] > float(config["max_decay_ratio_error"]):
            reasons.append("damping_decay_mismatch")
    return _report(reasons, metrics)

'''

anchor = "\n\ndef validate_sample("
assert anchor in s, "validate_sample anchor not found"
s = s.replace(anchor, validator + "\ndef validate_sample(", 1)

old = """    if sample.scenario == "free_fall":"""
new = """    if sample.scenario == "damping":
        return validate_damping(result, sample, surface, config)
    if sample.scenario == "free_fall":"""
assert old in s, "dispatch anchor not found"
s = s.replace(old, new, 1)
open(p, "w").write(s)
print("  validate_damping added + dispatched")
PY

echo
echo "=== 5) install the scenario module ==="
cp "$WS/tools/damping.py" src/physim/scenarios/damping.py
sed -i 's/\r$//' src/physim/scenarios/damping.py
echo "  installed src/physim/scenarios/damping.py"

echo
echo "=== 6) import + dispatch check ==="
"$WS/tools/conda_env/bin/python" -c "
import sys; sys.path.insert(0,'src')
import inspect
from physim.scenarios import ScenarioSample, create_scenario
from physim.scenarios.damping import DampingScenario
from physim.validation import validate_damping
print('  ScenarioSample has linear_damping:', 'linear_damping' in ScenarioSample.__dataclass_fields__)
print('  ScenarioSample has angular_damping:', 'angular_damping' in ScenarioSample.__dataclass_fields__)
print('  DampingScenario importable:', DampingScenario.__name__)
print('  validate_damping importable:', validate_damping.__name__)
import physim.physics.pybullet_backend as pb
src = inspect.getsource(pb)
print('  backend passes linearDamping:', 'linearDamping=float(getattr(sample' in src)
" 2>&1 | sed 's/^/  /'
