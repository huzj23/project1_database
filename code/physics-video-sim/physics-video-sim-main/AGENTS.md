# AGENTS.md

## Project goal

Build a reproducible physics-video generation pipeline on Kubric, PhyCo-Sim,
PyBullet, and Blender. The shared pipeline is:

```text
sample → simulate → validate → camera → render → save
```

Supported rigid-body scenarios currently are `rolling`, `constant_force`, and
`free_fall`. New scenarios must implement only motion-specific sampling and
validation; do not copy the renderer, asset loader, map loader, physics scene
construction, or metadata writer.

## Repository rules

- Upstream references live in `third_party/kubric` and `third_party/phyco-sim`.
- Do not modify `third_party/` unless a project-side adapter cannot solve the
  problem and the reason is documented first.
- Keep Asset, Map, SurfaceSampler, Scenario, Physics, Validation, Camera,
  Render, and IO separated.
- Scenario code receives resolved `AssetSpec` and `MapSpec`; it must not build
  absolute asset paths or hard-code map coordinates.
- All random choices derive from the group seed.
- Controlled-variable variants share the group seed, map, asset, spawn pose,
  sampled nuisance variables, lighting, and camera. Only the declared variable
  and physically required dependent quantities change.
- The physics adapter receives collision geometry, initial state, physical
  properties, gravity, force, and constraints. Never prescribe the simulated
  trajectory frame by frame.
- Validate before Blender rendering. Reject invalid samples instead of repairing
  their trajectories.
- Keep trajectories reasonably sized relative to the object and enforce a
  minimum projected object size in camera framing.
- Local GUI preview and server rendering use the same Scenario, config,
  manifests, seed, simulation result, camera, and Blender scene builder.

## Assets and maps

- Preserve original downloads in each asset's `source/` directory.
- Runtime object visuals normally use `visual/model.glb`; complex environments
  normally use `visual/scene.blend` so authored materials, lights, and World can
  be preserved.
- Only sphere, cylinder, cube, and cone categories may use primitive collision.
  Other dynamic objects require a low-poly collision mesh/URDF. Hollow or
  concave dynamic objects require a compound of convex parts.
- Initial orientation must match ordinary resting semantics. Recompute
  `support_height` and `footprint_radius` for that orientation.
- Map regions must be verified clear. Cover a large clean surface with the
  largest practical region; use multiple smaller regions around obstacles.
- Curved or irregular support surfaces require extracted static mesh collision.
- Preserve authored lighting. If it is insufficient, add Sun + one Area first;
  use multiple Area lights only if that remains insufficient.

## Development workflow

1. Read relevant code and reference-project implementations.
2. Make the smallest reusable project-side change.
3. Run unit and static checks.
4. Run one fixed-seed physics/render smoke sample per changed Scenario.
5. Only then start multi-sample or multi-GPU generation.
6. Report actual results and limitations; never claim an unexecuted test passed.

Machine-specific hosts, users, absolute paths, and recovery notes belong in
`*_xienan.md` files, not in the generic documents.
