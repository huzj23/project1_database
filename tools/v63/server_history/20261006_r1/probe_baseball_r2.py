"""CPU limited feasibility: actual recovered baseball, original authored obstacles.

Not a full-chain/penetration acceptance. Common convex surface exports are saved
for subsequent rendering; no prescribed trajectories or hidden impulses.
"""
from pathlib import Path
import json
import math
import time
import numpy as np
import pybullet as p
import trimesh
from scipy.spatial import ConvexHull

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node11/baseball_probe_r2'
OUT.mkdir(parents=True, exist_ok=False)
GEO = ROOT / 'log/V6.2_execution/geometry_audit'
SURVEY = ROOT / 'tmp/v63_node11/survey_r1'
BALL_PATH = ROOT / 'models/asset_recovery/v63/sphere_baseball/20261006_original4k/baseball_01_4k.gltf'

ball_mesh = trimesh.load(str(BALL_PATH), force='mesh', process=False)
ball_vertices = np.asarray(ball_mesh.vertices, dtype=np.float64)
ball_centre = (ball_vertices.min(0) + ball_vertices.max(0)) / 2
ball_vertices -= ball_centre
ball_dims = np.ptp(ball_vertices, axis=0)
if not (.070 < ball_dims.min() and ball_dims.max() < .080):
    raise RuntimeError('unexpected recovered baseball scale: ' + str(ball_dims))
ball_hull = trimesh.Trimesh(vertices=ball_vertices, faces=ball_mesh.faces, process=False).convex_hull
np.savez_compressed(OUT / 'baseball_common_hull.npz', vertices=ball_hull.vertices,
                    triangles=ball_hull.faces, source_centre=ball_centre,
                    source_vertices=ball_vertices, source_triangles=ball_mesh.faces)

radio = np.load(GEO / 'boombox.002.npz')
rv = radio['vertices']
audit = json.loads((GEO / 'audit.json').read_text())
components = audit['objects']['boombox.002']['components']
body = rv[components[0]['indices']]
centre = (body.min(0) + body.max(0)) / 2
radio_parts = []
for i, comp in enumerate(components):
    verts = rv[comp['indices']] - centre
    hull = trimesh.convex.convex_hull(verts)
    np.savez_compressed(OUT / ('radio_common_%02d.npz' % i), vertices=hull.vertices, triangles=hull.faces)
    radio_parts.append(np.asarray(hull.vertices))

source_paper = ROOT / 'tmp/v63_shared_inputs/models/gso/Paper_Mario_Sticker_Star_Nintendo_3DS_Game/visual_geometry.obj'
pv = np.asarray([[float(v) for v in line.split()[1:4]] for line in source_paper.read_text().splitlines() if line.startswith('v ')])
paper_dims = np.ptp(pv, axis=0)[[2, 0, 1]]
survey = json.loads((SURVEY / 'survey.json').read_text())
statics = []
# Keep the full exported environment; ball rebounds and antenna contacts cannot
# ignore the wall, stones, leaves, or grass. Outside ROI requires later expansion.
for row in survey['objects']:
    blob = np.load(SURVEY / row['file'])
    verts, triangles = blob['vertices'], blob['triangles']
    # PyBullet's command transport cannot accept the entire evaluated grass mesh
    # as one vertex array. Exact triangle chunks retain every authored surface.
    for start in range(0, len(triangles), 3000):
        tri = triangles[start:start + 3000]
        used, inverse = np.unique(tri, return_inverse=True)
        statics.append((row['name'], verts[used], inverse.reshape((-1, 3))))


