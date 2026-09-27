# Project structure

The finalized first-stage layout is:

```text
physics-video-sim/
├── AGENTS.md                         # generic contributor/agent rules
├── AGENTS_xienan.md                  # optional local-only operator notes
├── README.md                         # generic setup and commands
├── README_xienan.md                  # optional local-only operator workflow
├── pyproject.toml                    # Python package and dev dependencies
├── .gitignore                        # excludes binary assets/generated data
│
├── configs/
│   ├── assets.yaml                   # manifest roots; assets auto-discovered
│   ├── maps.yaml                     # maps, surface groups, clean regions
│   ├── local.yaml                    # desktop profile; set Blender path locally
│   ├── server.yaml                   # server profile; set paths/GPU IDs locally
│   └── scenarios/
│       ├── rolling.yaml              # uniform rolling + speed variants
│       ├── constant_force.yaml       # persistent force + force variants
│       └── free_fall.yaml            # drop/bounce + gravity variants
│
├── assets/
│   ├── README.md                     # naming/preprocessing/collision rules
│   ├── objects/
│   │   └── sphere_basketball/        # one concrete object example
│   │       ├── source/original.glb   # untouched download (Git ignored)
│   │       ├── visual/model.glb      # normalized render visual (Git ignored)
│   │       ├── collision/model.obj   # optional low-poly collision
│   │       ├── collision/model.urdf  # optional Bullet entry
│   │       ├── license/README.md      # provenance/license note
│   │       └── asset.yaml            # tracked asset manifest
│   ├── environments/
│   │   └── classroom/                # one concrete environment example
│   │       ├── source/original.blend # untouched source (Git ignored)
│   │       ├── visual/scene.blend    # normalized render scene (Git ignored)
│   │       ├── collision/surfaces/
│   │       │   ├── student_desk_a.obj
│   │       │   └── student_desk_a.urdf
│   │       ├── license/README.md
│   │       └── asset.yaml
│   ├── materials/                    # future reusable material manifests/files
│   └── hdri/                         # HDR/EXR manifests/files
│
├── src/physim/
│   ├── config.py                     # YAML loading and deterministic deep merge
│   ├── pipeline.py                   # generic orchestration and group camera
│   ├── reference.py                  # safe loading of vendored Kubric
│   ├── preview.py                    # non-rendered GUI guide objects
│   ├── assets/__init__.py            # AssetSpec/AssetManager
│   ├── maps/
│   │   ├── __init__.py               # MapSpec/SurfaceSpec/MapManager
│   │   └── surface_sampler.py        # legal deterministic surface sampling
│   ├── scenarios/
│   │   ├── __init__.py               # ScenarioSample, variants, registry
│   │   ├── common.py                 # shared sampling helpers
│   │   ├── rolling.py                # rolling-specific conditions
│   │   ├── constant_force.py         # force-specific conditions
│   │   └── free_fall.py              # drop-specific conditions
│   ├── physics/
│   │   ├── __init__.py               # BodyState/SimulationResult
│   │   └── pybullet_backend.py       # generic body/surface/force adapter
│   ├── validation/__init__.py        # common and scenario validators
│   ├── camera/__init__.py            # trajectory/object-aware camera
│   ├── render/
│   │   ├── __init__.py               # RenderResult
│   │   └── blender_backend.py        # shared Blender scene and passes
│   └── io/__init__.py                # images, MP4, GT, metadata, config
│
├── scripts/
│   ├── generate.py                   # one sample or one variant group
│   ├── generate_batch.py             # isolated multi-seed/multi-GPU scheduler
│   ├── enumerate_rolling.py          # rolling asset/map sampling visual audit
│   ├── preview_blender.py            # local GUI launcher
│   ├── blender_preview_scene.py      # shared-scene Blender preview worker
│   ├── export_preview_simulation.py  # server trajectory bundle export
│   ├── fetch_assets.py               # download explicitly configured assets
│   ├── setup_blender_preview.py      # repository-local Blender Python runtime
│   ├── prepare_visual_asset.py       # visual normalization
│   ├── generate_collision_mesh.py    # dynamic low-poly collision generation
│   ├── generate_hollow_cup_collision.py
│   ├── generate_environment_surface_collision.py
│   ├── inspect_glb.py
│   ├── inspect_blend_asset.py
│   ├── check_blender.py
│   └── blender_smoke_test.py
│
├── tests/
│   ├── test_asset_manager.py
│   ├── test_rolling_framework.py
│   └── test_scenarios.py
│
├── docs/
│   ├── ARCHITECTURE.md               # boundaries and extension strategy
│   ├── PIPELINE.md                   # authoritative behavior/principles
│   ├── PROJECT_STRUCTURE.md          # this file
│   ├── REFERENCE_PROJECTS.md         # generic upstream reuse notes
│   ├── REFERENCE_PROJECTS_xienan.md  # optional local-only verification notes
│   ├── SERVER.md                     # generic deployment checklist
│   └── SERVER_xienan.md              # optional local-only host/recovery notes
│
├── third_party/
│   ├── kubric/                       # upstream reference, unchanged
│   └── phyco-sim/                    # upstream reference, unchanged
│
├── datasets/                         # generated ground truth/videos, ignored
├── outputs/                          # reports/previews, ignored
├── cache/                            # runtime/scratch/download cache, ignored
└── logs/                             # batch logs, ignored
```

## Placement rules

- Do not add a top-level directory for each Scenario.
- Do not place environment assets below `assets/objects`.
- Do not store concrete asset paths inside Scenario source.
- Do not create scenario-specific render or IO implementations.
- Store large data inside the repository tree for operational convenience, but
  keep it ignored by Git.
- Track manifests, collision proxies, license notes, configs, source code, and
  documentation.
