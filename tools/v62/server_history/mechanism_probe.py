"""CPU exploratory table mechanism; NOT a certified common-geometry solution.

Uses the source table/chairs/floor triangle surfaces and radio connected-component
convex hulls. This approximation must be audited/canonicalized before acceptance.
No animation, anchors, invisible catchers, delayed impulses or forced release.
"""
from pathlib import Path
import itertools
import json
import math
import time
import numpy as np
import pybullet as p

ROOT = Path('/data/raw/huzijian/project1_database')
GEO = ROOT / 'log/V6.2_execution/geometry_audit'
OUT = ROOT / 'log/V6.2_execution/mechanism_probe'
OUT.mkdir(parents=True, exist_ok=False)
audit = json.loads((GEO / 'audit.json').read_text())
radio = np.load(GEO / 'boombox.002.npz')
verts = radio['vertices']
components = audit['objects']['boombox.002']['components']
body = verts[components[0]['indices']]
centre = (body.min(axis=0) + body.max(axis=0)) / 2
ball_path = ROOT / 'tmp/v62_shared_inputs/models/phyco_sim_objs/pool_table/white_ball.obj'
ball_verts = np.asarray([[float(x) for x in line.split()[1:4]]
                        for line in ball_path.read_text().splitlines() if line.startswith('v ')])
ball_verts -= (ball_verts.min(axis=0) + ball_verts.max(axis=0)) / 2
paper_path = ROOT / 'tmp/v62_shared_inputs/models/gso/Paper_Mario_Sticker_Star_Nintendo_3DS_Game/visual_geometry.obj'
paper = np.asarray([[float(x) for x in line.split()[1:4]]
                    for line in paper_path.read_text().splitlines() if line.startswith('v ')])
paper_dims = np.ptp(paper, axis=0)[[2, 0, 1]]
statics = [np.load(GEO / (n + '.npz')) for n in
           ['outdoor_table_chair_set_01_table.001', 'Floor_main',
            'outdoor_table_chair_set_01_chair_01.001', 'outdoor_table_chair_set_01_chair_02.001']]

