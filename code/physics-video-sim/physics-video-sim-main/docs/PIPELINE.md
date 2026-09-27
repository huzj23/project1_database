# Physics video generation pipeline

## 1. Terminology and order

- **Scenario**: a motion law/configuration such as `rolling`.
- **Map**: one visual environment plus semantic support regions.
- **Asset**: one simulated object with aligned visual/collision representations.
- **Group**: samples sharing one seed and initial image.
- **Variant**: one controlled-variable member inside a group.

The only supported execution order is:

```text
load config
→ sample map and asset
→ sample legal surface and initial/external conditions
→ PyBullet simulate
→ scenario validation
→ trajectory-aware camera
→ Blender render
→ save modalities and ground truth
```

Blender rendering must never start before physics validation passes.

## 2. Determinism and random sampling

Every random choice derives from the group seed:

- map and asset;
- legal surface and spawn location;
- initial resting orientation from asset metadata;
- initial linear/angular velocity;
- mass, friction, restitution, gravity/force parameters;
- camera side and world-Z azimuth offset.

For the same resolved config, Scenario, and seed, these values must reproduce.

`camera.policy: trajectory_side` is the default. It derives a useful side view
from the simulated reference trajectory and then samples a limited azimuth orbit
around world Z. `camera.policy: random` samples the full azimuth range while
still looking at and framing the trajectory.

## 3. Controlled-variable groups

Scenario YAML may declare:

```yaml
controlled_variants:
  variable: initial_speed
  multipliers: [1.0, 0.5, 1.5]
  labels: [x1, x0.5, x1.5]
```

All variants in a group share:

- seed, map, environment, asset and material;
- support region, spawn position and initial orientation;
- all nuisance physical parameters;
- lighting and camera.

Only the named variable and physically dependent quantities change (for
example, pure-rolling angular velocity scales with controlled linear speed).
The camera is computed from the simulated
largest-extent reference variant and reused for every member, so the initial
view remains identical and every variant remains in frame.

Supported controlled variables currently include initial speed, constant force,
gravity, and restitution. Do not vary drop height when strict identical initial
images are required.

The production defaults are 1280×720, 16 fps, and exactly 81 frames. The three
standard variants mean:

| Scenario | x0.5 / x1 / x1.5 controls | Physically required dependent change |
|---|---|---|
| `rolling` | initial linear speed | pure-rolling angular speed |
| `constant_force` | constant external force | acceleration resolved by Bullet |
| `free_fall` | gravity magnitude | no initial-state change |

Map, asset, spawn pose, mass, friction, restitution, nuisance velocities,
lighting, and camera stay fixed within the group.

## 4. Simulator boundary

Scenario code supplies only simulation conditions:

```text
collision geometry
initial position and orientation
initial linear and angular velocity
mass, friction, rolling/spinning friction, restitution
gravity
constant force or future constraints
```

PyBullet integrates all later states and contacts. It is forbidden to prescribe
the desired per-frame trajectory, repeatedly reset velocity to fake uniform
motion, or repair a failed bounce after simulation.

The physics sampling rate is normally 240 Hz and the saved/render trajectory is
sampled at video FPS.

## 5. Current scenarios

### `rolling` — near-uniform translation/rolling

- starts supported on a legal floor/table region;
- selects spherical assets in the baseline configuration so the declared
  pure-rolling state matches the collision geometry;
- samples planar velocity and matching pure-rolling angular velocity;
- applies no driving force;
- uses zero configured rolling/spinning drag for near-uniform speed;
- validates support, bounds, travel, trajectory/object ratio, and maximum speed
  change.

### `constant_force` — uniformly accelerated motion

- starts supported with a sampled initial planar velocity;
- samples a constant acceleration magnitude and converts it to `F = m a`;
- registers one persistent world-space force with PyBullet;
- never replaces Bullet velocity/position during integration;
- validates support, travel, force response, and acceleration consistency.

### `free_fall` — drop, collision, rebound

