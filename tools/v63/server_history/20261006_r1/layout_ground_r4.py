"""Server CPU full 48-object S-route and fail-closed initial geometry checks."""
from pathlib import Path
import json
import math
import numpy as np
import pybullet as p
from scipy.spatial.transform import Rotation

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node11/layout_r4'
OUT.mkdir(parents=True, exist_ok=False)
COMMON = ROOT / 'tmp/v63_node11/common_assets_r1'
SURVEY = ROOT / 'tmp/v63_node11/survey_r1'
assets = json.loads((COMMON / 'manifest.json').read_text())['assets']
survey = json.loads((SURVEY / 'survey.json').read_text())
sequence = (['paper'] * 4 + ['wii'] * 2
            + ['wii'] * 2 + ['dvd'] * 4 + ['cranium'] * 3 + ['trivial'] * 3
            + ['wii', 'wii', 'paper', 'tape', 'paper', 'wii', 'wii']
            + ['dvd'] * 4 + ['cranium'] * 6 + ['trivial'] * 5 + ['ouija'] * 2
            + ['ouija', 'cranium', 'trivial', 'trivial', 'paper', 'paper'])
assert len(sequence) == 48
cid = p.connect(p.DIRECT)
p.setGravity(0, 0, -9.81)
p.setTimeStep(1 / 960)
p.setPhysicsEngineParameter(numSolverIterations=100, deterministicOverlappingPairs=1)
names, statics, floors = {}, [], []
for row in survey['objects']:
    blob = np.load(SURVEY / row['file'])
    vertices, triangles = blob['vertices'], blob['triangles']
    for start in range(0, len(triangles), 3000):
        used, inverse = np.unique(triangles[start:start + 3000], return_inverse=True)
        shape = p.createCollisionShape(p.GEOM_MESH, vertices=vertices[used].tolist(),
                                       indices=inverse.tolist(), flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
        body = p.createMultiBody(0, shape)
        p.changeDynamics(body, -1, lateralFriction=.65, restitution=.03, collisionMargin=.0001)
        names[body] = row['name']
        statics.append(body)
        if row['name'] == 'Floor_main':
            floors.append(body)
            p.setCollisionFilterGroupMask(body, -1, 8, -1)

shapes = {}
for key, asset in assets.items():
    if key in sequence and key != 'tape':
        shapes[key] = p.createCollisionShape(p.GEOM_BOX, halfExtents=(np.array(asset['dims']) / 2).tolist())
ring_shapes = []
for part in assets['tape']['parts']:
    blob = np.load(part['mesh_file'])
    ring_shapes.append(p.createCollisionShape(p.GEOM_MESH, vertices=blob['vertices'].tolist()))


def rotation(theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])


def arc_route():
    xy = np.array([-2.17, 11.23])
    yaw = 0.
    samples = [[0., *xy, yaw]]
    distance = 0.
    # Entry, two opposing broad hairpins, exit. C1 continuous; camera is a
    # separate smooth path, not attached to these piecewise-curvature joints.
    for turn, radius in [(90, .60), (-180, .75), (180, .65)]:
        delta = math.radians(turn)
        curvature = math.copysign(1 / radius, delta)
        length = abs(delta) * radius
        old = xy.copy()
        old_yaw = yaw
        for frac in np.linspace(0, 1, max(2, round(length / .005)))[1:]:
            angle = old_yaw + frac * delta
            point = old + np.array([(math.sin(angle) - math.sin(old_yaw)) / curvature,
                                    (-math.cos(angle) + math.cos(old_yaw)) / curvature])
            samples.append([distance + frac * length, *point, angle])
        xy = np.array(samples[-1][1:3])
        yaw += delta
        distance += length
    for ds in np.linspace(0, 1.20, 241)[1:]:
        samples.append([distance + ds, *(xy + ds * np.array([math.cos(yaw), math.sin(yaw)])), yaw])
    return np.array(samples)


route = arc_route()
dims = {key: np.array(asset['dims']) for key, asset in assets.items() if 'dims' in asset}
tape = assets['tape']
dims['tape'] = np.array([2 * tape['outer_radius'], tape['width'], 2 * tape['outer_radius']])
pitches = []
for previous, following in zip(sequence[:-1], sequence[1:]):
    if previous == 'tape':
        pitch = .20
    elif following == 'tape':
        pitch = .10
    else:
        pitch = min(dims[previous][2] * .66,
                    dims[following][2] * .83 + (dims[previous][0] + dims[following][0]) / 2)
    pitches.append(pitch)
stations = np.r_[0., np.cumsum(pitches)]
scale = route[-1, 0] / stations[-1]
stations *= scale


