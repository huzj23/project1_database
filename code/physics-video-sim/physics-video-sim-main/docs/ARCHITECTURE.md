# Architecture

## Module boundaries

| Module | Responsibility | Must not own |
| --- | --- | --- |
| Asset | discover manifests, resolve safe paths, validate visual/collision/physics ranges | Scenario sampling |
| Map | attach semantic, clean support regions to environment assets | object-specific motion |
| SurfaceSampler | select a compatible region and legal spawn/path envelope | Blender or Bullet calls |
| Scenario | sample only motion-specific initial/external conditions | asset paths, rendering, trajectory scripting |
| Physics | translate a generic sample to PyBullet bodies/forces and normalize results | desired path correction |
| Validation | common and Scenario-specific acceptance checks | render-time fixes |
| Camera | frame a simulated reference trajectory and object size | scene generation |
| Render | load visuals/lights and keyframe completed physics states | physical integration |
| IO | stable modality/video/metadata layout | sampling decisions |
| Batch | isolated Blender processes, seeds, GPUs, retry accounting | Scenario logic |

## Runtime dependency direction

```text
environment profile + scenario config
              │
              ▼
      AssetManager / MapManager
              │
              ▼
       Scenario registry ──→ SurfaceSampler
              │
              ▼
         ScenarioSample
              │
              ▼
        PyBulletBackend
              │
              ▼
       SimulationResult
          │          │
          ▼          ▼
    Validation     Camera
          │          │
          └────┬─────┘
               ▼
       PhyCoBlenderBackend
               │
               ▼
          DatasetWriter
```

`ScenarioSample` is the stable boundary between sampling and physics. It
contains conditions, not a trajectory. `SimulationResult` is the stable
boundary shared by validation, camera, rendering, preview, and IO.

## Scenario extension

The registry currently maps:

```text
rolling        → RollingScenario + validate_rolling
constant_force → ConstantForceScenario + validate_constant_force
free_fall      → FreeFallScenario + validate_free_fall
```

This deliberately small registry avoids a premature inheritance hierarchy.
When a fourth rigid-body Scenario is added, it normally needs one sampler, one
validator, and possibly one explicit physics condition hook. Common body,
surface, render, and output construction remain unchanged.

For future multi-body scenarios, extend the sample boundary to a collection of
body initial states and constraints; do not introduce a scenario-specific
renderer. Soft-body/fluid simulation may require another physics adapter but
should still return the same render-facing trajectory/result abstraction.

## Controlled variants

A group seed selects the map, asset, surface, spawn pose, nuisance physics, and
camera randomness. Each variant replays the same deterministic sampling and
then scales only the configured variable. The largest expected variant is
simulated as the camera reference, and that camera is reused throughout the
group.

This design gives controlled comparisons without storing or replaying a hidden
set of hard-coded coordinates.

## Batch isolation

`scripts/generate_batch.py` launches Blender subprocesses. Each group is bound
to one visible GPU; a process generates its configured variants and exits.
Process isolation prevents Blender/Python global state and GPU allocations from
leaking between groups. Failed groups do not count toward the requested total;
later candidate seeds replace them up to an explicit attempt limit.

The environment variable selecting a GPU is set before Blender starts. Batch
workers do not choose GPUs inside Scenario code.

## Upstream reuse

The project reuses the unmodified PhyCo-Sim Kubric fork for `Scene`, primitives,
URDF-backed `FileBasedObject`, `PyBullet.run()`, contacts, Blender rendering,
and image writers. Project-side adapters handle manifests, conditions,
validation, camera policy, output schema, and compatibility shims.

No source below `third_party/` is modified.

## Preview consistency

Server simulation bundles contain resolved config, trajectory, collisions,
metadata, variant, and camera. Local GUI preview validates the same sampled
conditions and loads the recorded `SimulationResult` and `CameraSpec`; it does
not create a second random scene or a synthetic replacement trajectory.
