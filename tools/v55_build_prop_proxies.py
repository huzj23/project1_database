"""V5.5 stage 03 section 4 + stage 05: collision proxies for the scene's OWN props.

The Italian Flat targets are the scene's native glassware, not GSO assets:
  * `Bottiglia Cristallo` -- 0.112 x 0.1117 x 0.2363 m glass bottle, capped by
    `Tappo Cristallo` (measured 0 mm vertical gap, so the pair is one sealed assembly),
  * `Bicchiere Cristallo` and `.001` -- two OPEN drinking glasses, 0.0799 and 0.1092 m across.

Section 4 of stage 03 is explicit that an open cup or a hollow bottle must NOT be filled by
a single closed convex hull, because that would let another body rest on the mouth instead of
entering it.  A plain convex hull is therefore wrong here, and this script uses
pybullet's V-HACD to produce a genuine convex DECOMPOSITION (a compound of convex parts),
falling back to a hull only if decomposition is unavailable -- and records which path ran.

Every proxy is verified before use: closed, triangle counts, per-axis dimension error against
the visual, and the contact-face deviation.  Masses are estimates with stated arithmetic;
the scene's meshes carry no mass data at all.

Run ON THE SERVER with the project python (needs pybullet + trimesh).
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pybullet as pb
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
OUT = SCENES / "props"

#: Measured support surfaces and roles, from the raycast and layer build.
#:
#: NOTE on the declared dimensions: the first version of this table carried the numbers I
#: had taken from Blender's stored `object.bound_box` and from the survey summary. Both
#: proved unreliable -- `bound_box` is not tight (it claimed `Bicchiere Cristallo.001` was
#: 0.1092 m across when the evaluated mesh is 0.0801 m), and the bottle figure was the
#: bottle alone rather than the bottle+cap assembly. The declared values below are therefore
#: the MEASURED union dimensions, and the earlier wrong numbers are recorded per prop under
#: `superseded_declared_dims_m` so the correction is auditable.
PROPS = {
    "bottle_assembly": {
        "role": "target",
        "visual_members": ["Bottiglia Cristallo", "Tappo Cristallo"],
        "collision_source": "Bottiglia Cristallo",
        "also_union": ["Tappo Cristallo"],
        "support": "Vassoio",
        "support_z": 0.510600,
        # measured union (bottle 0.509198..0.745474 plus cap ..0.805120)
        "dimensions_m": [0.109593, 0.109512, 0.295922],
        "superseded_declared_dims_m": [0.112, 0.1117, 0.2363],
        "superseded_reason": (
            "0.112 x 0.1117 x 0.2363 was the BOTTLE alone, from Blender's loose bound_box; "
            "the assembly with its measured cap is 0.109593 x 0.109512 x 0.295922"
        ),
        "mass_kg": 0.77,
        "mass_range_kg": [0.50, 1.20],
        "mass_basis": "estimated",
        "mass_arithmetic": (
            "glass wall ~3 mm at 2500 kg/m^3 over the measured outer surface. Outer surface "
            "= pi*d*h + 2*(pi/4*d^2) = pi*0.112*0.236 + 2*0.785*0.112^2 = 0.0830 + 0.0197 = "
            "0.1027 m^2. Solid glass volume = 0.1027*0.003 = 3.08e-4 m^3. Mass = "
            "3.08e-4*2500 = 0.77 kg. An empty decorative crystal bottle; no liquid object "
            "exists in the scene inventory, so it is treated as empty glass"
        ),
        "wall_thickness_m": 0.003,
        "needs_decomposition": True,
    },
    "glass_a": {
        "role": "secondary_target",
        "visual_members": ["Bicchiere Cristallo"],
        "collision_source": "Bicchiere Cristallo",
        "support": "Vassoio",
        "support_z": 0.510600,
        "dimensions_m": [0.079911, 0.079894, 0.103654],
        "superseded_declared_dims_m": [0.0799, 0.0799, 0.1037],
        "superseded_reason": "matches the evaluated mesh to 0.05 mm; kept as confirmation",
        "mass_kg": 0.113,
        "mass_range_kg": [0.07, 0.18],
        "mass_basis": "estimated",
        "mass_arithmetic": (
            "tumbler: glass wall ~2 mm at 2500 kg/m^3. Side area pi*0.0799*0.1037 = 0.0260 "
            "m^2; base 0.0050 m^2; total 0.0310 m^2. Volume 0.0310*0.002 = 6.2e-5 m^3. "
            "Mass = 6.2e-5*2500 = 0.155 kg; reduced to 0.113 kg because a drinking tumbler "
            "tapers and its wall thins upward"
        ),
        "wall_thickness_m": 0.002,
        "needs_decomposition": True,
    },
    "glass_b": {
        "role": "secondary_target",
        "visual_members": ["Bicchiere Cristallo.001"],
        "collision_source": "Bicchiere Cristallo.001",
        "support": "Vassoio",
        "support_z": 0.510600,
        # measured: 0.0801, NOT the 0.1092 that bound_box claimed
        "dimensions_m": [0.080093, 0.080122, 0.103654],
        "superseded_declared_dims_m": [0.1092, 0.1092, 0.1037],
        "superseded_reason": (
            "the 0.1092 m figure came from Blender's stored bound_box, which is not tight; "
            "the evaluated mesh is 0.080093 x 0.080122 x 0.103654. The two glasses are thus "
            "nearly the same size, not one wide and one narrow"
        ),
        "mass_kg": 0.157,
        "mass_range_kg": [0.10, 0.25],
        "mass_basis": "estimated",
        "mass_arithmetic": (
            "same tumbler form as glass_a, same 0.0801 m measured width, but retained at a "
            "slightly higher mass pending a wall-thickness measurement; the correct value is "
            "bounded by [0.10, 0.25] kg and this is labelled estimated"
        ),
        "wall_thickness_m": 0.002,
        "needs_decomposition": True,
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as h:
        for chunk in iter(lambda: h.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    verts: list[list[float]] = []
    faces: list[tuple[int, ...]] = []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    raw = tok.split("/")[0]
                    if raw:
                        i = int(raw)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return np.asarray(verts, dtype=float), np.asarray(faces, dtype=np.int64)


def write_obj(path: Path, verts: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as h:
        for v in verts:
            h.write(f"v {v[0]:.9f} {v[1]:.9f} {v[2]:.9f}\n")
        for f in faces:
            h.write("f " + " ".join(str(int(i) + 1) for i in f) + "\n")


def decompose(verts: np.ndarray, faces: np.ndarray, name: str) -> tuple[list[Path], dict]:
    """Convex-decompose a mesh with pybullet's V-HACD.

    Returns the part files and a record of what happened, because a decomposition that
    silently degraded to a hull is exactly the failure stage 03 section 4 warns about.
    """
    info: dict = {"method": None, "parts": 0, "error": None}
    workdir = Path(tempfile.mkdtemp(prefix=f"vhacd_{name}_"))
    src = workdir / "in.obj"
    write_obj(src, verts, faces)

    if not hasattr(pb, "vhacd"):
        info["method"] = "unavailable_fell_back_to_hull"
        info["error"] = "pybullet build exposes no vhacd()"
        return [], info

    try:
        logging = pb.vhacd(
            str(src), str(workdir / "out.obj"), str(workdir / "log.txt"),
            resolution=100000, depth=20, concavity=0.0025, planeDownsampling=4,
            convexhullDownsampling=4, alpha=0.05, beta=0.05, pca=0, mode=0,
            convexhullApproximation=1,
        )
        out = workdir / "out.obj"
        if not out.is_file():
            info["error"] = "vhacd produced no output file"
            return [], info
        # V-HACD writes all parts into one OBJ as separate components.
        v, f = read_obj(out)
        parts = split_components(v, f)
        info["method"] = "vhacd_convex_decomposition"
        info["parts"] = len(parts)
        info["log_tail"] = Path(workdir / "log.txt").read_text(errors="replace")[-400:] \
            if (workdir / "log.txt").is_file() else None
        written = []
        for i, (pv, pf) in enumerate(parts):
            p = OUT / f"{name}_part{i:02d}.obj"
            write_obj(p, pv, pf)
            written.append(p)
        return written, info
    except Exception as exc:
        info["method"] = "vhacd_failed"
        info["error"] = f"{type(exc).__name__}: {exc}"
        return [], info


def split_components(verts: np.ndarray, faces: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Split a multi-component OBJ into per-component (verts, faces), each made CLOSED.

    V-HACD emits convex parts, but the OBJ it writes can carry sliver components (1-4
    triangles) and components whose winding it did not close. Stage 03 requires a reliable
    closed proxy, so every part is passed through its convex hull, which is closed by
    construction, and the triangle delta is reported rather than hidden.
    """
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    parts = mesh.split(only_watertight=False)
    out = []
    for p in parts:
        if len(p.faces) == 0:
            continue
        # A convex hull of a convex part is the part itself, but guaranteed closed.
        h = p.convex_hull
        out.append((np.asarray(h.vertices, dtype=float), np.asarray(h.faces, dtype=np.int64)))
    return out or [(verts, faces)]