def make_actor(key, position, yaw):
    quat = p.getQuaternionFromEuler([0, 0, yaw])
    mass = assets[key]['mass_estimate_kg']
    if key != 'tape':
        body = p.createMultiBody(mass, shapes[key], basePosition=position, baseOrientation=quat)
    else:
        n = len(ring_shapes) - 1
        body = p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=ring_shapes[0],
                                 basePosition=position, baseOrientation=quat,
                                 linkMasses=[0.] * n, linkCollisionShapeIndices=ring_shapes[1:],
                                 linkVisualShapeIndices=[-1] * n, linkPositions=[[0, 0, 0]] * n,
                                 linkOrientations=[[0, 0, 0, 1]] * n, linkInertialFramePositions=[[0, 0, 0]] * n,
                                 linkInertialFrameOrientations=[[0, 0, 0, 1]] * n, linkParentIndices=[0] * n,
                                 linkJointTypes=[p.JOINT_FIXED] * n, linkJointAxis=[[0, 0, 0]] * n)
        r2 = tape['outer_radius'] ** 2 + tape['inner_radius'] ** 2
        diag = [mass * (3 * r2 + tape['width'] ** 2) / 12, mass * r2 / 2,
                mass * (3 * r2 + tape['width'] ** 2) / 12]
        p.changeDynamics(body, -1, localInertiaDiagonal=diag)
    for link in range(-1, p.getNumJoints(body)):
        p.changeDynamics(body, link, lateralFriction=.45, restitution=.02, collisionMargin=.0001,
                         linearDamping=.015, angularDamping=.015, rollingFriction=.0002)
    return body


def fitted_pose(foot_xy, yaw, key):
    mat = rotation(yaw)
    if key == 'tape':
        local_points = [[0, -tape['width'] * .4, 0], [0, 0, 0], [0, tape['width'] * .4, 0]]
    else:
        d = dims[key]
        local_points = [[x * d[0] / 2, y * d[1] / 2, 0] for x in [-.95, 0, .95] for y in [-.95, 0, .95]]
    points = np.array(local_points) @ mat.T + np.array([*foot_xy, 0.])
    support = []
    for point in points:
        hits = p.rayTest([point[0], point[1], .5], [point[0], point[1], -.5], collisionFilterMask=8)
        hit = hits[0]
        support.append({'hit': names.get(hit[0], 'dynamic_or_miss'), 'z': hit[3][2], 'normal_z': hit[4][2]})
    if not all(row['hit'] == 'Floor_main' for row in support):
        return None, None, {'support': support, 'reason': 'floor ray miss'}
    xy = points[:, :2] - foot_xy
    z = np.array([r['z'] for r in support])
    if key == 'tape':
        # Its selected corridor is flat; a free-standing wheel on a slope would
        # start without the trigger. Reject that location instead of anchoring.
        a, b, c = 0., 0., float(z.max())
        residual = z - c
        if np.ptp(z) > .0002:
            return None, None, {'support': support, 'reason': 'ring slope'}
    else:
        a, b, c = np.linalg.lstsq(np.c_[xy, np.ones(len(xy))], z, rcond=None)[0]
        residual = z - (a * xy[:, 0] + b * xy[:, 1] + c)
    if np.ptp(residual) > .001:
        return None, None, {'support': support, 'reason': 'nonplanar footprint', 'residual_span': float(np.ptp(residual))}
    normal = np.array([-a, -b, 1.])
    normal /= np.linalg.norm(normal)
    heading = np.array([math.cos(yaw), math.sin(yaw), a * math.cos(yaw) + b * math.sin(yaw)])
    heading /= np.linalg.norm(heading)
    across = np.cross(normal, heading)
    matrix = np.column_stack([heading, across, normal])
    position = np.array([*foot_xy, c + residual.max() + .0003]) + normal * dims[key][2] / 2
    quat = Rotation.from_matrix(matrix).as_quat()
    return position.tolist(), quat.tolist(), {'support': support, 'normal': normal.tolist(),
                                               'residual_span': float(np.ptp(residual))}


def collision_gate(body):
    p.performCollisionDetection()
    contacts = []
    # Teleporting an exploratory placement must not reuse an old cached contact
    # manifold. Query fresh closest points against current broad-phase pairs.
    aabbs = [p.getAABB(body, link) for link in range(-1, p.getNumJoints(body))]
    lower = np.min([v[0] for v in aabbs], axis=0) - .002
    upper = np.max([v[1] for v in aabbs], axis=0) + .002
    pairs = p.getOverlappingObjects(lower.tolist(), upper.tolist()) or []
    fresh = []
    for other, link in set(pairs):
        if other != body:
            fresh.extend(p.getClosestPoints(body, other, .002, linkIndexB=link))
    for cp in fresh:
        if cp[8] < -.0010001:
            contacts.append({'other': names.get(cp[2], str(cp[2])), 'depth_m': -cp[8],
                             'position': cp[5], 'links': [cp[3], cp[4]]})
    return not contacts, contacts


