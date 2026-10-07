"""V6.4 -- physics_common: the ONE world builder shared by every local and full trial.

Plan section 11 names this module's job: "unified static ROI, dynamic compound shapes, COM/inertia, parameters and
actor ID; shared by all solves". Plan section 5.2 is the reason it exists: the old desktop probe and the old ground
layout disagreed on TEN solver parameters, and neither wrote them to any JSON, so the only way to make one physical
world is to build both from one manifest. This module therefore contains NO literal mass, friction, restitution,
damping or margin. Everything comes from `v64_physics_manifest_r1.json`.

Modes are explicit rather than implied (plan section 11: "local diagnosis, real upstream and full single solve must
be clearly separate modes; production mode must reject diagnostic first-block input"). A caller states its mode and
`set_initial_state` refuses inputs that mode does not permit, instead of trusting the caller to remember.

The actor namespace:
    B            the recovered baseball (common convex hull, 0.145 kg)
    A            the original boombox.002 -- 37 source components as ONE rigid body
    R            the receiving box on the table (the paper proxy the desktop probe used)
    F01..F48     the ground chain, in station order
Unaltered native scene objects keep their own survey names and are never hidden or moved.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pybullet as p

ROOT = Path("/data/raw/huzijian/project1_database")
N11 = ROOT / "tmp/v63_node11"
DEFAULT_MANIFEST = ROOT / "tmp/v64_node12/v64_physics_manifest_r2.json"
SURVEY_DIR = N11 / "survey_r1"
LAYOUT = N11 / "layout_r6/layout.json"
COMMON = N11 / "common_assets_r1/manifest.json"
GEOMETRY_AUDIT = ROOT / "log/V6.2_execution/geometry_audit"

# The table surface height, read from the desktop probe rather than guessed. The probe placed R at
# `0.685922 + paper_dims[2]/2 + 0.0003`, so 0.685922 is the authored table top. It is recorded here as a named
# constant because the R->ground drop height is a real physical input, not a layout detail.
TABLE_TOP_Z = 0.685922
# The desktop probe's radio and receiving-box poses, and the ball's ORIGINAL probe start. These are probe states
# (plan section 6.1 says they are not film-ready); they are kept because the mechanism they produce is the thing
# being preserved, and the extension along the ballistic arc starts from exactly here.
PROBE_BALL_START = [-3.025, 11.30, 0.95]
PROBE_BALL_VELOCITY = [7.0, 0.0, -1.8119098614883202]
PROBE_TARGET_Z = 0.875
PROBE_R_XY = [-2.38, 11.27]

MODES = ("diagnostic", "upstream", "full")
# inputs that only the diagnostic mode may use. Plan section 6.2 permits a clearly marked diagnostic input to
# locate a fault, and section 7.1 forbids it in production; section 5.2's manifest already records the relay
# 5 rad/s probe as diagnostic-only with full_chain_acceptance false.
DIAGNOSTIC_ONLY_INPUTS = ("first_block_edge_rotation", "window_probe_omega")


class ModeViolation(RuntimeError):
    """Raised when a mode is handed an input the plan does not allow that mode to use."""


def load_manifest(path=DEFAULT_MANIFEST):
    path = Path(path)
    m = json.loads(path.read_text())
    if not m.get("loaders_must_use_this_file"):
        raise RuntimeError("manifest does not declare itself authoritative: " + str(path))
    return m


def _broadcast(value, n):
    return [list(value) for _ in range(n)]


class World:
    """One physical world, assembled only from the manifest."""

    def __init__(self, manifest_path=DEFAULT_MANIFEST, hz=960, mode="upstream", verbose=True, overrides=None,
                 layout_override=None):
        """`layout_override` lets a candidate layout be solved against the SAME manifest and the same static ROI, so
        a layout revision never silently carries a different physics definition with it (plan 5.2)."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self.hz = hz
        self.verbose = verbose
        self.M = load_manifest(manifest_path)
        self.W = self.M["world"]
        self.div = self.M["divergence_resolution"]
        # A declared override set, used ONLY by the sensitivity sweep (plan 7.2). It is recorded on the World so a
        # report can never present an override run as a nominal one, and the plan's requirement that the nominal
        # parameters stay fixed is enforced by every non-sweep caller passing nothing here.
        self.overrides = dict(overrides or {})
        for key, value in self.overrides.items():
            if key not in self.div:
                raise KeyError(f"unknown parameter override {key!r}; known: {sorted(self.div)}")
            if key == "gravity":
                self.W["gravity_m_s2"] = value
            self.div[key] = dict(self.div[key], chosen=value)
        self.margin = self.div["collision_margin"]["chosen"]
        self.dt = 1.0 / hz

        self.layout = (json.loads(Path(layout_override).read_text()) if layout_override
                       else json.loads(Path(self.M["sources"]["layout"]["path"]).read_text()))
        self.layout_path = str(layout_override or self.M["sources"]["layout"]["path"])
        self.common = json.loads(Path(self.M["sources"]["common_assets"]["path"]).read_text())
        self.survey = json.loads((SURVEY_DIR / "survey.json").read_text())

        self.client = p.connect(p.DIRECT)
        # Bind every pybullet call to THIS world's client. Without `physicsClientId`, pybullet defaults to client
        # 0, so a process that builds a second World silently drives the FIRST one: `p2_prio_r5` ran a no-input
        # control and then a real solve, and the real solve's `step()` was stepping the control's world, which is
        # why it reported R landing on F05 while the same physics in a single-World process reported F01. A
        # wrong-but-plausible number is far more dangerous here than an exception, so the id is passed explicitly.
        self.cid = self.client
        p.setGravity(*self.W["gravity_m_s2"], physicsClientId=self.cid)
        p.setPhysicsEngineParameter(numSolverIterations=self.W["numSolverIterations"],
                                    deterministicOverlappingPairs=self.W["deterministicOverlappingPairs"],
                                    contactBreakingThreshold=self.W["contactBreakingThreshold"],
                                    physicsClientId=self.cid)
        p.setTimeStep(self.dt, physicsClientId=self.cid)

        self.body_names = {}       # bodyUniqueId -> name
        self.actors = {}           # actor id -> bodyUniqueId
        self.kind = {}             # actor id -> 'box' | 'ball' | 'radio' | 'tape'
        self.link_count = {}       # actor id -> number of links
        self._static = []
        self._radio_parts = None
        self._ball_hull = None
        self._load_meshes()
        self._build_static_roi()
        self._build_dynamic()

    # -----------------------------------------------------------------------------------------
    # geometry
    # -----------------------------------------------------------------------------------------
    def _load_meshes(self):
        hull_path = N11 / "baseball_probe_r3/baseball_common_hull.npz"
        self._ball_hull = np.load(hull_path)
        # the radio's 37 convex components: prefer the shared library, fall back to the probe's own export
        parts = self.common["assets"]["radio"].get("parts")
        files = []
        if parts:
            for part in parts:
                mf = part.get("mesh_file")
                if mf and Path(mf).exists():
                    files.append(Path(mf))
        if len(files) != 37:
            files = sorted((N11 / "baseball_probe_r3").glob("radio_common_*.npz"))
        if len(files) != 37:
            raise RuntimeError(f"expected 37 radio components, found {len(files)}")
        self._radio_files = files
        # the ring tape, if the layout still contains it
        self._tape_files = []
        tp = self.common["assets"]["tape"].get("parts")
        if tp:
            for part in tp:
                mf = part.get("mesh_file")
                if mf and Path(mf).exists():
                    self._tape_files.append(Path(mf))
        if self.verbose:
            print(f"  radio components: {len(files)}")
            print(f"  tape wedges     : {len(self._tape_files)}")
            print(f"  ball hull       : {len(self._ball_hull['vertices'])} verts / "
                  f"{len(self._ball_hull['triangles'])} triangles")

    # -----------------------------------------------------------------------------------------
    # every pybullet call goes through these, so the client id can never be forgotten
    # -----------------------------------------------------------------------------------------
    def _P(self, fn, *a, **k):
        k.setdefault("physicsClientId", self.cid)
        return fn(*a, **k)

    def move_actor(self, oid, position, quaternion=None):
        """Reposition a dynamic actor. Uses this world's client, so callers never touch a bare `p.*` call."""
        body = self.actors[oid]
        if quaternion is None:
            _pos, quaternion = self._P(p.getBasePositionAndOrientation, body)
        self._P(p.resetBasePositionAndOrientation, body, list(position), list(quaternion))
        return body

    def actor_pose(self, oid):
        return self._P(p.getBasePositionAndOrientation, self.actors[oid])

    def park_ball(self, where=(500.0, 500.0, 500.0)):
        """The no-input control: the ball is placed far outside the ROI with zero velocity rather than deleted, so
        the actor set, the contact-pair set and the static build stay identical; only its influence is removed."""
        body = self.actors["B"]
        self._P(p.resetBasePositionAndOrientation, body, list(where), [0, 0, 0, 1])
        self._P(p.resetBaseVelocity, body, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        return body

    def close(self):
        """Release this world's physics client. A process that builds several Worlds should call this, because each
        World owns its own client and an unreleased client keeps its whole body set and contact cache alive."""
        if getattr(self, "cid", None) is not None:
            try:
                p.disconnect(physicsClientId=self.cid)
            except Exception:
                pass
            self.cid = None
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def _build_static_roi(self):
        """The native scene, exactly as surveyed. Transport chunking only; no welded caps, no added floor."""
        static_fric = self.div["static_friction"]["chosen"]
        rest = self.div["static_restitution"]["chosen"]
        for row in self.survey["objects"]:
            blob = np.load(SURVEY_DIR / row["file"])
            verts, tri = blob["vertices"], blob["triangles"]
            for start in range(0, len(tri), 3000):
                piece = tri[start:start + 3000]
                used, inverse = np.unique(piece, return_inverse=True)
                shape = self._P(p.createCollisionShape, p.GEOM_MESH, vertices=verts[used].tolist(),
                                indices=inverse.reshape(-1).tolist(), flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
                body = self._P(p.createMultiBody, 0, shape)
                self._P(p.changeDynamics, body, -1, lateralFriction=static_fric, restitution=rest,
                        collisionMargin=self.margin)
                self.body_names[body] = row["name"]
                self._static.append(body)

    def _apply_solver(self, body, rec, nlinks=-1):
        s = rec["solver"]
        for link in range(-1, nlinks if nlinks >= 0 else 0):
            self._P(p.changeDynamics, body, link, lateralFriction=s["lateralFriction"],
                    restitution=s["restitution"],
                    collisionMargin=s.get("collisionMargin", self.margin),
                    linearDamping=s.get("linearDamping", 0.0),
                    angularDamping=s.get("angularDamping", 0.0),
                    rollingFriction=s.get("rollingFriction", 0.0))

    def _compound(self, files, rec, position, orientation):
        shapes = [self._P(p.createCollisionShape, p.GEOM_MESH, vertices=np.load(f)["vertices"].tolist())
                  for f in files]
        n = len(shapes) - 1
        body = self._P(p.createMultiBody, baseMass=rec["mass_kg"], baseCollisionShapeIndex=shapes[0],
                       basePosition=list(position), baseOrientation=list(orientation),
                       linkMasses=[0.0] * n, linkCollisionShapeIndices=shapes[1:],
                       linkVisualShapeIndices=[-1] * n,
                       linkPositions=[[0, 0, 0]] * n, linkOrientations=[[0, 0, 0, 1]] * n,
                       linkInertialFramePositions=[[0, 0, 0]] * n,
                       linkInertialFrameOrientations=[[0, 0, 0, 1]] * n,
                       linkParentIndices=[0] * n, linkJointTypes=[p.JOINT_FIXED] * n,
                       linkJointAxis=[[0, 0, 0]] * n)
        self._apply_solver(body, rec, nlinks=n)
        return body, n

    def _build_dynamic(self):
        """Every dynamic actor, at its REAL settled pose. Plan 6.3: the settle start must be re-derived for the new
        real support surface, and both frequencies must share ONE frozen initial state."""
        # --- R: the receiving box on the table, at the probe's own pose.
        # Its solver values come from the manifest's dedicated "R" record, NOT from a ground box and NOT from a
        # divergence row: R is a desktop actor that exists in only one of the two old worlds, so its friction is its
        # own definition. Reading it from a fabricated divergence row is exactly the error that stopped R falling.
        r_rec = dict(self.M["objects"]["R"])
        paper_dims = np.array(r_rec["dims_m"], dtype=float)
        r_shape = self._P(p.createCollisionShape, p.GEOM_BOX, halfExtents=r_rec["canonical_half_extents_m"])
        r_pos = [PROBE_R_XY[0], PROBE_R_XY[1], TABLE_TOP_Z + paper_dims[2] / 2 + 0.0003]
        r_body = self._P(p.createMultiBody, r_rec["mass_kg"], r_shape, basePosition=r_pos)
        self._apply_solver(r_body, r_rec)
        self.actors["R"] = r_body
        self.kind["R"] = "box"
        self.link_count["R"] = 0
        self.body_names[r_body] = "R"
        self.r_rec = r_rec
        self.r_start = r_pos

        # --- A: the radio, 37 components, base origin at the authored body centre
        a_rec = self.M["objects"]["A"]
        audit = json.loads((GEOMETRY_AUDIT / "audit.json").read_text())
        rv = np.load(GEOMETRY_AUDIT / "boombox.002.npz")["vertices"]
        comp0 = audit["objects"]["boombox.002"]["components"][0]["indices"]
        body_verts = rv[comp0]
        centre = ((body_verts.min(0) + body_verts.max(0)) / 2).tolist()
        a_body, a_n = self._compound(self._radio_files, a_rec, centre, [0, 0, 0, 1])
        self.actors["A"] = a_body
        self.kind["A"] = "radio"
        self.link_count["A"] = a_n
        self.body_names[a_body] = "A"
        self.a_centre = centre

        # --- B: the ball, common convex hull, 0.145 kg
        b_rec = self.M["objects"]["B"]
        b_shape = self._P(p.createCollisionShape, p.GEOM_MESH, vertices=self._ball_hull["vertices"].tolist())
        b_body = self._P(p.createMultiBody, b_rec["mass_kg"], b_shape, basePosition=PROBE_BALL_START)
        self._P(p.changeDynamics, b_body, -1, lateralFriction=b_rec["solver"]["lateralFriction"],
                restitution=b_rec["solver"]["restitution"],
                collisionMargin=b_rec["solver"]["collisionMargin"],
                ccdSweptSphereRadius=b_rec["solver"]["ccdSweptSphereRadius"],
                contactProcessingThreshold=b_rec["solver"]["contactProcessingThreshold"])
        self.actors["B"] = b_body
        self.kind["B"] = "ball"
        self.link_count["B"] = 0
        self.body_names[b_body] = "B"

        # --- F01..F48: the ground chain at its settled poses
        for row in self.layout["objects"]:
            oid = row["id"]
            rec = self.M["objects"][oid]
            key = rec["asset_key"]
            if key == "tape" and self._tape_files:
                body, n = self._compound(self._tape_files, rec, row["settled_position"],
                                         row["settled_quaternion_xyzw"])
                self._P(p.changeDynamics, body, -1, localInertiaDiagonal=rec["inertia_kg_m2"])
                self.kind[oid] = "tape"
            elif key == "tape":
                # plan section 4.4 substitute: the ring is replaced by approved small boxes. The actor id stays
                # stable so the event table and camera work do not silently rename anything.
                body, n = self._make_box(rec, row["settled_position"], row["settled_quaternion_xyzw"])
                self.kind[oid] = "box"
            else:
                body, n = self._make_box(rec, row["settled_position"], row["settled_quaternion_xyzw"])
                self.kind[oid] = "box"
            self.actors[oid] = body
            self.link_count[oid] = n
            self.body_names[body] = oid

        if self.verbose:
            print(f"  dynamic actors: {len(self.actors)} "
                  f"({sum(1 for k in self.kind.values() if k == 'box')} boxes, "
                  f"{sum(1 for k in self.kind.values() if k == 'tape')} tape, ball, radio)")

    def _make_box(self, rec, position, orientation):
        shape = self._P(p.createCollisionShape, p.GEOM_BOX, halfExtents=rec["canonical_half_extents_m"])
        body = self._P(p.createMultiBody, rec["mass_kg"], shape, basePosition=list(position),
                       baseOrientation=list(orientation))
        self._apply_solver(body, rec)
        return body, 0

    # -----------------------------------------------------------------------------------------
    # initial state -- mode-gated
    # -----------------------------------------------------------------------------------------
    def ballistic_extension_tau(self, target_flight_s):
        """How far back along the SAME ballistic arc the probe start must move to buy visible flight.

        The probe start is already on the real arc: the velocity was solved so the ball reaches
        `PROBE_TARGET_Z` at the contact, so extending backwards needs no new tuning. Going back by tau with the
        SAME velocity gives P0' = P0 - V*tau - g*tau^2/2, which is exact, not fitted.
        """
        g = np.array(self.W["gravity_m_s2"], dtype=float)
        v = np.array(PROBE_BALL_VELOCITY, dtype=float)
        p0 = np.array(PROBE_BALL_START, dtype=float)
        return p0 - v * target_flight_s - 0.5 * g * target_flight_s ** 2

    def set_initial_state(self, extend_flight_s=None, diagnostic=None):
        """Place every actor in the state this run starts from.

        `diagnostic` may only be supplied in diagnostic mode. In upstream and full mode any diagnostic input is a
        hard error, because plan section 7.1 requires production to run from the unified real initial state with
        nothing injected beyond the ball's declared initial condition.
        """
        if diagnostic and self.mode != "diagnostic":
            raise ModeViolation(
                f"mode {self.mode!r} may not use a diagnostic input; "
                f"plan 7.1 requires production to start from the unified real initial state. "
                f"got {sorted(diagnostic)} of {DIAGNOSTIC_ONLY_INPUTS}")
        start = np.array(PROBE_BALL_START, dtype=float)
        if extend_flight_s:
            start = self.ballistic_extension_tau(extend_flight_s)
        p.resetBasePositionAndOrientation(self.actors["B"], start.tolist(), [0, 0, 0, 1], physicsClientId=self.cid)
        p.resetBaseVelocity(self.actors["B"], list(PROBE_BALL_VELOCITY), [0, 0, 0], physicsClientId=self.cid)
        self.ball_start = start.tolist()
        self.flight_extension_s = float(extend_flight_s or 0.0)
        self.diagnostic = diagnostic
        return start.tolist()

    # -----------------------------------------------------------------------------------------
    # stepping and recording
    # -----------------------------------------------------------------------------------------
    def step(self, steps, record=True, pairs=None, static_pairs=None, static_every=16, full_contacts_every=0,
             contact_every=4):
        """Advance the simulation, recording per SUBSTEP as plan 7.1 requires.

        CONTACT COLLECTION -- two earlier forms were wrong, so the history is recorded here:

          * v1 read an untargeted `getContactPoints()` and took only `len(...)` of it. It spent ~30 minutes of CPU
            and logged nothing useful.
          * v2 tracked 192 TARGETED `getContactPoints(a, b)` pairs every substep. Exact, but the corrected profile
            (`p2_profile_r4.py`) measured 45.8 ms/substep for it, because each call re-runs narrowphase for a pair
            the solver has already resolved.
          * v3 (current) reads the post-step contact cache ONCE per recorded substep and filters to the tracked
            pairs in Python: 0.393 ms/substep on the same profile. The earlier claim that this is "240x cheaper"
            came from a profile that never ITERATED the returned list, i.e. it priced the pybullet call and not the
            Python consumption loop; acting on that conclusion made one 5 s solve go from 296 s to 463 s. The cache
            read is the right form, but it is not free.

        Contacts are recorded on a CADENCE rather than every substep. That is defensible because plan 7.3 makes the
        penetration gate an INDEPENDENT geometric check and forbids using `cp[8]` as the conclusion, so this log is
        a diagnostic aid rather than evidence. A cadence can miss a contact lasting fewer than `contact_every`
        substeps (4 substeps = 4.2 ms at 960 Hz), so the cadence is stored on the World and reported with results.

        Every pybullet call passes `physicsClientId`. The default is client 0, so a process that builds a second
        World would otherwise silently drive the FIRST one -- which is exactly what happened: a run that built a
        no-input control and then a real solve reported R landing on F05, while the identical physics in a
        single-World process reported F01. A wrong-but-plausible number is more dangerous here than an exception.
        """
        ids = list(self.actors)
        bodies = [self.actors[i] for i in ids]
        if record:
            self.pos = {i: np.empty((steps + 1, 3)) for i in ids}
            self.quat = {i: np.empty((steps + 1, 4)) for i in ids}
            self.linvel = {i: np.empty((steps + 1, 3)) for i in ids}
            self.angvel = {i: np.empty((steps + 1, 3)) for i in ids}
            for i, b in zip(ids, bodies):
                pos, quat = self._P(p.getBasePositionAndOrientation, b)
                self.pos[i][0] = pos
                self.quat[i][0] = quat
                lv, av = self._P(p.getBaseVelocity, b)
                self.linvel[i][0] = lv
                self.angvel[i][0] = av
        if pairs is None:
            pairs = self.default_pairs()
        # A set of frozensets, for filtering the contact cache in Python. `pairs` is kept as the declared
        # tracked-pair list so the record states what was watched.
        self.pairs = pairs
        wanted = {frozenset((a, b)) for a, b in pairs}
        if static_pairs:
            wanted |= {frozenset((a, b)) for a, b in static_pairs}
        self.contacts = []
        self.max_penetration = 0.0
        self.worst_penetration = None
        for s in range(steps):
            self._P(p.stepSimulation)
            t = (s + 1) / self.hz
            # ONE read of the post-step contact cache per recorded substep, then filter in Python. The measured
            # numbers and the two earlier wrong forms are documented in the docstring above.
            take_contacts = (contact_every <= 1) or (s % contact_every == 0)
            if take_contacts:
                for cp in self._P(p.getContactPoints):
                    ba, bb = cp[1], cp[2]
                    if wanted and frozenset((ba, bb)) not in wanted:
                        continue
                    dist = cp[8]
                    n1 = self.body_names.get(ba, "?")
                    n2 = self.body_names.get(bb, "?")
                    internal = (ba == bb)
                    self.contacts.append((t, n1, n2, dist, internal))
                    if dist < self.max_penetration:
                        self.max_penetration = dist
                        self.worst_penetration = {"t": t, "pair": [n1, n2], "distance": dist,
                                                  "internal": internal, "source": "cache"}
            if full_contacts_every and (s % full_contacts_every == 0):
                for cp in self._P(p.getContactPoints):
                    if cp[1] not in self.body_names or cp[2] not in self.body_names:
                        continue
                    dist = cp[8]
                    if dist < self.max_penetration:
                        self.max_penetration = dist
                        self.worst_penetration = {"t": t, "pair": [self.body_names[cp[1]],
                                                                   self.body_names[cp[2]]],
                                                  "distance": dist, "internal": cp[1] == cp[2],
                                                  "source": "full_sweep"}
            if record:
                for i, b in zip(ids, bodies):
                    pos, quat = self._P(p.getBasePositionAndOrientation, b)
                    self.pos[i][s + 1] = pos
                    self.quat[i][s + 1] = quat
                    lv, av = self._P(p.getBaseVelocity, b)
                    self.linvel[i][s + 1] = lv
                    self.angvel[i][s + 1] = av
        self.steps = steps
        self.sim_time = steps / self.hz
        self.contact_every = contact_every
        return self

    def default_pairs(self):
        """The pairs tracked on EVERY substep: dynamic-to-dynamic only.

        Roughly 240 pairs, which is the affordable set. The native statics are deliberately NOT in here, and that
        is a measurement-driven decision rather than an omission: an earlier version added every static within
        0.35 m of each ground part, which is ~176 statics x 48 parts and produced **8653 pairs / ~41 million
        getContactPoints calls**, i.e. tens of minutes of CPU for one 5-second solve with no intermediate result.
        Grass and leaf clusters are what inflate that count.

        Dropping per-substep static tracking does not weaken the penetration evidence, because plan 7.3 requires the
        penetration gate to be an INDEPENDENT geometric check and explicitly forbids treating `cp[8]` as the
        conclusion. Per-substep static contacts are therefore a convenience signal here, and the authoritative
        measurement is `validate_geometry.py` in P3. Static contacts are still sampled: see `static_pairs` and
        `step(full_contacts_every=...)`.
        """
        pairs = []
        if all(k in self.actors for k in ("B", "A", "R")):
            pairs += [(self.actors["B"], self.actors["A"]), (self.actors["A"], self.actors["R"]),
                      (self.actors["B"], self.actors["R"])]
        ground = [row["id"] for row in self.layout["objects"]]
        for i, g in enumerate(ground):
            # neighbours two apart: window [1,6] failed precisely because F03 reached F05 directly, so a
            # one-apart list would be blind to the fault under investigation
            for j in range(i + 1, min(i + 3, len(ground))):
                pairs.append((self.actors[g], self.actors[ground[j]]))
            if "R" in self.actors:
                pairs.append((self.actors[g], self.actors["R"]))
            if "B" in self.actors:
                pairs.append((self.actors[g], self.actors["B"]))
        return self._unique(pairs)

    def static_pairs(self, extra_actors=("R", "B")):
        """Dynamic-to-static pairs, tracked on a COARSE cadence rather than every substep.

        Only the actors whose interaction with the real ground is part of the story are included (the falling
        receiving box and the rebounding ball), and the static set is narrowed by AABB proximity to that actor's
        own start position. The point of the coarse cadence is that a static contact that matters -- R striking the
        floor, a box resting on a stone -- persists for many substeps, so sampling it every 16th substep still
        records it, while the exact contact instant comes from the dynamic-dynamic set or from P3's own checker.
        """
        pairs = []
        for name in extra_actors:
            if name not in self.actors:
                continue
            body = self.actors[name]
            for st in self._static_near(body):
                pairs.append((body, st))
        return self._unique(pairs)

    @staticmethod
    def _unique(pairs):
        seen, out = set(), []
        for a, b in pairs:
            k = (min(a, b), max(a, b))
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def _static_near(self, body):
        """Static bodies whose AABB comes within a reach radius of this body's start AABB.

        The radius is the body's own largest dimension (plus a small clearance), i.e. how far any part of it could
        reach while tipping, rather than a fixed generous box that would sweep in unrelated grass.
        """
        if not hasattr(self, "_static_aabbs"):
            self._static_aabbs = []
            for st in self._static:
                try:
                    self._static_aabbs.append((st, p.getAABB(st)))
                except Exception:
                    pass
        lo, hi = p.getAABB(body)
        reach = max(hi[i] - lo[i] for i in range(3)) + 0.05
        out = []
        for st, (slo, shi) in self._static_aabbs:
            if (slo[0] - reach <= hi[0] and lo[0] <= shi[0] + reach
                    and slo[1] - reach <= hi[1] and lo[1] <= shi[1] + reach
                    and slo[2] - reach <= hi[2] and lo[2] <= shi[2] + reach):
                out.append(st)
        return out

    # -----------------------------------------------------------------------------------------
    # event extraction
    # -----------------------------------------------------------------------------------------
    def first_contact_time(self, a, b, external_only=True):
        """First time a and b touched. `external_only` drops intra-body seams, per plan 5.2."""
        for t, n1, n2, dist, internal in self.contacts:
            if internal and external_only:
                continue
            if {n1, n2} == {a, b}:
                return t
        return None

    def tilt_deg(self, actor):
        """Angle between the actor's local up axis and world up. Used for the 'tipped past ~60 degrees' gate."""
        q = self.quat[actor][-1]
        rot = np.array(p.getMatrixFromQuaternion(q.tolist())).reshape(3, 3)
        up_local = np.array([0, 0, 1.0])
        up_world = rot @ up_local
        return float(np.degrees(np.arccos(np.clip(up_world[2], -1.0, 1.0))))

    def peak_tilt_deg(self, actor):
        rot = np.array([p.getMatrixFromQuaternion(q.tolist()) for q in self.quat[actor]]).reshape(-1, 3, 3)
        ups = rot @ np.array([0, 0, 1.0])
        return float(np.degrees(np.arccos(np.clip(ups[:, 2], -1.0, 1.0))).max())

    def displacement(self, actor):
        return float(np.linalg.norm(self.pos[actor][-1] - self.pos[actor][0]))

    def responded(self, actor, tilt_threshold=5.0, disp_threshold=0.004):
        """A relay part 'responded' only if it actually moved. Plan 6.2 forbids calling a whole bridge passed on a
        single `translation > 4 cm` test, so both angle and displacement are reported and the caller decides."""
        return (self.peak_tilt_deg(actor) > tilt_threshold) or (self.displacement(actor) > disp_threshold)

    def summary(self):
        return {
            "mode": self.mode, "hz": self.hz, "sim_time": self.sim_time,
            "ball_start": getattr(self, "ball_start", None),
            "flight_extension_s": getattr(self, "flight_extension_s", 0.0),
            "max_penetration_m": self.max_penetration,
            "worst_penetration": self.worst_penetration,
            "contact_records": len(self.contacts),
        }