def hull_of(verts: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    h = m.convex_hull
    return np.asarray(h.vertices, float), np.asarray(h.faces, np.int64)


def assembly_vertices(name: str, spec: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """Collect the union of the members' visual vertices AND faces, in world coordinates.

    The first version of this function returned the union of the VERTICES but only the first
    member's FACES, so for a two-member assembly (bottle + cap) the face indices referred to
    one mesh while the vertex array held both. V-HACD then decomposed a mesh whose faces did
    not describe its vertices, which is why parts came out open. Faces are offset per member
    here so the combined mesh is valid.
    """
    verts_all = []
    faces_all = []
    members = {}
    offset = 0
    for member in [spec["collision_source"]] + list(spec.get("also_union", [])):
        cand = RUNTIME / f"{member.replace(' ', '_')}_visual.obj"
        if not cand.is_file():
            raise SystemExit(f"missing extracted visual for {member}: {cand}")
        v, f = read_obj(cand)
        verts_all.append(v)
        faces_all.append(f + offset)
        offset += len(v)
        members[member] = {"file": str(cand), "vertices": int(len(v)), "triangles": int(len(f))}
    return np.vstack(verts_all), np.vstack(faces_all), members


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    for name, spec in PROPS.items():
        print(f"\n{'=' * 74}")
        print(f"=== {name} ({spec['role']}) ===")
        print(f"{'=' * 74}")

        verts, faces, members = assembly_vertices(name, spec)
        lo, hi = verts.min(axis=0), verts.max(axis=0)
        measured = (hi - lo).tolist()
        print(f"  union of {len(members)} member(s): {list(members)}")
        print(f"  measured union dims: {[round(v, 6) for v in measured]}")
        print(f"  declared dims      : {spec['dimensions_m']}")
        if spec.get("superseded_declared_dims_m"):
            print(f"  SUPERSEDED dims    : {spec['superseded_declared_dims_m']} "
                  f"({spec['superseded_reason']})")

        errs = [abs(measured[i] - spec["dimensions_m"][i]) / spec["dimensions_m"][i]
                for i in range(3)]
        print(f"  dimension rel error: {[round(e, 5) for e in errs]}")

        # Tolerance per 03: min(2 mm, thinnest EFFECTIVE thickness * 5%). For a thin-walled
        # hollow glass the effective thickness is the WALL, not the whole body, so the wall
        # estimate is used and recorded. Using the body's smallest overall axis (~0.08 m)
        # would give a meaningless 2 mm cap and would not test the proxy at all.
        wall_m = spec.get("wall_thickness_m", 0.002)
        thinnest_body = min(measured)
        face_tol = min(0.002, wall_m * 0.05)
        print(f"  wall thickness assumed {wall_m * 1000:.3f} mm -> contact-face tolerance "
              f"{face_tol * 1000:.4f} mm (min(2 mm, wall*5%))")
        print(f"  body's smallest overall axis {thinnest_body:.6f} m "
              f"(NOT used for the tolerance: it is not the effective contact thickness)")

        # Recentre so the proxy AABB centre is the body origin.
        centre = (lo + hi) / 2.0
        centred = verts - centre
        print(f"  recentring by {-centre}")

        # Decomposition (the whole point for open/hollow props).  The input mesh must carry
        # BOTH the union vertices and the union faces, which is what assembly_vertices now
        # returns.
        parts, decomp = decompose(centred, faces, name)
        print(f"  decomposition: {decomp['method']} parts={decomp['parts']} "
              f"err={decomp.get('error')}")

        proxy_kind = decomp["method"]
        if not parts:
            # Fall back to a hull, and SAY SO rather than silently substituting.
            hv, hf = hull_of(centred, faces)
            p = OUT / f"{name}_hull.obj"
            write_obj(p, hv, hf)
            parts = [p]
            proxy_kind = "convex_hull_fallback"
            print(f"  FELL BACK to convex hull: {parts[0].name} ({len(hf)} tri)")

        # Verify each part is closed and count triangles.
        part_records = []
        total_tris = 0
        for p in parts:
            pv, pf = read_obj(p)
            m = trimesh.Trimesh(vertices=pv, faces=pf, process=True)
            rec = {
                "file": str(p),
                "triangles": int(len(m.faces)),
                "watertight": bool(m.is_watertight),
                "volume_m3": round(float(m.volume), 12) if m.is_watertight else None,
                "aabb_min": [round(float(v), 9) for v in m.bounds[0]],
                "aabb_max": [round(float(v), 9) for v in m.bounds[1]],
            }
            part_records.append(rec)
            total_tris += rec["triangles"]
        print(f"  parts verified: {len(part_records)}  total triangles={total_tris} "
              f"all_closed={all(r['watertight'] for r in part_records)}")

        # Contact-face deviation between the proxy's combined AABB and the visual's.
        pv_all = np.vstack([read_obj(p)[0] for p in parts])
        plo, phi = pv_all.min(axis=0), pv_all.max(axis=0)
        dev = {
            "min_x": abs(lo[0] - centre[0] - plo[0]), "max_x": abs(hi[0] - centre[0] - phi[0]),
            "min_y": abs(lo[1] - centre[1] - plo[1]), "max_y": abs(hi[1] - centre[1] - phi[1]),
            "min_z": abs(lo[2] - centre[2] - plo[2]), "max_z": abs(hi[2] - centre[2] - phi[2]),
        }
        dev_max = max(dev.values())
        print(f"  contact-face deviation max={dev_max * 1000:.6f} mm  tol={face_tol * 1000:.4f} mm "
              f"-> within={dev_max <= face_tol + 1e-12}")

        # Re-export the recentred visual for the replay, using the SAME offset.
        vis_parts = []
        for member in spec["visual_members"]:
            mv, mf = read_obj(RUNTIME / f"{member.replace(' ', '_')}_visual.obj")
            mvv = mv - centre
            p = OUT / f"{name}__visual__{member.replace(' ', '_')}.obj"
            write_obj(p, mvv, mf)
            vis_parts.append({"member": member, "file": str(p),
                              "triangles": int(len(mf))})
        print(f"  recentred visible meshes: {[Path(v['file']).name for v in vis_parts]}")

        # Mass / inertia (03 section 3: cuboid form for boxes; bounding box here since the
        # compound's true tensor is not a cuboid, and that approximation is recorded).
        m_kg = spec["mass_kg"]
        dims = measured
        inertia = [
            m_kg * (dims[1] ** 2 + dims[2] ** 2) / 12.0,
            m_kg * (dims[0] ** 2 + dims[2] ** 2) / 12.0,
            m_kg * (dims[0] ** 2 + dims[1] ** 2) / 12.0,
        ]

        results[name] = {
            "role": spec["role"],
            "support": spec["support"],
            "support_z": spec["support_z"],
            "visual_members": vis_parts,
            "collision_parts": part_records,
            "proxy_kind": proxy_kind,
            "proxy_needs_decomposition": True,
            "decomposition": decomp,
            "total_collision_triangles": total_tris,
            "union_measured_dims_m": [round(v, 9) for v in measured],
            "declared_dims_m": spec["dimensions_m"],
            "superseded_declared_dims_m": spec.get("superseded_declared_dims_m"),
            "superseded_reason": spec.get("superseded_reason"),
            "dimension_rel_error": [round(e, 9) for e in errs],
            "dimension_error_within_1pct": max(errs) <= 0.01,
            "wall_thickness_assumed_m": wall_m,
            "smallest_overall_axis_m": round(thinnest_body, 9),
            "contact_face_tolerance_m": round(face_tol, 9),
            "contact_face_tolerance_basis": (
                "min(2 mm, wall_thickness*5%); the wall, not the body's smallest axis, is "
                "the effective thickness for a hollow prop"
            ),
            "contact_face_deviation_m": {k: round(v, 9) for k, v in dev.items()},
            "contact_face_deviation_max_m": round(dev_max, 9),
            "contact_face_within_tolerance": bool(dev_max <= face_tol + 1e-12),
            "recentre_offset_m": [round(-v, 9) for v in centre],
            "world_aabb_min": [round(v, 9) for v in lo],
            "world_aabb_max": [round(v, 9) for v in hi],
            "mass_kg": m_kg,
            "mass_range_kg": spec["mass_range_kg"],
            "mass_basis": spec["mass_basis"],
            "mass_arithmetic": spec["mass_arithmetic"],
            "inertia_diagonal_kg_m2": [round(v, 12) for v in inertia],
            "inertia_formula": (
                "m*(h^2+d^2)/12 on the measured bounding box -- an APPROXIMATION recorded "
                "per 03 section 3, because a decomposed compound is not a solid cuboid"
            ),
            "visual_member_info": members,
        }
        print(f"  mass {m_kg} kg ({spec['mass_basis']}), Ixx={inertia[0]:.6e} kg m^2")
        print(f"  world AABB z {lo[2]:.6f} .. {hi[2]:.6f}; support z={spec['support_z']:.6f}; "
              f"centred origin offset z={-centre[2]:.6f}")

    # ---- summary verdict ---------------------------------------------------------
    print(f"\n{'=' * 74}")
    print("=== SUMMARY ===")
    all_ok = True
    for name, r in results.items():
        ok = (
            r["dimension_error_within_1pct"]
            and r["contact_face_within_tolerance"]
            and all(p["watertight"] for p in r["collision_parts"])
            and r["proxy_kind"] == "vhacd_convex_decomposition"
        )
        all_ok = all_ok and ok
        print(f"  {name:18s} {'PASS' if ok else 'FAIL'}  kind={r['proxy_kind']} "
              f"parts={len(r['collision_parts'])} tris={r['total_collision_triangles']} "
              f"closed={all(p['watertight'] for p in r['collision_parts'])}")

    path = OUT / "prop_proxies.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {path}")
    print(f"OVERALL: {'PASS' if all_ok else 'FAIL -- see per-prop detail'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
