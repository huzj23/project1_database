"""Backdrop construction for PhyCo-Sim scenarios.

Two backdrop families, matching the two tracks of the improvement plan:

``studio``
    Reproduces the reference look: a **cyclorama** (floor + back wall) with PBR
    concrete, lit by a **three-point softbox rig** (large key softbox + front fill
    + cool wall rim) over an HDRI ambient, with motion blur enabled.

``interior``
    Uses a **ReplicaCAD** interactive apartment stage as a photoreal interior
    background.  The stage is attached with ``simulation_filename=None`` so
    pybullet ignores it entirely (see ``pybullet.py``: the simulator returns
    ``None`` for objects without a simulation file) while Blender still renders
    it -- i.e. a purely visual, non-colliding backdrop.

Both are added as ``background=True`` assets so they stay out of
``scene.foreground_assets``.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import phyco_common as pc

# --------------------------------------------------------------------------------------
# Asset roots (created by tools/fetch_polyhaven.sh and tools/fetch_interactive_assets.sh)
# --------------------------------------------------------------------------------------

PBR_ROOT = os.path.join(pc.MODELS_DIR, "pbr_textures")
HDRI_HDR_ROOT = os.path.join(pc.MODELS_DIR, "hdri_hdr")
REPLICAD_ROOT = os.path.join(pc.MODELS_DIR, "backgrounds", "replicad")
GSO_ROOT = os.path.join(pc.MODELS_DIR, "gso")


def list_pbr_materials() -> List[Tuple[str, str]]:
    """(category, asset_name) for every downloaded Poly Haven material."""
    out: List[Tuple[str, str]] = []
    if not os.path.isdir(PBR_ROOT):
        return out
    for cat in sorted(os.listdir(PBR_ROOT)):
        cdir = os.path.join(PBR_ROOT, cat)
        if not os.path.isdir(cdir):
            continue
        for entry in sorted(os.listdir(cdir)):
            if entry.endswith(".blend") and os.path.isdir(os.path.join(cdir, entry, "textures")):
                out.append((cat, entry[: -len(".blend")]))
    return out


def pbr_texture_dir(asset: str, category: Optional[str] = None) -> Optional[str]:
    """Locate ``<PBR_ROOT>/<category>/<asset>.blend/textures`` for an asset name."""
    if not os.path.isdir(PBR_ROOT):
        return None
    cats = [category] if category else sorted(os.listdir(PBR_ROOT))
    for cat in cats:
        p = os.path.join(PBR_ROOT, cat, f"{asset}.blend", "textures")
        if os.path.isdir(p):
            return p
    return None


def _find_map(texdir: str, patterns: Tuple[str, ...]) -> Optional[str]:
    """First file in ``texdir`` whose lowercase name contains any pattern."""
    if not texdir or not os.path.isdir(texdir):
        return None
    for f in sorted(os.listdir(texdir)):
        low = f.lower()
        if any(p in low for p in patterns):
            return os.path.join(texdir, f)
    return None


def pbr_material(kb, asset: str, category: Optional[str] = None,
                 uv_scale: float = 1.0):
    """Build a Principled BSDF material wired to a Poly Haven PBR texture set.

    Missing maps are tolerated: whatever exists (diffuse / normal / roughness /
    displacement) is wired up and the rest falls back to the BSDF defaults.
    Returns ``(material, info_dict)``.
    """
    import bpy

    texdir = pbr_texture_dir(asset, category)
    mat = bpy.data.materials.new(name=f"pbr_{asset}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    info = {"asset": asset, "texture_dir": texdir, "maps": {}}

    if bsdf is None or not texdir:
        bsdf.inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1.0)
        info["fallback"] = "no texture dir"
        return mat, info

    def add_image(path, non_color=False, interpolation="Linear"):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(path, check_existing=True)
        node.image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
        node.interpolation = interpolation
        return node

    def add_coord_scale(scale):
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (scale, scale, scale)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        return mp

    maps = {
        "diffuse": (_find_map(texdir, ("_diff_", "diffuse", "_col_")), False),
        "rough": (_find_map(texdir, ("_rough_", "roughness")), True),
        "normal": (_find_map(texdir, ("_nor_gl_", "_nor_", "normal")), True),
        "disp": (_find_map(texdir, ("_disp_", "displacement", "_height_")), True),
    }
    coord = add_coord_scale(uv_scale) if uv_scale != 1.0 else None

    if maps["diffuse"][0]:
        n = add_image(maps["diffuse"][0])
        if coord:
            nt.links.new(coord.outputs["Vector"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        info["maps"]["diffuse"] = os.path.basename(maps["diffuse"][0])

    if maps["rough"][0]:
        n = add_image(maps["rough"][0], non_color=True)
        if coord:
            nt.links.new(coord.outputs["Vector"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Roughness"])
        info["maps"]["roughness"] = os.path.basename(maps["rough"][0])

    if maps["normal"][0]:
        n = add_image(maps["normal"][0], non_color=True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        if coord:
            nt.links.new(coord.outputs["Vector"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        if "Normal" in bsdf.inputs:
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        info["maps"]["normal"] = os.path.basename(maps["normal"][0])

    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.3
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.3

    return mat, info


def apply_bpy_material(renderer, kubric_obj, mat) -> bool:
    """Attach a raw ``bpy`` material to an asset already added to the scene.

    Kubric's ``PhysicalObject.material`` trait only accepts a
    ``kubric.core.materials.Material``, so a hand-built node material cannot be
    passed at construction time.  The upstream scenarios solve this the same way:
    add the object first, then reach the Blender datablock through
    ``asset.linked_objects[renderer]`` and write into its material slots.
    """
    bo = kubric_obj.linked_objects.get(renderer)
    if bo is None or not hasattr(bo, "data"):
        return False
    if bo.data.materials:
        bo.data.materials[0] = mat
    else:
        bo.data.materials.append(mat)
    return True


# --------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------

def enable_hdri_file(renderer, hdri: str, strength: float = 1.0,
                     rotation=(0.0, 0.0, 0.0), bg_strength: float = 1.0) -> Optional[str]:
    """Light the scene from a plain ``.hdr`` file (no tarball / manifest needed).

    ``strength`` drives the *ambient lighting*; ``bg_strength`` drives what the
    camera sees.  Keeping these separate matters a lot: Kubric's world node graph
    splits camera rays from lighting rays, so the HDRI can stay fully visible as a
    photoreal background while contributing almost no fill light.  Ambient at
    full strength floods the floor and erases the contact shadow entirely -- a
    near-zero ambient with a strong key light is what makes an object read as
    actually resting on the ground.

    Falls back to the tarball-based cache in ``models/hdri_haven`` when only that
    form is available.
    """
    path = os.path.join(HDRI_HDR_ROOT, f"{hdri}_4k.hdr")
    if os.path.isfile(path):
        renderer._set_ambient_light_hdri(path, hdri_rotation=rotation, strength=strength)
        renderer._set_background_hdri(path, hdri_rotation=rotation)
        # Kubric's _set_background_hdri takes no strength, so scale the world's
        # background node ourselves.  This node feeds camera rays only, so it
        # changes what the HDRI *looks* like without touching the lighting.
        if bg_strength != 1.0:
            try:
                renderer.bg_node.inputs["Strength"].default_value = float(bg_strength)
            except Exception as e:
                print(f"[phyco] bg_strength not applied: {e}", flush=True)
        return path
    try:
        pc.enable_hdri(renderer, hdri)
        return f"tar:{hdri}"
    except Exception:
        return None


def add_softbox(kb, scene, name: str, position, target, intensity: float,
                size: float, color=(1.0, 1.0, 1.0)):
    """One area-light 'softbox' aimed at ``target``."""
    lt = kb.RectAreaLight(name=name, position=position, intensity=intensity,
                          width=size, height=size, color=color)
    lt.look_at(tuple(target))
    scene += lt
    return lt


def enable_motion_blur(shutter: float = 0.25) -> dict:
    """Turn on Cycles motion blur, matching the reference recipe."""
    import bpy

    r = bpy.context.scene.render
    r.use_motion_blur = True
    r.motion_blur_shutter = float(shutter)
    return {"use_motion_blur": True, "shutter": float(shutter)}


# --------------------------------------------------------------------------------------
# Track A -- studio cyclorama
# --------------------------------------------------------------------------------------

@dataclass
class StudioSpec:
    """Parameters of the studio (cyclorama + softbox) backdrop."""

    floor_size: float = 9.0
    wall_height: float = 6.0
    wall_distance: float = 6.0
    floor_material: Optional[str] = "concrete_floor_worn_001"
    floor_category: Optional[str] = "concrete_textures"
    wall_material: Optional[str] = None
    wall_category: Optional[str] = None
    uv_scale: float = 1.0
    #: three-point rig: (name, position, intensity, size, colour)
    lights: Tuple = (
        ("Large Softbox", (4.0, -4.5, 6.0), 1500.0, 5.0, (1.0, 0.97, 0.92)),
        ("Front Fill",    (-5.0, -5.5, 2.8),  380.0, 4.0, (0.95, 0.97, 1.0)),
        ("Cool Wall Rim", (-1.0, 5.0, 5.0),   650.0, 3.0, (0.88, 0.93, 1.0)),
    )
    hdri: Optional[str] = "empty_warehouse_01"
    hdri_strength: float = 1.0
    motion_blur_shutter: float = 0.25


def build_studio(kb, scene, renderer, spec: StudioSpec = StudioSpec(),
                 ground_z: float = 0.0) -> dict:
    """Floor + back wall cyclorama, PBR ground, three-point softbox rig."""
    info: Dict = {"backdrop": "studio", "materials": {}}

    floor = kb.Cube(name="studio_floor",
                    scale=(spec.floor_size, spec.floor_size, 0.1),
                    position=(0.0, 0.0, ground_z - 0.1),
                    static=True, background=True, segmentation_id=1)
    floor.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.55, 0.55, 1.0),
                                               roughness=0.85)
    scene += floor
    if spec.floor_material and pbr_texture_dir(spec.floor_material, spec.floor_category):
        mat, mi = pbr_material(kb, spec.floor_material, spec.floor_category,
                               uv_scale=spec.uv_scale)
        if apply_bpy_material(renderer, floor, mat):
            info["materials"]["floor"] = mi

    wall = kb.Cube(name="studio_back_wall",
                   scale=(spec.floor_size, 0.1, spec.wall_height),
                   position=(0.0, spec.wall_distance, ground_z + spec.wall_height - 0.1),
                   static=True, background=True, segmentation_id=3)
    wall.material = kb.PrincipledBSDFMaterial(color=(0.62, 0.62, 0.62, 1.0),
                                              roughness=0.9)
    scene += wall
    if spec.wall_material and pbr_texture_dir(spec.wall_material, spec.wall_category):
        mat, mi = pbr_material(kb, spec.wall_material, spec.wall_category,
                               uv_scale=spec.uv_scale)
        if apply_bpy_material(renderer, wall, mat):
            info["materials"]["wall"] = mi

    lights = []
    for name, pos, inten, size, col in spec.lights:
        add_softbox(kb, scene, name, pos, (0.0, 0.0, ground_z + 1.0),
                    inten, size, col)
        lights.append({"name": name, "position": list(pos), "intensity": inten,
                       "size": size, "color": list(col)})
    info["lights"] = lights

    if spec.hdri:
        p = enable_hdri_file(renderer, spec.hdri, spec.hdri_strength)
        info["hdri"] = {"id": spec.hdri, "path": p, "strength": spec.hdri_strength}

    info["motion_blur"] = enable_motion_blur(spec.motion_blur_shutter)
    info["cyclorama"] = {
        "floor_size": spec.floor_size, "wall_height": spec.wall_height,
        "wall_distance": spec.wall_distance,
    }
    return info


# --------------------------------------------------------------------------------------
# Track B1 -- ReplicaCAD interior
# --------------------------------------------------------------------------------------

def list_replicad_stages() -> List[str]:
    p = os.path.join(REPLICAD_ROOT, "stages")
    if not os.path.isdir(p):
        return []
    return sorted(f[: -len(".glb")] for f in os.listdir(p) if f.endswith(".glb"))


@dataclass
class InteriorSpec:
    """Parameters of the ReplicaCAD interior backdrop."""

    stage: str = "frl_apartment_stage"
    scale: float = 1.0
    uv_scale: float = 1.0
    hdri: Optional[str] = "empty_warehouse_01"
    hdri_strength: float = 0.55
    #: gentle top-up lights so the room is not lit by HDRI alone
    fill_intensity: float = 260.0
    fill_position: Tuple[float, float, float] = (0.0, -3.0, 3.2)
    motion_blur_shutter: float = 0.25


def add_stage_direct(renderer, glb_path: str, join: bool = False) -> dict:
    """Load a ReplicaCAD stage with a *direct* bpy glTF import.

    Why not the normal ``scene += FileBasedObject`` path?  Kubric's glTF branch
    force-sets ``rotation_quaternion = (0.707107, -0.707107, 0, 0)`` on the joined
    object and then applies **rotation only**.  Every ReplicaCAD node already
    carries its own ``+90 deg X`` rotation plus a ``0.01`` scale (the source data
    is authored in centimetres), so that overwrite destroys the transform: the
    room ended up spanning ~1300 m and rendered nothing at all.

    Importing straight through ``bpy.ops.import_scene.gltf`` preserves the node
    transforms, and the room lands at a sane ~7 x 13 x 3 m with its floor near
    z = 0.  A backdrop is static, so it never needs the physics simulator.

    Returns a report dict with the measured bounds and floor height.
    """
    import bpy
    import numpy as np

    before = {o.name for o in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=glb_path)
    added = [o for o in bpy.data.objects if o.name not in before]
    meshes = [o for o in added if o.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"glTF import produced no meshes: {glb_path}")

    lo = np.array([1e18] * 3)
    hi = np.array([-1e18] * 3)
    for o in meshes:
        mw = np.array(o.matrix_world)
        local = np.array([list(c) for c in o.bound_box], dtype=float)   # (8,3)
        corners = local @ mw[:3, :3].T + mw[:3, 3]
        lo = np.minimum(lo, corners.min(axis=0))
        hi = np.maximum(hi, corners.max(axis=0))

    if join:
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(state=True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.join()
        meshes = [bpy.context.view_layer.objects.active]

    _STAGE_MESHES[id(renderer)] = meshes
    return {
        "stage": os.path.basename(glb_path),
        "objects": len(added),
        "meshes": len(meshes),
        "bounds_min": [float(v) for v in lo],
        "bounds_max": [float(v) for v in hi],
        "extents_m": [float(v) for v in (hi - lo)],
        "floor_z": float(lo[2]),      # global lowest point -- NOT the local floor
    }


#: meshes of the most recently imported stage, keyed by renderer identity
_STAGE_MESHES: Dict[int, list] = {}


def floor_z_at(renderer, x: float, y: float, radius: float = 0.45,
               tol: float = 0.03) -> Optional[float]:
    """Height of the stage floor *at* (x, y).

    ``add_stage_direct`` reports the room's global minimum z, which is the lowest
    point anywhere -- a sunken step or the foot of the staircase.  Placing an
    actor at that height sinks it into the floorboards wherever the local floor
    is higher, because ReplicaCAD floors are not level.

    A downward ray is the right probe: floors here are large low-poly quads, so
    vertex sampling finds nothing inside a small disc around the anchor.  (Ray
    casting was unusable while the stage was still imported through Kubric's
    mangled glTF path; with the direct import the geometry is real and hit-able.)
    """
    import bpy

    meshes = _STAGE_MESHES.get(id(renderer))
    if not meshes:
        return None

    dg = bpy.context.evaluated_depsgraph_get()
    origin = (float(x), float(y), 60.0)
    hit, loc, normal, _idx, obj, _mat = bpy.context.scene.ray_cast(
        dg, origin, (0.0, 0.0, -1.0), distance=200.0)
    if hit and normal is not None and normal[2] > 0.5:
        return float(loc[2])

    # fall back: densest z band among nearby face centres
    import numpy as np
    zs = []
    for o in meshes:
        mw = np.array(o.matrix_world)
        me = o.data
        n = len(me.polygons)
        if not n:
            continue
        centres = np.empty(n * 3, dtype=float)
        me.polygons.foreach_get("center", centres)
        centres = centres.reshape(-1, 3)
        world = centres @ mw[:3, :3].T + mw[:3, 3]
        near = world[(np.abs(world[:, 0] - x) < radius) &
                     (np.abs(world[:, 1] - y) < radius)]
        if len(near):
            zs.append(near[:, 2])
    if not zs:
        return None
    z = np.concatenate(zs)
    hist, edges = np.histogram(z, bins=40)
    k = int(np.argmax(hist))
    band = z[np.abs(z - 0.5 * (edges[k] + edges[k + 1])) < tol]
    return float(np.median(band)) if len(band) else float(0.5 * (edges[k] + edges[k + 1]))


@dataclass
class InteriorDirectSpec:
    """Parameters for the direct-import ReplicaCAD interior backdrop."""

    stage: str = "frl_apartment_stage"
    hdri: Optional[str] = "empty_warehouse_01"
    hdri_strength: float = 1.0
    key_intensity: float = 0.0        # 0 = HDRI only
    key_position: Tuple[float, float, float] = (1.6, -2.0, 2.6)
    key_size: float = 1.6
    motion_blur_shutter: float = 0.25


def build_interior_direct(kb, scene, renderer,
                          spec: InteriorDirectSpec = InteriorDirectSpec(),
                          look_at: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> dict:
    """Photoreal ReplicaCAD room as a render-only backdrop (direct GLB import).

    Note ``kb``/``scene`` are only needed for the optional light; the room itself
    is added straight through bpy.
    """
    info: Dict = {"backdrop": "interior_direct", "stage": spec.stage}
    glb = os.path.join(REPLICAD_ROOT, "stages", f"{spec.stage}.glb")
    if not os.path.isfile(glb):
        raise FileNotFoundError(f"ReplicaCAD stage not found: {glb}")

    info.update(add_stage_direct(renderer, glb))
    info["glb"] = glb

    if spec.hdri:
        info["hdri"] = {"id": spec.hdri,
                        "path": enable_hdri_file(renderer, spec.hdri, spec.hdri_strength),
                        "strength": spec.hdri_strength}

    if spec.key_intensity > 0:
        add_softbox(kb, scene, "Interior Key", spec.key_position, look_at,
                    spec.key_intensity, spec.key_size, (1.0, 0.97, 0.92))
        info["key"] = {"position": list(spec.key_position),
                       "intensity": spec.key_intensity}

    info["motion_blur"] = enable_motion_blur(spec.motion_blur_shutter)
    return info


def build_interior(kb, scene, renderer, spec: "InteriorSpec" = None,
                   look_at: Tuple[float, float, float] = (0.0, 0.0, 1.0)) -> dict:
    """DEPRECATED: the Kubric FileBasedObject glTF path mangles ReplicaCAD stages.

    Kept only so old scripts fail loudly rather than silently rendering nothing.
    Use :func:`build_interior_direct` instead.
    """
    raise RuntimeError(
        "build_interior() is broken for ReplicaCAD stages: Kubric's glTF branch "
        "overwrites the node transforms (room lands ~1300 m away and renders "
        "nothing). Use build_interior_direct().")


# --------------------------------------------------------------------------------------
# Camera placement for interiors
# --------------------------------------------------------------------------------------

def interior_camera_distance(renderer) -> float:
    """Unused hook kept for symmetry; interior framing is chosen by the caller."""
    return 6.0


def setup_orbit_camera(kb, scene, look_at, distance: float = 4.5,
                          elevation_deg: float = 18.0, azimuth_deg: float = -55.0,
                          focal_length: float = 55.0, sensor_width: float = 36.0):
    """Place the camera on an orbit *inside* the room.

    The iterative auto-framer is wrong here: it pulls back until the subject fits,
    which walks the camera straight through a wall.  Inside a room we instead pin
    a modest distance and let the (already small) subject sit in a wider interior
    composition -- which is also what the reference footage does.
    """
    import numpy as np

    cam = kb.PerspectiveCamera(focal_length=focal_length, sensor_width=sensor_width)
    el = np.deg2rad(elevation_deg)
    az = np.deg2rad(azimuth_deg)
    t = np.asarray(look_at, dtype=float)
    cam.position = (
        t[0] + distance * np.cos(el) * np.cos(az),
        t[1] + distance * np.cos(el) * np.sin(az),
        t[2] + distance * np.sin(el),
    )
    cam.look_at(tuple(t))
    scene.camera = cam
    return cam


def stage_bounds(scale: float = 1.0) -> Optional[Tuple[Tuple[float, float, float],
                                                       Tuple[float, float, float]]]:
    """World-space bounds of whatever is currently in the Blender scene.

    Called after the stage is imported; used to pick a camera position that is
    actually inside the room rather than inside a wall.
    """
    import bpy
    import mathutils

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            for i, v in enumerate((w.x, w.y, w.z)):
                lo[i] = min(lo[i], v)
                hi[i] = max(hi[i], v)
    if lo[0] == float("inf"):
        return None
    return (tuple(lo), tuple(hi))
