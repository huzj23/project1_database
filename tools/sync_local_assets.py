"""Pull the assets needed for local realism samples from the server.

Local runs only need a handful of items; the full GSO library (1033 objects)
stays on the server.  This fetches:
  * a few GSO objects suitable as single actors
  * two Poly Haven HDRIs
  * one PBR ground material
  * one ReplicaCAD stage (for the fixed 3D-interior path)
"""

from __future__ import annotations

import argparse
import os
import posixpath
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ssh_ctl  # noqa: E402

WS = ssh_ctl.WORKSPACE
LOCAL_MODELS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

GSO_OBJECTS = [
    "Sootheze_Cold_Therapy_Elephant",
    "Room_Essentials_Fabric_Cube_Lavender",
    "Mad_Gab_Refresh_Card_Game",
    "Ecoforms_Plant_Container_GP16A_Coral",
    "Down_To_Earth_Orchid_Pot_Ceramic_Lime",
    "Whey_Protein_Vanilla",
]
HDRIS = ["empty_warehouse_01_4k.hdr", "studio_small_09_4k.hdr"]
PBR = [("concrete_textures", "concrete_floor_worn_001")]
STAGES = ["frl_apartment_stage.glb"]


def collect(sftp) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = []

    for name in GSO_OBJECTS:
        rdir = posixpath.join(WS, "models/gso", name)
        try:
            entries = sftp.listdir_attr(rdir)
        except IOError:
            print(f"  ! missing on server: {name}")
            continue
        for e in entries:
            if e.st_mode & 0o040000:
                continue
            plan.append((posixpath.join(rdir, e.filename),
                         os.path.join(LOCAL_MODELS, "gso", name, e.filename)))

    for h in HDRIS:
        plan.append((posixpath.join(WS, "models/hdri_hdr", h),
                     os.path.join(LOCAL_MODELS, "hdri_hdr", h)))

    for cat, asset in PBR:
        rdir = posixpath.join(WS, "models/pbr_textures", cat, f"{asset}.blend", "textures")
        try:
            entries = sftp.listdir_attr(rdir)
        except IOError:
            print(f"  ! missing PBR: {asset}")
            continue
        for e in entries:
            # skip the displacement map: large and unused by our material builder
            if "_disp_" in e.filename:
                continue
            plan.append((posixpath.join(rdir, e.filename),
                         os.path.join(LOCAL_MODELS, "pbr_textures", cat,
                                      f"{asset}.blend", "textures", e.filename)))

    for s in STAGES:
        plan.append((posixpath.join(WS, "models/backgrounds/replicad/stages", s),
                     os.path.join(LOCAL_MODELS, "backgrounds", "replicad", "stages", s)))
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=ssh_ctl.DEFAULT_ACCOUNT, choices=sorted(ssh_ctl.HOSTS))
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args(argv)

    client = ssh_ctl.connect(args.account)
    try:
        sftp = client.open_sftp()
        plan = collect(sftp)
        total = 0
        print(f"items: {len(plan)}")
        t0 = time.time()
        for remote, local in plan:
            try:
                size = sftp.stat(remote).st_size
            except IOError:
                print(f"  ! stat failed: {remote}")
                continue
            total += size
            if args.dry_run:
                continue
            os.makedirs(os.path.dirname(local), exist_ok=True)
            sftp.get(remote, local)
        dt = max(time.time() - t0, 1e-6)
        print(f"total {total/1048576:.1f} MB"
              + ("  (dry run)" if args.dry_run else f"  in {dt/60:.1f} min"))
        print(f"local root: {LOCAL_MODELS}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
