---
pretty_name: Physics Video Simulation Assets
license: other
tags:
  - blender
  - pybullet
  - physics-simulation
  - synthetic-data
---

# Physics Video Simulation Assets

Private working archive of runtime and source assets for
[`TLEphage/physics-video-sim`](https://github.com/TLEphage/physics-video-sim).
The directory layout is preserved so the files can be synchronized directly
into a project checkout.

Canonical private dataset repository:
[`physics-video-lab/physics-video-assets`](https://huggingface.co/datasets/physics-video-lab/physics-video-assets).

## Included assets

- `classroom` — Blender Demo Files classroom, CC0-1.0;
- `sphere_baseball` — Poly Haven baseball, CC0-1.0;
- `food_lime` — Poly Haven lime, CC0-1.0;
- `food_lychee` — Poly Haven lychee, CC0-1.0.

Additional assets contributed by the group (normalized to the same
conventions: `source/` original, `visual/`, low-poly `collision/`,
`asset.yaml`, `license/`):

- `special_plush_elephant` - GSO Sootheze Cold Therapy Elephant, CC BY-SA 4.0 (attribution + ShareAlike);
- `replicad_apartment` - ReplicaCAD/FRL apartment stage, CC BY-NC 4.0 (attribution, NON-COMMERCIAL only);
- `turntable` - project-generated disc, CC0-1.0.

`special_plush_elephant` and `replicad_apartment` are NOT CC0-1.0, so they
must be named explicitly when uploading:

```bash
python scripts/sync_hf_assets.py upload \
  --asset-id special_plush_elephant --allowed-license "CC BY-SA 4.0" \
  --asset-id replicad_apartment    --allowed-license "CC BY-NC 4.0" \
  --asset-id turntable             --allowed-license "CC0-1.0"
```

The `CC BY-NC 4.0` environment must not be used commercially. Assets whose
license is `UNKNOWN` remain private-only and are never upload-allowlisted.

The private archive can additionally contain locally supplied assets whose
source and redistribution license are still `UNKNOWN`. Those files are for the
owner's private storage and project synchronization only. They must not be
republished, shared, or made accessible by changing this dataset to public.

Each asset directory may contain its untouched download under `source/`, a
normalized runtime visual under `visual/`, collision geometry, `asset.yaml`,
and provenance under `license/`. `assets_manifest.json` records the byte size
and SHA-256 digest of every synchronized file.

An object asset may declare `visual.material` to ask the renderer for a PBR
texture set. When it does, the maps can be shipped INSIDE the asset under
`visual/textures/<name>/` and referenced with a `textures:` key, which is
searched before the shared library. That keeps the asset usable after a plain
`download`, with no `<workspace>/models/pbr_textures` present.

The license in each `asset.yaml` and `license/SOURCE.md` applies to that asset;
there is no single license covering the whole archive.

## Synchronize into the project

```bash
git clone --recurse-submodules https://github.com/TLEphage/physics-video-sim.git
cd physics-video-sim
python -m pip install -e ".[assets]"
hf auth login
python scripts/sync_hf_assets.py download
python scripts/sync_hf_assets.py verify
```

Authentication is currently required because the dataset repository is
private. Never store a Hugging Face access token in the project tree.
