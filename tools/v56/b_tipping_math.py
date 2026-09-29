"""Analytic tipping energetics for the three candidates, used to choose a defensible push.

A box of thickness t and height h tips about its front bottom edge. The centre of mass must rise
from h/2 to L/2 where L = hypot(t, h), so the trigger must supply at least

    dPE = m g (L - h) / 2

A pure rotation about the edge at angular speed w gives KE = (1/2) I w^2 with I = m L^2 / 3, so
the minimum angular speed that just reaches the tipping point is

    w_crit = sqrt( 3 g (L - h) / L^2 )

independent of mass. This sets the scale for the trigger speed and shows the push is mass-invariant,
which is why the toppling dynamics should not depend on the assumed density.
"""

from __future__ import annotations

import math

G = 9.81

BOXES = {
    "Hasbro_Cranium_Performance_and_Acting_Game": (0.055838, 0.272574),
    "Hasbro_Trivial_Pursuit_Family_Edition_Game": (0.073462, 0.272852),
    "Supernatural_Ouija_Board_Game": (0.062497, 0.408406),
}

print(f"{'asset':44s} {'t_m':>9s} {'h_m':>9s} {'h/t':>6s} {'tip_deg':>8s} "
      f"{'w_crit_rad_s':>13s} {'rise_mm':>8s} {'w0=0.30/w_crit':>15s}")
for name, (t, h) in BOXES.items():
    L = math.hypot(t, h)
    tip = math.degrees(math.atan2(t, h))
    rise = (L - h) / 2.0
    w_crit = math.sqrt(3.0 * G * (L - h) / (L * L))
    print(f"{name:44s} {t:9.6f} {h:9.6f} {h/t:6.3f} {tip:8.4f} {w_crit:13.4f} "
          f"{rise*1000:8.4f} {0.30/w_crit:15.3f}")

W0_PRIMARY = 3.0
W0_SWEEP = (1.0, 2.0, 3.0, 4.5)

print(f"\nNote the first candidate for the trigger: w0 = {W0_PRIMARY} rad/s gives these multiples of")
print("the critical speed. A trigger BELOW w_crit cannot topple the striker at all, so a run at such")
print("a speed would say nothing about whether A can knock B over; the primary trigger is therefore")
print("chosen comfortably ABOVE every w_crit, and the sweep brackets the critical values so the")
print("transition is visible rather than assumed.")
for name, (t, h) in BOXES.items():
    L = math.hypot(t, h)
    w_crit = math.sqrt(3.0 * G * (L - h) / (L * L))
    edge_speed = W0_PRIMARY * L / 2.0
    print(f"  {name:44s} w_crit {w_crit:6.3f}  w0/w_crit {W0_PRIMARY/w_crit:5.2f}x  "
          f"edge speed {edge_speed:.3f} m/s")

print(f"\nsweep: w0 in {W0_SWEEP} rad/s")
for name, (t, h) in BOXES.items():
    L = math.hypot(t, h)
    w_crit = math.sqrt(3.0 * G * (L - h) / (L * L))
    verdicts = " ".join(f"{w}({'above' if w > w_crit else 'BELOW'})" for w in W0_SWEEP)
    print(f"  {name:44s} w_crit {w_crit:6.3f} -> {verdicts}")