records, failures = [], []
for index, (station, key) in enumerate(zip(stations, sequence)):
    nominal = np.array([np.interp(station, route[:, 0], route[:, j]) for j in [1, 2]])
    yaw = float(np.interp(station, route[:, 0], route[:, 3]))
    z = -.04 + dims[key][2] / 2 + .0003
    pos = [*nominal, z]
    body = make_actor(key, pos, yaw)
    name = 'F%02d' % (index + 1)
    names[body] = name
    tested = []
    accepted = False
    # Small placement corrections only. Curvature, counts and genuine surfaces
    # remain; no ground patch or uniform object scaling is introduced.
    offsets = [(0., 0.)] + [(a, b) for a in [0., -.015, .015, -.035, .035] for b in [-.01, .01, -.02, .02, -.04, .04, -.08, .08]]
    extra = [(a, b) for a in [-.09, -.06, -.03, 0., .03, .06, .09]
             for b in [-.12, -.09, -.06, -.03, 0., .03, .06, .09, .12]]
    offsets += sorted([v for v in extra if v not in offsets], key=lambda v: v[0] ** 2 + v[1] ** 2)
    for along, across in offsets:
        shift = rotation(yaw) @ [along, across, 0.]
        pos, quat, gates = fitted_pose(nominal + shift[:2], yaw, key)
        if pos is None:
            tested.append({'offset_m': [along, across], 'ok': False, 'gates': gates})
            continue
        p.resetBasePositionAndOrientation(body, pos, quat)
        ok, contacts = collision_gate(body)
        gates['contacts_over_1mm'] = contacts
        tested.append({'offset_m': [along, across], 'ok': ok, 'gates': gates})
        if ok:
            accepted = True
            break
    if not accepted:
        # Keep the nominal failing location clearly marked, don't render it as
        # a passed placement and don't hide the obstacle.
        pos = [*nominal, z]
        quat = p.getQuaternionFromEuler([0, 0, yaw])
        p.resetBasePositionAndOrientation(body, pos, quat)
        failures.append(name)
    records.append({'id': name, 'asset_key': key, 'asset_id': assets[key]['asset_id'], 'body': body,
                    'position': pos, 'quaternion_xyzw': quat,
                    'yaw': yaw, 'station_m': float(station), 'dims': dims[key].tolist(),
                    'mass_estimate_kg': assets[key]['mass_estimate_kg'], 'placement_ok': accepted,
                    'attempts': tested})
    print('PLACED', name, key, accepted, flush=True)

settle = {'status': 'NOT_RUN_INITIAL_GATE_FAILED'}
if not failures:
    peak_tilt = {r['id']: 0. for r in records}
    for step in range(1920):
        p.stepSimulation()
        if step % 16 == 0:
            for row in records:
                pos, quat = p.getBasePositionAndOrientation(row['body'])
                rot = np.array(p.getMatrixFromQuaternion(quat)).reshape((3, 3))
                initial_rot = np.array(p.getMatrixFromQuaternion(row['quaternion_xyzw'])).reshape((3, 3))
                tilt = math.degrees(math.acos(float(np.clip(initial_rot[:, 2] @ rot[:, 2], -1, 1))))
                peak_tilt[row['id']] = max(peak_tilt[row['id']], tilt)
    settle = {'status': 'PASS' if max(peak_tilt.values()) < 2 else 'FAIL', 'peak_tilt_deg': peak_tilt,
              'seconds': 2, 'hz': 960, 'input': 'no ball, no moving table actor, no impulses'}
    for row in records:
        pos, quat = p.getBasePositionAndOrientation(row['body'])
        row['settled_position'] = pos
        row['settled_quaternion_xyzw'] = quat
report = {'status': 'INITIAL_LAYOUT_PASS_PENDING_RELAY' if not failures and settle['status'] == 'PASS' else 'LAYOUT_NEEDS_REPAIR',
          'common_manifest': str(COMMON / 'manifest.json'), 'ground_count': len(records),
          'ground_asset_types': len(set(sequence)), 'route_length_m': float(route[-1, 0]),
          'total_absolute_turn_deg': 450., 'arc_radii_m': [.60, .75, .65],
          'note': 'Two opposing 180-degree main bends plus curved entry/straight exit; native slope fitted, grass/leaf clusters avoided. Need relay/swept validation.',
          'pitches_scale': float(scale), 'objects': records, 'route_samples': route.tolist(),
          'failed_placements': failures, 'settle': settle,
          'table_and_full_chain': 'NOT_INCLUDED_IN_THIS_DIAGNOSTIC'}
with (OUT / 'layout.json').open('x') as handle:
    json.dump(report, handle, indent=2)
p.disconnect(cid)
print('LAYOUT_COMPLETE', report['status'], failures, settle['status'], flush=True)
