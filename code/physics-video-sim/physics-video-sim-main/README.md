# physics-video-sim

A config-driven physics-video pipeline built around PyBullet, Blender, Kubric,
and PhyCo-Sim.

```text
seeded sample
→ PyBullet simulation
→ scenario validation
→ trajectory-aware camera
→ Blender render
→ RGB/depth/segmentation/video/metadata
```

The current scenarios are:

- `rolling`: near-uniform planar rolling from an initial linear/angular state;
- `constant_force`: planar motion under a persistent world-space force;
- `free_fall`: a raised object falls under gravity, contacts the support
  surface, and rebounds according to its collision properties.

Production output defaults to 1280×720, 16 fps, exactly 81 frames, and Cycles
at 128 samples per pixel with adaptive sampling and denoising.

## Setup

Clone the repository and its reference projects:

```bash
git clone --recurse-submodules <repository-url>
cd physics-video-sim
```

Create the Python development environment:

```bash
conda create -n physics-video-sim python=3.10 -y
conda activate physics-video-sim
python -m pip install -e ".[dev]"
```

Prepare machine profiles by copying the examples or editing the generic
profiles:

```text
configs/local.yaml
configs/server.yaml
```

Set `paths.blender_executable` in the profile. Absolute Blender paths belong in
machine-local config, never in core Python code.

Reference-project installation details are documented in
[`docs/REFERENCE_PROJECTS.md`](docs/REFERENCE_PROJECTS.md). Asset preparation is
documented in [`assets/README.md`](assets/README.md).

## Generate one sample

Run Blender with the project entry point. The separator `--` passes remaining
arguments to the Python script:

```bash
blender --background --factory-startup \
  --python scripts/generate.py -- \
  --config configs/server.yaml \
  --scenario rolling \
  --seed 1000 \
  --variant x1
```

Generate every controlled-variable member of one group:

```bash
blender --background --factory-startup \
  --python scripts/generate.py -- \
  --config configs/server.yaml \
  --scenario constant_force \
  --seed 1000 \
  --all-variants
```

The default scenario configs define `x1`, `x0.5`, and `x1.5`. All members of a
group share their initial image and nuisance variables; only the declared
controlled variable changes.

## Batch generation

Generate ten groups for all three scenarios using isolated Blender processes:

```bash
python scripts/generate_batch.py \
  --config configs/server.yaml \
  --groups-per-scenario 10 \
  --gpu-ids 0 1 2 3
```

Each successful group currently contains three videos, one for each configured
multiplier. Invalid groups are rejected before rendering and replaced by later
candidate seeds up to the configured attempt limit.

## Output

```text
datasets/<scenario>/seed-001000/<variant>/
├── rgb/
├── depth/
├── segmentation/
├── video.mp4
├── trajectory.json
├── collisions.json
├── metadata.json
└── config.yaml
```

Large assets, generated datasets, caches, logs, and previews stay inside the
repository directory for convenient synchronization but are excluded from Git.

## Validation and development checks

```bash
python -m pytest -q
python -m ruff check src scripts tests
```

See:

- [`docs/PIPELINE.md`](docs/PIPELINE.md) for sampling and physics semantics;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for module boundaries;
- [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) for the final tree;
- [`docs/SERVER.md`](docs/SERVER.md) for a generic deployment procedure.
