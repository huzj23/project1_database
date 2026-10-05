"""Limited local relay diagnostics, not a solved/accepted production trajectory.

Only the first block receives initial velocities corresponding to 5 rad/s
rotation about its front lower edge; no later impulses/kinematics.
This tests local geometry/propagation, not actual table-supplied energy.
"""
from pathlib import Path
import json
import math
import time
import numpy as np
import pybullet as p
from scipy.spatial.transform import Rotation

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node11/relay_probe_r2'
OUT.mkdir(parents=True, exist_ok=False)
layout = json.loads((ROOT / 'tmp/v63_node11/layout_r6/layout.json').read_text())
assets = json.loads(Path(layout['common_manifest']).read_text())['assets']
survey_dir = ROOT / 'tmp/v63_node11/survey_r1'
survey = json.loads((survey_dir / 'survey.json').read_text())
p.connect(p.DIRECT)
p.setGravity(0, 0, -9.81)
p.setPhysicsEngineParameter(numSolverIterations=120, deterministicOverlappingPairs=1,
                           contactBreakingThreshold=.0005)
names = {}
for row in survey['objects']:
    blob = np.load(survey_dir / row['file'])
    verts, tri = blob['vertices'], blob['triangles']
    for start in range(0, len(tri), 3000):
        used, inverse = np.unique(tri[start:start + 3000], return_inverse=True)
        shape = p.createCollisionShape(p.GEOM_MESH, vertices=verts[used].tolist(),
                                       indices=inverse.tolist(), flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
        body = p.createMultiBody(0, shape)
        p.changeDynamics(body, -1, lateralFriction=.65, restitution=.03, collisionMargin=.0001)
        names[body] = row['name']
shapes = {}
for key, asset in assets.items():
    if key not in ('baseball', 'radio', 'tape'):
        shapes[key] = [p.createCollisionShape(p.GEOM_BOX, halfExtents=(np.array(asset['dims']) / 2).tolist())]
shapes['tape'] = [p.createCollisionShape(p.GEOM_MESH, vertices=np.load(part['mesh_file'])['vertices'].tolist())
                  for part in assets['tape']['parts']]


def actor(row):
    key = row['asset_key']
    shape = shapes[key]
    mass = assets[key]['mass_estimate_kg']
    n = len(shape) - 1
    bid = p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=shape[0],
                            basePosition=row['settled_position'], baseOrientation=row['settled_quaternion_xyzw'],
                            linkMasses=[0.] * n, linkCollisionShapeIndices=shape[1:],
                            linkVisualShapeIndices=[-1] * n, linkPositions=[[0, 0, 0]] * n,
                            linkOrientations=[[0, 0, 0, 1]] * n, linkInertialFramePositions=[[0, 0, 0]] * n,
                            linkInertialFrameOrientations=[[0, 0, 0, 1]] * n,
                            linkParentIndices=[0] * n, linkJointTypes=[p.JOINT_FIXED] * n,
                            linkJointAxis=[[0, 0, 0]] * n)
    if key == 'tape':
        r2 = assets[key]['outer_radius'] ** 2 + assets[key]['inner_radius'] ** 2
        w = assets[key]['width']
        p.changeDynamics(bid, -1, localInertiaDiagonal=[mass * (3 * r2 + w*w) / 12,
                                                       mass * r2 / 2, mass * (3 * r2 + w*w) / 12])
    for link in range(-1, n):
        p.changeDynamics(bid, link, lateralFriction=.45, restitution=.02, collisionMargin=.0001,
                         linearDamping=.015, angularDamping=.015, rollingFriction=.0002)
    names[bid] = row['id']
    return bid


windows = [(1, 6), (6, 10), (10, 15), (14, 19), (19, 25), (24, 29), (29, 35), (36, 42), (42, 48)]
results = []
for hz in [960, 1920]:
    p.setTimeStep(1 / hz)
    for first, last in windows:
        t0 = time.time()
        selected = layout['objects'][first - 1:last]
        bids = [actor(row) for row in selected]
        firstrow = selected[0]
        initial = Rotation.from_quat(firstrow['settled_quaternion_xyzw']).as_matrix()
        d = np.array(firstrow['dims'])
        edge = np.array([d[0] / 2, 0., -d[2] / 2])
        pivot = np.array(firstrow['settled_position']) + initial @ edge
        # Diagnostic only: release the first block with a measured-state-like
        # initial rotation rate around its lower front edge. Unlike a 15-degree
        # teleported lean this starts at the collision-tested upright pose.
        # This does NOT prove the upstream/table can supply the chosen energy.
        omega = initial @ np.array([0., 5., 0.])
        velocity = np.cross(omega, -initial @ edge)
        p.resetBaseVelocity(bids[0], velocity.tolist(), omega.tolist())
        peaks = {row['id']: 0. for row in selected}
        translations = {row['id']: 0. for row in selected}
        contacts = {}
        for step in range(int(2.5 * hz)):
            p.stepSimulation()
            if step % 8 == 0:
                for bid, row in zip(bids, selected):
                    pos, quat = p.getBasePositionAndOrientation(bid)
                    current = Rotation.from_quat(quat).as_matrix()
                    prior = Rotation.from_quat(row['settled_quaternion_xyzw']).as_matrix()
                    tilt = math.degrees(math.acos(float(np.clip(current[:, 2] @ prior[:, 2], -1, 1))))
                    peaks[row['id']] = max(peaks[row['id']], tilt)
                    translations[row['id']] = max(translations[row['id']],
                                                  float(np.linalg.norm(np.array(pos) - row['settled_position'])))
                    for cp in p.getContactPoints(bodyA=bid):
                        other = names[cp[2]]
                        if other.startswith('F') and other != 'Floor_main':
                            pair = '--'.join(sorted([row['id'], other]))
                            if pair not in contacts:
                                contacts[pair] = step / hz
        responded = {row['id']: (translations[row['id']] > .04 if row['asset_key'] == 'tape'
                                 else peaks[row['id']] > 45) for row in selected}
        result = {'window': [first, last], 'hz': hz, 'input': 'first block initial edge rotation 5 rad/s; diagnostic only',
                  'initial_linear_velocity': velocity.tolist(), 'initial_angular_velocity': omega.tolist(),
                  'all_responded': all(responded.values()), 'responded': responded,
                  'peak_tilt_deg': peaks, 'max_translation_m': translations, 'first_pair_contacts': contacts,
                  'runtime_s': time.time() - t0, 'full_chain_acceptance': False}
        results.append(result)
        with (OUT / ('window_%02d_%02d_%d.json' % (first, last, hz))).open('x') as handle:
            json.dump(result, handle, indent=2)
        print('RELAY', first, last, hz, result['all_responded'], responded, flush=True)
        for bid in bids:
            # Removing transient physics objects is not a filesystem deletion.
            p.removeBody(bid)
with (OUT / 'summary.json').open('x') as handle:
    json.dump({'status': 'LOCAL_DIAGNOSTIC_ONLY', 'results': results}, handle, indent=2)
p.disconnect()
