"""Shared infrastructure for PhyCo-Sim single-object scenario generation.

This module is imported *inside* Blender's bundled Python 3.10
(``blender.exe --background --python <entry>.py``).  It provides:

* repository/runtime path bootstrap
* the mesh asset registry (maps logical names -> (obj, urdf) pairs)
* scene construction helpers (ground, camera, lighting)
* render-layer decoding and on-disk export helpers (frames, videos, metadata)

Notes / hard-won platform constraints (Windows, Blender 3.4.1):
* ``bpy`` is NOT importable from the bundled interpreter as a plain module;
  everything must run through ``blender.exe --background --python``.
* ``Blender(..., verbose=False)`` crashes Blender on Windows because
  ``RedirectStream`` uses ``os.dup2`` on a stream Blender owns.  Always use
  ``verbose=True``.
* ``OpenEXR`` must be pinned to ``3.2.3``; 3.2.7+ segfaults against the
  OpenEXR runtime Blender 3.4 links.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

# --------------------------------------------------------------------------------------
# Path bootstrap
# --------------------------------------------------------------------------------------

# <root>/code/scenarios/phyco_common.py  ->  <root>
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(_THIS_DIR)
PROJECT_ROOT = os.path.dirname(CODE_DIR)

REPO_DIR = os.path.join(CODE_DIR, "vendor", "phyco-sim")
KUBRIC_DIR = os.path.join(REPO_DIR, "kubric")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MESH_DIR = os.path.join(MODELS_DIR, "phyco_sim_objs")
HDRI_DIR = os.path.join(MODELS_DIR, "hdri_haven")
KUBASIC_DIR = os.path.join(MODELS_DIR, "kubasic")
OUTCOMES_DIR = os.path.join(PROJECT_ROOT, "outcomes")


def bootstrap_syspath() -> None:
    """Make the vendored kubric package importable."""
    for p in (KUBRIC_DIR, os.path.join(REPO_DIR, "src")):
        if p not in sys.path:
            sys.path.insert(0, p)


def patch_numpy_legacy_aliases() -> list:
    """Restore numpy aliases that Blender 3.4's bundled add-ons still use.

    Blender 3.4's glTF importer calls ``np.bool`` (and friends), which NumPy
    removed in 1.24.  We need NumPy 1.26 for the rest of the stack, so instead of
    downgrading we re-attach the aliases.  Without this, importing a ``.glb``
    fails with ``AttributeError: module 'numpy' has no attribute 'bool'``.

    Returns the list of aliases that were actually installed.
    """
    import numpy as np

    patched = []
    for alias, target in (("bool", bool), ("int", int), ("float", float),
                          ("complex", complex), ("object", object),
                          ("str", str), ("long", int), ("unicode", str)):
        if not hasattr(np, alias):
            try:
                setattr(np, alias, target)
                patched.append(alias)
            except Exception:
                pass
    return patched


# --------------------------------------------------------------------------------------
# Asset registry
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class MeshAsset:
    """A rigid mesh with its PyBullet URDF and Blender-renderable OBJ."""

    name: str
    obj_rel: str
    urdf_rel: str
    #: nominal half-extent along +Z of the mesh in *local* units (scale applied later)
    nominal_height: float

    @property
    def obj_path(self) -> str:
        return os.path.join(MESH_DIR, self.obj_rel)

    @property
    def urdf_path(self) -> str:
        return os.path.join(MESH_DIR, self.urdf_rel)


#: Meshes shipped by the upstream repository, verified present under models/phyco_sim_objs.
ASSETS: Dict[str, MeshAsset] = {
    "ball": MeshAsset("ball", "ball_drop/ball_drop_z_1-0.obj",
                      "ball_drop/ball_drop_z_1-0.urdf", 1.0),
    "ball_small": MeshAsset("ball_small", "ball_drop/ball_drop_z_0-0.obj",
                            "ball_drop/ball_drop_z_0-0.urdf", 0.5),
    "brick_box": MeshAsset("brick_box", "bricks/brick_slide_x_0-0.obj",
                           "bricks/brick_slide_x_0-0.urdf", 0.5),
    "brick": MeshAsset("brick", "bricks/brick_slide_x_2-0.obj",
                       "bricks/brick_slide_x_2-0.urdf", 0.5),
    "brick_tall": MeshAsset("brick_tall", "bricks/brick_x-1-0.obj",
                            "bricks/brick_x-1-0.urdf", 0.5),
    "jenga": MeshAsset("jenga", "jenga_block.obj", "jenga_block.urdf", 0.045),
    "plane": MeshAsset("plane", "plane.obj", "plane.urdf", 0.5),
    "platform": MeshAsset("platform", "cube_platform.obj",
                          "cube_platform.urdf", 0.5),
    "wall": MeshAsset("wall", "cube_wall-0-0-0.obj",
                      "cube_wall-0-0-0.urdf", 0.5),
}


def get_asset(name: str) -> MeshAsset:
    if name not in ASSETS:
        raise KeyError(f"unknown asset '{name}'. available: {sorted(ASSETS)}")
    a = ASSETS[name]
    for p in (a.obj_path, a.urdf_path):
        if not os.path.isfile(p):
            raise FileNotFoundError(f"asset file missing: {p}")
    return a


_MESH_BOUNDS_CACHE: Dict[str, tuple] = {}


def mesh_bounds(obj_path: str) -> tuple:
    """Axis-aligned bounds ``(min_xyz, max_xyz)`` of an OBJ's vertices.

    Parsed straight from the ``v`` lines and cached.  Kubric's ``Object3D.bounds``
    is not usable here because these ``FileBasedObject`` instances carry no asset
    metadata, so it would fall back to the unit-cube default and mis-size the
    camera framing.
    """
    if obj_path in _MESH_BOUNDS_CACHE:
        return _MESH_BOUNDS_CACHE[obj_path]

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    with open(obj_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("v "):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                continue
            for i, v in enumerate((x, y, z)):
                if v < lo[i]:
                    lo[i] = v
                if v > hi[i]:
                    hi[i] = v

    if lo[0] == float("inf"):
        lo, hi = [-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]
    result = (tuple(lo), tuple(hi))
    _MESH_BOUNDS_CACHE[obj_path] = result
    return result


def mesh_half_extent(obj_path: str) -> Tuple[float, float, float]:
    """Half-extents (hx, hy, hz) of the mesh in its own local units."""
    lo, hi = mesh_bounds(obj_path)
    return tuple((hi[i] - lo[i]) / 2.0 for i in range(3))


def read_urdf_inertia(urdf_path: str) -> dict:
    """Parse mass and the inertia tensor from a URDF's ``<inertial>`` block.

    The mesh assets ship with an inertial block generated by the upstream
    ``create_urdf_for_obj.py`` (box approximation).  Reading it back lets the
    rotation scenario report angular momentum and rotational energy that are
    consistent with the body actually being simulated.
    """
    import xml.etree.ElementTree as ET

    out = {"mass": None, "inertia": None, "origin": None}
    try:
        root = ET.parse(urdf_path).getroot()
    except Exception:
        return out
    inertial = root.find(".//inertial")
    if inertial is None:
        return out
    mass = inertial.find("mass")
    if mass is not None and mass.get("value") is not None:
        out["mass"] = float(mass.get("value"))
    i = inertial.find("inertia")
    if i is not None:
        out["inertia"] = {
            k: float(i.get(k)) for k in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")
            if i.get(k) is not None
        }
    origin = inertial.find("origin")
    if origin is not None and origin.get("xyz"):
        out["origin"] = [float(v) for v in origin.get("xyz").split()]
    return out


def principal_moment(inertia: dict | None, axis: str) -> float | None:
    """Moment of inertia about a principal axis ('x'/'y'/'z')."""
    if not inertia:
        return None
    key = {"x": "ixx", "y": "iyy", "z": "izz"}.get(axis.lower())
    return inertia.get(key) if key else None


# --------------------------------------------------------------------------------------
# Scene construction
# --------------------------------------------------------------------------------------

@dataclass
class SceneSpec:
    resolution: Tuple[int, int] = (768, 432)
    frame_start: int = 0
    frame_end: int = 96
    frame_rate: int = 24
    step_rate: int = 240
    gravity: Tuple[float, float, float] = (0.0, 0.0, -9.81)
    samples: int = 64
    use_denoising: bool = True


def make_scene(kb, spec: SceneSpec):
    """Create a Kubric scene + Blender renderer + PyBullet simulator."""
    from kubric.simulator import PyBullet
    from kubric.renderer import Blender

    if spec.step_rate % spec.frame_rate != 0:
        raise ValueError(
            f"step_rate ({spec.step_rate}) must be an integer multiple of "
            f"frame_rate ({spec.frame_rate})")

    scratch = tempfile.mkdtemp(prefix="phyco_scratch_")
    scene = kb.Scene(
        resolution=spec.resolution,
        frame_start=spec.frame_start,
        frame_end=spec.frame_end,
        frame_rate=spec.frame_rate,
        step_rate=spec.step_rate,
        gravity=spec.gravity,
    )
    # NOTE: verbose=True is mandatory on Windows (see module docstring).
    renderer = Blender(
        scene, scratch_dir=scratch,
        samples_per_pixel=spec.samples,
        use_denoising=spec.use_denoising,
        verbose=True,
    )
    simulator = PyBullet(scene, scratch_dir=scratch)
    return scene, renderer, simulator, scratch


def add_ground(kb, scene, size: float = 6.0, segmentation_id: int = 1):
    """Static, non-interactive ground plane (a thin cube avoids URDF quirks)."""
    ground = kb.Cube(
        name="ground",
        scale=(size, size, 0.05),
        position=(0.0, 0.0, -0.05),
        static=True,
        segmentation_id=segmentation_id,
    )
    ground.material = kb.PrincipledBSDFMaterial(color=kb.Color.from_name("gray"))
    scene += ground
    return ground


def setup_camera(kb, scene, look_at, distance: float, elevation_deg: float = 28.0,
                 azimuth_deg: float = -60.0, focal_length: float = 42.0,
                 sensor_width: float = 36.0):
    """Place a camera on a spherical orbit around ``look_at`` and aim it there."""
    import numpy as np

    cam = kb.PerspectiveCamera(focal_length=focal_length, sensor_width=sensor_width)
    el = np.deg2rad(elevation_deg)
    az = np.deg2rad(azimuth_deg)
    target = np.asarray(look_at, dtype=float)
    cam.position = (
        target[0] + distance * np.cos(el) * np.cos(az),
        target[1] + distance * np.cos(el) * np.sin(az),
        target[2] + distance * np.sin(el),
    )
    cam.look_at(tuple(target))
    scene.camera = cam
    return cam


def orbit_camera(kb, scene, look_at, distance, elevation_deg, azimuth_deg,
                 focal_length=42.0, sensor_width=36.0):
    """(Re)place an existing camera; used by the auto-framing loop."""
    import numpy as np

    cam = scene.camera
    el = np.deg2rad(elevation_deg)
    az = np.deg2rad(azimuth_deg)
    target = np.asarray(look_at, dtype=float)
    cam.position = (
        target[0] + distance * np.cos(el) * np.cos(az),
        target[1] + distance * np.cos(el) * np.sin(az),
        target[2] + distance * np.sin(el),
    )
    cam.look_at(tuple(target))
    return cam


def auto_frame_camera(kb, scene, positions, look_at, elevation_deg=24.0,
                      azimuth_deg=-62.0, margin: float = 0.12,
                      start_distance: float = 5.0, iters: int = 6,
                      focal_length: float = 42.0, sensor_width: float = 36.0,
                      min_distance: float = 0.0, max_distance: float = 0.0):
    """Iteratively choose a camera distance so ``positions`` fill the frame.

    Uses Kubric's own projection (``Camera.project_point``, normalised image
    coordinates) rather than hand-rolled trigonometry, so it stays correct for
    any look-at convention the framework uses.

    ``min_distance`` / ``max_distance`` (0 = unbounded) clamp the result.  The cap
    matters for backdrop shots: without it the framer backs off until the subject
    alone fills the frame -- cropping the cyclorama away, or stepping through a
    wall in a room.  With it the subject stays large while the backdrop remains
    visible.  The floor matters for very small subjects (a spinning block), where
    the framer would otherwise crowd the lens.
    """
    import numpy as np

    setup_camera(kb, scene, look_at=look_at, distance=start_distance,
                 elevation_deg=elevation_deg, azimuth_deg=azimuth_deg,
                 focal_length=focal_length, sensor_width=sensor_width)

    pts = np.asarray(positions, dtype=float)
    d = float(start_distance)
    target = np.asarray(look_at, dtype=float)
    report = {}

    for _ in range(max(1, iters)):
        orbit_camera(kb, scene, tuple(target), d, elevation_deg, azimuth_deg,
                     focal_length, sensor_width)
        uv, behind = _project_all(scene, pts)
        if not len(uv):
            d *= 1.6
            continue
        span_x = uv[:, 0].max() - uv[:, 0].min()
        span_y = uv[:, 1].max() - uv[:, 1].min()
        cx = 0.5 * (uv[:, 0].max() + uv[:, 0].min())
        cy = 0.5 * (uv[:, 1].max() + uv[:, 1].min())
        report = {
            "distance": d, "span_x": float(span_x), "span_y": float(span_y),
            "center": [float(cx), float(cy)], "behind_camera": behind,
        }
        if behind:
            d *= 1.6
            continue

        # --- recentre: nudge the aim point so the trajectory bbox is centred --------
        # Perspective makes the near half of a circle project larger, which pushes
        # the bbox off-centre; shifting the look-at point fixes it.
        mw = np.asarray(scene.camera.matrix_world, dtype=float)
        right = mw[:3, 0]
        up = mw[:3, 1]
        vis_w = 2.0 * d * np.tan(np.arctan(sensor_width / (2.0 * focal_length)))
        vis_h = vis_w * scene.resolution[1] / scene.resolution[0]
        ex, ey = float(cx - 0.5), float(cy - 0.5)
        target = target + right * (ex * vis_w) - up * (ey * vis_h)
        report["aim_offset"] = [float(ex), float(ey)]

        # --- fit: scale distance so the trajectory sits inside the safe area -------
        need = max(span_x / (1.0 - 2 * margin), span_y / (1.0 - 2 * margin))
        if need <= 0:
            break
        if abs(need - 1.0) < 0.02 and abs(ex) < 0.02 and abs(ey) < 0.02:
            break
        d *= need

    # Clamp only the *final* answer.  Clamping inside the loop starves the
    # recentring feedback above: the aim offset is derived from the observed
    # span, so if the distance can never reach the value that would centre the
    # subject, the target keeps drifting and the camera flies off.
    if max_distance > 0:
        d = min(d, max_distance)
    if min_distance > 0:
        d = max(d, min_distance)
    report["clamped_to"] = [min_distance, max_distance]

    orbit_camera(kb, scene, tuple(target), d, elevation_deg, azimuth_deg,
                 focal_length, sensor_width)
    uv, behind = _project_all(scene, pts)
    if len(uv):
        report["final_span_x"] = float(uv[:, 0].max() - uv[:, 0].min())
        report["final_span_y"] = float(uv[:, 1].max() - uv[:, 1].min())
        report["final_center"] = [
            float(0.5 * (uv[:, 0].max() + uv[:, 0].min())),
            float(0.5 * (uv[:, 1].max() + uv[:, 1].min())),
        ]
    report["final_distance"] = d
    report["margin"] = margin
    report["aim_point"] = [float(v) for v in target]
    return d, report


def _project_all(scene, pts):
    """Project world points to normalised image coords; drop those behind."""
    import numpy as np

    uv = []
    behind = 0
    for p in pts:
        try:
            c = scene.camera.project_point(point3d=p)
        except Exception:
            continue
        if c[2] <= 0:            # sign(z) <= 0 => behind the camera
            behind += 1
            continue
        uv.append((float(c[0]), float(c[1])))
    return np.asarray(uv) if uv else np.zeros((0, 2)), behind


def add_lighting(kb, scene, intensity: float = 4.0):
    """Simple three-point-ish lighting; keeps runs free of HDRI downloads."""
    scene += kb.DirectionalLight(name="key", position=(3, -4, 6), intensity=intensity)
    scene += kb.DirectionalLight(name="fill", position=(-4, -2, 3),
                                 intensity=intensity * 0.35)


def set_background(renderer, scene, rgb=(0.35, 0.45, 0.60)):
    """Give the scene a neutral world colour instead of pure black.

    A non-black background keeps the sky region informative for optical-flow /
    depth supervision and makes the silhouette of the object unambiguous.
    """
    renderer._set_background_color(tuple(rgb) + (1.0,))
    renderer._set_ambient_light_color(tuple(rgb) + (1.0,))
    try:
        scene.background = tuple(rgb) + (1.0,)
    except Exception:
        pass
    return tuple(rgb)


def list_cached_hdris() -> List[str]:
    """HDRI ids that are both listed in the manifest and present as tarballs."""
    manifest = os.path.join(HDRI_DIR, "HDRI_haven.json")
    if not os.path.isfile(manifest):
        return []
    try:
        with open(manifest, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []
    out = []
    for name in data.get("assets", {}):
        if os.path.isfile(os.path.join(HDRI_DIR, f"{name}.tar.gz")):
            out.append(name)
    return sorted(out)


def enable_hdri(renderer, hdri_id: str = "studio_small_03"):
    """Light the scene from a locally cached HDRI (fully offline).

    ``HDRI_haven.json`` normally points at ``gs://kubric-public/...``; we rewrite
    ``data_dir`` to the local cache so ``AssetSource`` resolves tarballs on disk.
    """
    manifest = os.path.join(HDRI_DIR, "HDRI_haven.json")
    if not os.path.isfile(manifest):
        raise FileNotFoundError(f"HDRI manifest not found: {manifest}")
    import json as _json
    with open(manifest, "r", encoding="utf-8") as fh:
        data = _json.load(fh)
    entry = data["assets"][hdri_id]
    # point the manifest at the local cache instead of gs://
    data = dict(data)
    data["data_dir"] = HDRI_DIR
    tmp_manifest = os.path.join(tempfile.mkdtemp(prefix="phyco_hdri_"), "HDRI_haven.json")
    with open(tmp_manifest, "w", encoding="utf-8") as fh:
        _json.dump(data, fh)
    import kubric as kb
    src = kb.AssetSource.from_manifest(tmp_manifest)
    tex = src.create(asset_id=hdri_id)
    renderer._set_ambient_light_hdri(tex.filename)
    renderer._set_background_hdri(tex.filename)
    return hdri_id, entry


# --------------------------------------------------------------------------------------
# Export helpers
# --------------------------------------------------------------------------------------

def _owned(arr, dtype=None):
    """Return a private, C-contiguous copy of ``arr``.

    Render layers come out of Kubric as views over buffers whose lifetime we do
    not control: ``read_channels_from_exr`` builds them with ``np.frombuffer``
    over transient EXR channel bytes.  Even after an explicit
    ``np.array(..., copy=True)``, subsequent NumPy allocations were observed to
    corrupt the depth layer -- accessing it later segfaulted (reproduced with
    rgba+segmentation prepared first, depth last).

    Round-tripping through ``tobytes()`` guarantees a brand-new buffer with no
    ``base`` and no shared ownership, which makes the crash impossible.
    """
    import numpy as np

    a = np.ascontiguousarray(np.asarray(arr), dtype=dtype)
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)


def prepare_rgba(frames, dtype="uint8"):
    """RGBA frames -> owned uint8 BGR array ready for JPEG encoding."""
    import numpy as np

    return np.ascontiguousarray(
        np.stack([_owned(f)[..., :3][..., ::-1] for f in frames]).astype(dtype))


def prepare_segmentation(frames, dtype="uint16"):
    """Instance-mask frames -> owned 2-D uint16 array."""
    import numpy as np

    out = []
    for f in frames:
        a = _owned(f)
        if a.ndim == 3:
            a = a[..., 0].copy()
        out.append(a.astype(dtype))
    return np.ascontiguousarray(np.stack(out))


def prepare_depth_mm(frames, max_depth_m: float = 100.0):
    """Depth frames -> owned 2-D uint16 array in millimetres (0 == invalid).

    Kept separate from the encoder on purpose: every numpy operation on the
    Blender-produced buffers happens here, before any OpenCV call runs.  Mixing
    the two was observed to corrupt the heap -- the crash landed inside this
    function, but only when JPEG/PNG writes had already happened.
    """
    import numpy as np

    out = []
    for f in frames:
        arr = _owned(f, dtype=np.float64)
        if arr.ndim == 3:
            arr = arr[..., 0].copy()
        valid = np.isfinite(arr) & (arr > 0) & (arr < max_depth_m)
        mm = np.zeros(arr.shape, dtype=np.uint16)
        mm[valid] = np.clip(np.round(arr[valid] * 1000.0),
                            1, 65535).astype(np.uint16)
        out.append(mm)
    return np.ascontiguousarray(np.stack(out))


def write_image_sequence(arr, out_dir: str, stem: str, ext: str,
                         params=None) -> List[str]:
    """Encode a prepared (N, H, W[, C]) array to ``<stem>_%05d.<ext>``."""
    import cv2
    import numpy as np

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i in range(arr.shape[0]):
        p = os.path.join(out_dir, f"{stem}_{i:05d}.{ext}")
        cv2.imwrite(p, np.ascontiguousarray(arr[i]), params or [])
        paths.append(p)
    return paths


def save_rgba_jpg(frames, out_dir: str, quality: int = 95) -> List[str]:
    import cv2

    return write_image_sequence(prepare_rgba(frames), out_dir, "rgba", "jpg",
                                [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])


def save_segmentation_png(frames, out_dir: str) -> List[str]:
    return write_image_sequence(prepare_segmentation(frames), out_dir,
                                "segmentation", "png")


def save_depth_png(frames, out_dir: str, max_depth_m: float = 100.0) -> List[str]:
    """Write 16-bit depth in millimetres (0 == invalid/background)."""
    return write_image_sequence(prepare_depth_mm(frames, max_depth_m), out_dir,
                                "depth", "png")


def make_qa_sheet(out_dir: str, n_frames: int, out_path: str | None = None,
                  n_cols: int = 6, thumb_w: int = 240) -> str | None:
    """Tile a few RGB frames (top) and colourised masks (bottom) into one JPEG.

    Segmentation ids are tiny integers, so the raw PNGs look black in a viewer;
    this sheet is for human QA only and is not part of the dataset payload.
    """
    import cv2
    import numpy as np

    n_pick = min(n_cols * 2, n_frames)
    idxs = np.linspace(0, n_frames - 1, n_pick).astype(int)

    rows = []
    for want in ("rgba", "segmentation"):
        tiles = []
        for i in idxs:
            p = os.path.join(out_dir, f"{want}_{i:05d}."
                             + ("jpg" if want == "rgba" else "png"))
            if not os.path.isfile(p):
                continue
            img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if img is None:
                continue
            if img.ndim == 3 and img.shape[2] == 4:
                img = img[:, :, :3]
            if want == "segmentation":
                seg = img.astype(np.int32)
                pal = np.zeros((*seg.shape, 3), np.uint8)
                pal[seg == 1] = (90, 90, 90)      # ground
                pal[seg == 2] = (60, 60, 220)     # object
                img = pal
            h, w = img.shape[:2]
            scale = thumb_w / float(w)
            img = cv2.resize(img, (thumb_w, max(1, int(h * scale))),
                             interpolation=cv2.INTER_NEAREST)
            cv2.putText(img, str(i), (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0) if want == "rgba" else (255, 255, 255), 1,
                        cv2.LINE_AA)
            tiles.append(img)
        if tiles:
            hmin = min(t.shape[0] for t in tiles)
            tiles = [t[:hmin] for t in tiles]
            rows.append(np.hstack(tiles))

    if not rows:
        return None
    wmin = min(r.shape[1] for r in rows)
    rows = [r[:, :wmin] for r in rows]
    sheet = np.vstack(rows)
    out_path = out_path or os.path.join(out_dir, "qa_contact_sheet.jpg")
    cv2.imwrite(out_path, sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return out_path


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def encode_video(frame_glob_dir: str, pattern: str, out_path: str, fps: int,
                 crf: int = 18) -> bool:
    """Encode an image sequence to H.264 mp4 via ffmpeg (preferred)."""
    if not _ffmpeg_available():
        return False
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(fps),
        "-i", os.path.join(frame_glob_dir, pattern),
        "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return os.path.isfile(out_path)
    except Exception:
        return False


def write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def default(o):
        import numpy as np
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return str(o)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=default)


def parse_resolution(text: str) -> Tuple[int, int]:
    if "x" in text.lower():
        w, h = text.lower().split("x")
        return int(w), int(h)
    n = int(text)
    return n, n
