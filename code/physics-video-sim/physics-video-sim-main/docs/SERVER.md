# Server deployment

This document intentionally contains no organization-specific host names,
accounts, mount points, keys, or absolute installation paths. Keep those in a
machine-specific `SERVER_<name>.md` file.

## Required server capabilities

- Linux host reachable by SSH;
- NVIDIA GPU and a driver supported by the selected Blender release;
- project-owned storage large enough for `assets/`, `datasets/`, and `cache/`;
- Blender headless execution;
- the PhyCo-Sim/Kubric Python environment and PyBullet;
- `ffmpeg` or OpenCV for `video.mp4` output.

Normal generation must use an unprivileged project account. Use root only for
the smallest necessary system dependency or permission repair, and return to
the project account immediately afterward.

## Generic SSH checks

```bash
ssh <project-host>
id
pwd
```

Check project storage without changing it:

```bash
stat <project-storage-root>
touch <project-storage-root>/.write-test
rm <project-storage-root>/.write-test
```

For multiple nodes, create a temporary file on one node and confirm the other
node sees the same inode/content before assuming storage is shared.

GPU and runtime checks:

```bash
nvidia-smi
python --version
conda env list
blender --version
ffmpeg -version
```

## Deployment

Clone or update the same Git remote and branch used by the development machine:

```bash
git clone --recurse-submodules <repository-url> <project-root>
cd <project-root>
git remote -v
git submodule status
```

Do not commit large binary assets or generated data. Synchronize the Git tree
normally, then separately synchronize repository-local ignored directories:

```text
assets/
datasets/
cache/preview-sim/     # only when a local GUI preview needs server trajectories
```

Never synchronize temporary Blender scratch data while a job is running.

## Configuration

Set the server profile to paths valid on that machine:

```yaml
paths:
  asset_root: assets
  output_root: datasets
  cache_root: cache
  blender_executable: <absolute-or-PATH-resolved-blender>
  phyco_sim_root: third_party/phyco-sim

execution:
  headless: true
  gpu_ids: [0]
```

The Blender path is configuration, not Python source code.

## Smoke test before batching

For each changed Scenario, first generate one baseline group on one GPU:

```bash
CUDA_VISIBLE_DEVICES=0 blender --background --factory-startup \
  --python scripts/generate.py -- \
  --config configs/server.yaml \
  --scenario <scenario> \
  --seed 1000 \
  --variant x1
```

Confirm:

- physics validation passed;
- the selected asset and surface collision loaded;
- the expected motion/contact occurred;
- Blender used the requested GPU;
- RGB, depth, segmentation, trajectory, contacts, metadata, config, and MP4 exist;
- the object remains large enough in frame and the complete trajectory is visible.

Only then run `scripts/generate_batch.py`.

## Permission recovery

If the project user cannot log in, inspect the real UID/GID and only the exact
home/SSH paths involved. Repair ownership only when it is demonstrably wrong.
Do not recursively chmod a home directory and do not alter unrelated SSH or
system configuration.