def run(vx, radio_mass, target_z=.875, hz=480, enabled=True):
    t0 = time.time()
    cid = p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81)
    p.setTimeStep(1 / hz)
    p.setPhysicsEngineParameter(numSolverIterations=120, deterministicOverlappingPairs=1,
                               contactBreakingThreshold=.001)
    names = {}
    for name, verts, tri in statics:
        shape = p.createCollisionShape(p.GEOM_MESH, vertices=verts.tolist(), indices=tri.ravel().tolist(), flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
        bid = p.createMultiBody(0, shape)
        p.changeDynamics(bid, -1, lateralFriction=.75, restitution=.03, collisionMargin=.0001)
        names[bid] = name
    shapes = [p.createCollisionShape(p.GEOM_MESH, vertices=verts.tolist()) for verts in radio_parts]
    count = len(shapes) - 1
    a = p.createMultiBody(baseMass=radio_mass, baseCollisionShapeIndex=shapes[0], basePosition=centre.tolist(),
                         linkMasses=[0.] * count, linkCollisionShapeIndices=shapes[1:],
                         linkVisualShapeIndices=[-1] * count, linkPositions=[[0, 0, 0]] * count,
                         linkOrientations=[[0, 0, 0, 1]] * count, linkInertialFramePositions=[[0, 0, 0]] * count,
                         linkInertialFrameOrientations=[[0, 0, 0, 1]] * count, linkParentIndices=[0] * count,
                         linkJointTypes=[p.JOINT_FIXED] * count, linkJointAxis=[[0, 0, 0]] * count)
    names[a] = 'A_radio'
    for link in range(-1, count):
        p.changeDynamics(a, link, lateralFriction=.8, restitution=.03, collisionMargin=.0001,
                         linearDamping=.02, angularDamping=.02)
    rs = p.createCollisionShape(p.GEOM_BOX, halfExtents=(paper_dims / 2).tolist())
    r = p.createMultiBody(.07, rs, basePosition=[-2.38, 11.27, .685922 + paper_dims[2] / 2 + .0003])
    p.changeDynamics(r, -1, lateralFriction=.4, restitution=.03, collisionMargin=.0001)
    names[r] = 'R_paper'
    b = None
    initial = [-3.025, 11.30, .95]
    flight = .263 / vx
    velocity = [vx, 0., (target_z - initial[2] + 4.905 * flight * flight) / flight]
    if enabled:
        bs = p.createCollisionShape(p.GEOM_MESH, vertices=np.asarray(ball_hull.vertices).tolist())
        b = p.createMultiBody(.145, bs, basePosition=initial)
        names[b] = 'B_baseball'
        p.resetBaseVelocity(b, velocity)
        p.changeDynamics(b, -1, lateralFriction=.45, restitution=.45, collisionMargin=.0001,
                         ccdSweptSphereRadius=.030, contactProcessingThreshold=0)
    events, samples = {}, []
    worst = {'distance': 0.}
    initial_contacts = []
    p.performCollisionDetection()
    for cp in p.getContactPoints():
        if cp[8] < -.001:
            initial_contacts.append({'pair': [names.get(cp[1]), names.get(cp[2])], 'distance': cp[8]})
    for step in range(int(2.5 * hz)):
        p.stepSimulation()
        now = (step + 1) / hz
        for first, second, label in [(b, a, 'B_A'), (a, r, 'A_R'), (b, r, 'B_R')]:
            if first is not None and p.getContactPoints(first, second) and label not in events:
                events[label] = now
        for cp in p.getContactPoints():
            if cp[8] < worst['distance']:
                worst = {'distance': cp[8], 't': now, 'pair': [names.get(cp[1]), names.get(cp[2])],
                         'link_indices': [cp[3], cp[4]], 'positions': [cp[5], cp[6]]}
        if step % max(1, hz // 120) == 0:
            ap, aq = p.getBasePositionAndOrientation(a)
            rp, rq = p.getBasePositionAndOrientation(r)
            rot = np.array(p.getMatrixFromQuaternion(aq)).reshape(3, 3)
            world = (body - centre) @ rot.T + ap
            samples.append({'t': now, 'A_position': ap, 'A_quaternion': aq,
                            'A_tilt_deg': math.degrees(math.acos(float(np.clip(rot[2, 2], -1, 1)))),
                            'A_body_min_z': float(world[:, 2].min()), 'R_position': rp, 'R_quaternion': rq,
                            'B_position': p.getBasePositionAndOrientation(b)[0] if b is not None else None})
    final = samples[-1]
    candidate = bool(enabled and 'B_A' in events and 'A_R' in events and events['B_A'] < events['A_R']
                     and 'B_R' not in events and final['A_tilt_deg'] > 45 and final['A_body_min_z'] > .68
                     and min(s['R_position'][2] for s in samples) < .4 and not initial_contacts)
    result = {'vx': vx, 'radio_mass': radio_mass, 'ball_mass': .145, 'target_z': target_z, 'hz': hz,
              'ball_enabled': enabled, 'B_initial': initial, 'B_velocity': velocity, 'events': events,
              'initial_penetrations_over_1mm': initial_contacts, 'worst_cached_contact': worst,
              'candidate_not_acceptance': candidate, 'final': final, 'samples': samples,
              'wall_s': time.time() - t0}
    p.disconnect(cid)
    return result


summary = {'status': 'LIMITED_FEASIBILITY_NOT_PHYSICS_PASS', 'ball_dims': ball_dims.tolist(),
           'ball_common': str(OUT / 'baseball_common_hull.npz'), 'radio_common_parts': len(radio_parts),
           'radio_centre': centre.tolist(), 'environment_static_count': len(statics),
           'radio_mass_assumption': '1.5/2.5kg estimates, mass concentrated in main body; not measured',
           'friction': 'radio .8, table .75 (pair .6 estimate), sensitivity pending', 'cases': []}
for index, (mass, vx) in enumerate([(mass, vx) for mass in [2.5, 1.5] for vx in [6., 7., 8.]]):
    result = run(vx, mass)
    with (OUT / ('case_%02d.json' % index)).open('x') as handle:
        json.dump(result, handle, indent=2)
    summary['cases'].append({k: v for k, v in result.items() if k != 'samples'})
    with (OUT / ('progress_%02d.json' % index)).open('x') as handle:
        json.dump(summary, handle, indent=2)
    print('CASE_DONE', index, json.dumps(summary['cases'][-1]), flush=True)
winners = [row for row in summary['cases'] if row['candidate_not_acceptance']]
if winners:
    best = winners[0]
    for label, hz, enabled in [('refined', 960, True), ('no_ball', 480, False)]:
        result = run(best['vx'], best['radio_mass'], hz=hz, enabled=enabled)
        with (OUT / (label + '.json')).open('x') as handle:
            json.dump(result, handle, indent=2)
        summary[label] = {k: v for k, v in result.items() if k != 'samples'}
with (OUT / 'summary.json').open('x') as handle:
    json.dump(summary, handle, indent=2)
print('BASEBALL_PROBE_COMPLETE', flush=True)