def run(vx, ball_mass, radio_mass, hz=480, ball_enabled=True, rx=-2.38):
    client = p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81)
    p.setTimeStep(1/hz)
    p.setPhysicsEngineParameter(numSolverIterations=100, deterministicOverlappingPairs=1,
                               contactBreakingThreshold=.001)
    static_ids = []
    for surf in statics:
        shape = p.createCollisionShape(p.GEOM_MESH, vertices=surf['vertices'].tolist(),
                                       indices=surf['triangles'].ravel().tolist(), flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
        bid = p.createMultiBody(0, shape)
        p.changeDynamics(bid, -1, lateralFriction=.55, restitution=.03, collisionMargin=.0002)
        static_ids.append(bid)
    shapes = [p.createCollisionShape(p.GEOM_MESH, vertices=(verts[c['indices']] - centre).tolist())
              for c in components]
    count = len(shapes)-1
    a = p.createMultiBody(baseMass=radio_mass, baseCollisionShapeIndex=shapes[0], basePosition=centre.tolist(),
                         linkMasses=[0.0]*count, linkCollisionShapeIndices=shapes[1:],
                         linkVisualShapeIndices=[-1]*count, linkPositions=[[0,0,0]]*count,
                         linkOrientations=[[0,0,0,1]]*count, linkInertialFramePositions=[[0,0,0]]*count,
                         linkInertialFrameOrientations=[[0,0,0,1]]*count, linkParentIndices=[0]*count,
                         linkJointTypes=[p.JOINT_FIXED]*count, linkJointAxis=[[0,0,0]]*count)
    for link in range(-1, count):
        p.changeDynamics(a, link, lateralFriction=.5, restitution=.03, collisionMargin=.0002,
                         linearDamping=.02, angularDamping=.02)
    rs = p.createCollisionShape(p.GEOM_BOX, halfExtents=(paper_dims/2).tolist())
    r = p.createMultiBody(.07, rs, basePosition=[rx,11.27,.685922+paper_dims[2]/2+.0003])
    p.changeDynamics(r,-1,lateralFriction=.4,restitution=.03,collisionMargin=.0002)
    b = None
    if ball_enabled:
        bs = p.createCollisionShape(p.GEOM_MESH, vertices=ball_verts.tolist())
        b = p.createMultiBody(ball_mass, bs, basePosition=[-3.025,10.83,1.04])
        # Keep the same ballistic target near the back of the body as speed varies.
        flight = .285/vx
        vy = .40/flight
        vz = (.87-1.04+4.905*flight*flight)/flight
        p.resetBaseVelocity(b, [vx,vy,vz])
        p.changeDynamics(b,-1,lateralFriction=.3,restitution=.1,collisionMargin=.0002,
                         ccdSweptSphereRadius=float(np.ptp(ball_verts,axis=0).min()/2*.8), contactProcessingThreshold=0)
    events, samples, mindepth = {}, [], 0.
    for step in range(round(2.5*hz)):
        p.stepSimulation()
        t = (step+1)/hz
        for pair, label in [((a,r),'A_R'), ((b,a),'B_A'), ((b,r),'B_R')]:
            if pair[0] is None:
                continue
            if p.getContactPoints(*pair) and label not in events:
                events[label] = t
        for contact in p.getContactPoints():
            mindepth = min(mindepth, contact[8])
        if step % max(1,hz//60) == 0:
            ap, aq = p.getBasePositionAndOrientation(a)
            rp, rq = p.getBasePositionAndOrientation(r)
            bp = p.getBasePositionAndOrientation(b)[0] if b is not None else None
            rot = np.asarray(p.getMatrixFromQuaternion(aq)).reshape(3,3)
            body_world = (body-centre) @ rot.T + ap
            all_world = (verts-centre) @ rot.T + ap
            tilt = math.degrees(math.acos(float(np.clip(rot[2,2],-1,1))))
            samples.append({'t':t,'A_position':ap,'A_quaternion':aq,'A_tilt_deg':tilt,
                            'A_body_min_z':float(body_world[:,2].min()),
                            'A_all_min_z':float(all_world[:,2].min()),
                            'R_position':rp,'R_quaternion':rq,'B_position':bp})
    final = samples[-1]
    candidate = bool(ball_enabled and 'B_A' in events and 'A_R' in events and
                     events['B_A'] < events['A_R'] and 'B_R' not in events and
                     final['A_tilt_deg'] > 45 and final['A_body_min_z'] > .68 and
                     min(s['R_position'][2] for s in samples) < .4)
    result = {'vx':vx,'ball_mass_kg':ball_mass,'radio_mass_kg':radio_mass,'hz':hz,
              'ball_enabled':ball_enabled,'receiver_x':rx,'events':events,
              'max_radio_tilt_deg':max(s['A_tilt_deg'] for s in samples),
              'min_R_z':min(s['R_position'][2] for s in samples),
              'solver_min_contact_distance_m':mindepth,'candidate_not_acceptance':candidate,
              'final':final,'samples':samples}
    p.disconnect(client)
    return result

summary = {'status':'EXPLORATORY_NOT_A_GEOMETRY_OR_PHYSICS_PASS',
           'radio_collision':'connected-component convex hull approximation, fixed rigid links; no whole-radio hull',
           'radio_mass_note':'1.5 or 2.5 kg hypothesis; not measured; mass concentrated in body',
           'receiver':'70 g box using measured source extents; surface bake pending',
           'environment_scope':'source table, two chairs, Floor_main only; full obstacle gate pending',
           'ball_dims_m':np.ptp(ball_verts,axis=0).tolist(), 'cases':[]}
cases = [(vx,bm,am) for vx,bm,am in itertools.product([2.5,3.5,4.5],[.17],[1.5,2.5])]
for index, params in enumerate(cases):
    result = run(*params)
    (OUT / ('case_%02d.json'%index)).write_text(json.dumps(result,indent=2))
    summary['cases'].append({k:v for k,v in result.items() if k != 'samples'})
    print(json.dumps(summary['cases'][-1]),flush=True)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
winners = [c for c in summary['cases'] if c['candidate_not_acceptance']]
if winners:
    best = winners[0]
    for label, hz, enabled in [('refined',960,True),('no_ball',480,False)]:
        result = run(best['vx'],best['ball_mass_kg'],best['radio_mass_kg'],hz,enabled)
        (OUT/(label+'.json')).write_text(json.dumps(result,indent=2))
        summary[label] = {k:v for k,v in result.items() if k != 'samples'}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print('MECHANISM_PROBE_COMPLETE',flush=True)
