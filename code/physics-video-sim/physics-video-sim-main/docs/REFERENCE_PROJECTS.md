# Kubric and PhyCo-Sim reuse notes

## Fixed references

| Project | Upstream | Role |
| --- | --- | --- |
| Kubric | <https://github.com/google-research/kubric> | scene abstractions, assets, metadata helpers, Blender/PyBullet adapters |
| PhyCo-Sim | <https://github.com/nnsriram97/phyco-sim> | maintained Kubric fork, rigid-body simulation extensions, renderer/batch examples |

The checked-out revisions are recorded by Git/submodule state. Do not silently
mix a renderer from one Blender generation with another project's binary or
Python runtime; validate the exact combination with a minimal official sample.

## Installation model

PhyCo-Sim's setup uses a Blender-bundled Python matching its documented Blender
baseline and installs its vendored Kubric plus PyBullet, OpenEXR, OpenCV, and
scenario dependencies into that runtime. Keep this official server baseline
working before attempting a Blender upgrade.

Local desktop Blender is for GUI inspection. It may use a separate,
repository-local Python package directory under `cache/runtime/`; do not modify
the system Python environment merely to support preview.

## Reuse boundaries

| Capability | Reuse | Project-owned layer |
| --- | --- | --- |
| Scene and assets | Kubric `Scene`, primitives, `FileBasedObject` | YAML manifests and `AssetManager` |
| Physics | PhyCo-Sim/Kubric `PyBullet.run()` and contact extraction | initial conditions, persistent forces, normalized results |
| Rendering | PhyCo-Sim/Kubric Blender renderer and passes | scene construction, lighting policy, camera, diagnostics |
| Metadata and images | Kubric serialization helpers | stable dataset schema and resolved config |
| Batch ideas | PhyCo-Sim process/GPU launchers | scenario-neutral isolated worker scheduler |

Do not copy large scenario files from PhyCo-Sim. They combine asset loading,
sampling, physics, rendering, and metadata in scenario-specific code. This
project instead keeps only motion-specific sampling and validation inside each
Scenario.

## Physics rules

The simulator receives:

- collision bodies;
- initial position/orientation;
- initial linear/angular velocity;
- mass, friction, restitution, gravity;
- optional forces, torques, and constraints.

It then integrates the trajectory. Project code must not overwrite object state
each simulation step to make an intended curve appear. A constant-force sample
uses PhyCo-Sim's persistent force hook; free-fall bounce is produced by gravity,
contact, and restitution.

The useful reusable output is the render-frame trajectory plus contact events.
Validation remains project-owned because upstream examples commonly log or
continue after an unsuitable motion instead of rejecting it before rendering.

## Renderer rules

Reuse the upstream Blender renderer for RGB, depth, segmentation, and future
flow passes. Blender receives the completed PyBullet transforms as animation
keyframes and does not run a second physical simulation.

Preserve authored environment lights and World. If a fixed-seed inspection
finds them insufficient, add Sun + one Area in the environment manifest; add a
multi-Area rig only when the first supplement is still insufficient.

## Compatibility

The server and desktop Blender versions may differ. Asset normalization records
axis/scale compensation in manifest metadata, and all combinations require a
fixed-seed visual check. Keep compatibility shims in project adapters rather
than editing `third_party/`.

Machine-specific verification results, hosts, users, and absolute output paths
are retained separately in `REFERENCE_PROJECTS_xienan.md`.