- samples a safe XY location and height above a support surface;
- samples small horizontal/vertical and angular initial velocities;
- applies gravity only;
- requires a real contact event and positive post-contact upward velocity;
- validates drop distance, penetration, bounds, bounce, speed, and
  trajectory/object ratio.

## 6. Assets

Object layout:

```text
assets/objects/<category>_<name>/
├── source/                 # untouched original download
├── visual/model.glb        # normalized runtime visual
├── collision/model.obj     # low-poly collision where required
├── collision/model.urdf
├── asset.yaml
└── license/
```

Environment layout:

```text
assets/environments/<name>/
├── source/
├── visual/scene.blend
├── collision/surfaces/<region>.obj
├── collision/surfaces/<region>.urdf
├── asset.yaml
└── license/
```

Only `sphere`, `cylinder`, `cube`, and `cone` may use primitive collisions.
Other dynamic objects use low-poly mesh/URDF collision. A hollow cup cannot use
a solid convex hull; use a compound wall/base/handle representation.

Asset `initial_orientation` records ordinary resting semantics. A cup rests on
its base with its opening up; an elongated fruit rests on its stable short-axis
support. `support_height` and `footprint_radius` must be recomputed in that pose.

## 7. Map regions

`configs/maps.yaml` references environments by asset ID and declares semantic
surface groups. A region records type, object-size range, bounds/polygon,
height, normal, cleanliness, optional sampling overrides, and collision files.

- register the largest practical region on a continuous clean floor;
- split around obstacles to use the rest of a large map;
- do not include clutter, holes, or geometry outside the support surface;
- require `cleanliness: verified_clear` and record the verification method;
- use a box only for a truly flat rectangular support;
- extract mesh collision for curved/irregular surfaces such as shaped desks.

Future collision scenarios must additionally load every obstacle that can be
contacted; a clean support-only proxy is sufficient only when the legal region
guarantees no obstacle interaction.

## 8. Validation and framing

Before rendering, common validation checks finite states, maximum speed, XY
bounds, and:

```text
trajectory_extent / object_extent <= configured maximum
```

The camera uses both the complete reference trajectory and the largest object
extent. It fits horizontal and vertical trajectory spans against the real image
aspect ratio and enforces minimum/maximum projected object fractions. If the
complete path cannot fit without making the object too small, the sample is
rejected; the camera is not moved arbitrarily far away.

When visibility requires a viewpoint change, orbit around world Z first.
Increasing downward pitch is a fallback.

## 9. Rendering and output

Blender loads the same environment/asset metadata, preserves authored lighting,
applies the validated PyBullet trajectory as keyframes, and renders configured
modalities. It does not run another physics solver.

The default production renderer is Cycles at 128 samples per pixel with adaptive
sampling, denoising, a 0.01 noise threshold, and explicit reflection,
transmission, transparency, and volume bounce limits. Lower-quality smoke-test
overrides must use a separate machine/test config rather than weakening these
defaults.

```text
datasets/<scenario>/seed-<seed>/<variant>/
├── rgb/
├── depth/
├── segmentation/
├── video.mp4
├── trajectory.json         # includes derived acceleration
├── collisions.json
├── metadata.json
└── config.yaml
```

Metadata records Scenario, seed, variant, map/surface, asset, initial/external
conditions, camera/reference variant, validation metrics, renderer diagnostics,
and source/license hashes.

## 10. Adding a Scenario

1. Add `configs/scenarios/<scenario>.yaml`.
2. Add `src/physim/scenarios/<scenario>.py` implementing seeded condition
   sampling.
3. Register it in `create_scenario()`.
4. Add its validator to `validate_sample()`.
5. Add only the physics hook genuinely needed by the new conditions.
6. Reuse AssetManager, MapManager, SurfaceSampler, PyBulletBackend, Camera,
   BlenderBackend, DatasetWriter, and batch runner.
7. Add deterministic/unit tests and run one server smoke sample before batching.

Do not copy the pipeline or renderer for each motion type.
