"""V6.5 -- is the followed subject actually INSIDE the frame, on the frames that exist?

A DEFECT OF MY OWN THAT THIS EXISTS TO CATCH
--------------------------------------------
`camera_design_r9.py` reports "subject's LARGEST dimension below 50 px: 0 frames" and "UPRIGHT HEIGHT below 50 px: 0
frames", which reads like gate 4 passing. But it computes the subject's apparent size from the distance between the
camera and its DAMPED AIM, and it tests whether the subject is inside the cone around the ray to ITSELF:

    worst = max over bbox corners of angle(corner - cam, target - cam)   where target = subject position

The camera does not look at the subject. It looks at `look_xyz`, the damped aim, which deliberately LAGS the subject
and swings across the gap between subjects at every anchor switch. So "inside the cone around the ray to itself" is not
the same question as "inside the frame", and it is the same substitution of a convenient test for the real one that
produced the earlier ray-test mistakes.

This reads the projected subject positions -- computed independently, by exact projection through the authored camera
path -- and answers the question that actually decides readability:

  * how many frames put the subject OUTSIDE the 1280x720 frame, and which;
  * how far from the frame centre the subject sits, in pixels;
  * how large the subject appears at those positions.

A subject outside the frame is not readable no matter how many pixels it would have occupied had it been inside.
"""

import json
import sys

OUT = "/data/raw/huzijian/project1_database/outcomes/v65/radio_scurve_domino/v65_20261007_final"
path = OUT + "/subject_screen_motion.json"
try:
    d = json.load(open(path))
except FileNotFoundError:
    sys.exit(f"missing {path}; run check_subject_motion.py first")

W, H = 1280, 720
detail = d["detail"]
print(f"frames analysed: {len(detail)}   frame is {W}x{H}")
print(f"near-plane samples dropped: {d['dropped_near_plane']}")

inside, outside = [], []
for e in detail:
    if "x_px" not in e:
        continue
    x, y = e["x_px"], e["y_px"]
    (inside if (0 <= x <= W and 0 <= y <= H) else outside).append(e)

print(f"\nsubject INSIDE the frame: {len(inside)} frames")
print(f"subject OUTSIDE the frame: {len(outside)} frames")
for e in outside[:25]:
    print(f"    frame {e['frame']:4d} t={e['t']:6.3f}s  {e['subject']:>5}  at ({e['x_px']:.0f}, {e['y_px']:.0f})")

if inside:
    import math
    cx = [math.hypot(e["x_px"] - W / 2, e["y_px"] - H / 2) for e in inside]
    print(f"\ndistance of the subject from the frame centre: mean {sum(cx) / len(cx):.1f} px, "
          f"max {max(cx):.1f} px  (half-diagonal {math.hypot(W / 2, H / 2):.0f} px)")
    # how much of the frame the subject uses, at its actual on-screen position
    off = [e for e in inside if max(abs(e["x_px"] - W / 2), abs(e["y_px"] - H / 2)) > 0.4 * max(W, H)]
    print(f"frames with the subject beyond 40% of the half-frame from centre: {len(off)}")

steps = [(e["step_px"], e["frame"], e["t"], e["subject"]) for e in detail if e.get("step_px")]
steps.sort(reverse=True)
print(f"\nlargest per-frame subject movements on screen (same subject in both frames):")
for s, f, t, subj in steps[:12]:
    print(f"    frame {f:4d} t={t:6.3f}s  {subj:>5}  {s:7.2f} px")
if steps:
    vals = [s for s, _, _, _ in steps]
    print(f"  mean {sum(vals) / len(vals):.2f} px  median {sorted(vals)[len(vals) // 2]:.2f} px  max {max(vals):.2f} px")
    # 5% of frame width is a reasonable "does not smear" threshold for a 24 fps tracking shot
    bad = [s for s, _, _, _ in steps if s > 0.05 * W]
    print(f"  frames moving more than 5% of the frame width ({0.05 * W:.0f} px): {len(bad)}")

tail = [e for e in detail if 5.0 <= e["t"] <= 6.5]
if tail:
    tin = [e for e in tail if "x_px" in e and 0 <= e["x_px"] <= W and 0 <= e["y_px"] <= H]
    print(f"\nTAIL window t=5.0-6.5 s (the V6.5 payoff): {len(tail)} frames, {len(tin)} with the subject in frame")
    for e in tail:
        if "x_px" in e:
            ok = "in " if (0 <= e["x_px"] <= W and 0 <= e["y_px"] <= H) else "OUT"
            print(f"    frame {e['frame']:4d} t={e['t']:6.3f} {e['subject']:>5} {ok} ({e['x_px']:6.0f},{e['y_px']:6.0f})"
                  f"  step {e.get('step_px') if e.get('step_px') is not None else '-'}")

json.dump({"frames": len(detail), "inside": len(inside), "outside": len(outside),
           "outside_frames": [{"frame": e["frame"], "t": e["t"], "subject": e["subject"],
                               "x": e["x_px"], "y": e["y_px"]} for e in outside],
           "step_over_5pct_width": len([s for s, _, _, _ in steps if s > 0.05 * W]) if steps else 0},
          open(OUT + "/subject_in_frame.json", "w"), indent=2)
print(f"\nwrote {OUT}/subject_in_frame.json")
