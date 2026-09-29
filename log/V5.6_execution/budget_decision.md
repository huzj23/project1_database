# V5.6 §8 render budget: measured on Hidden Alley, and the tier decision

Measured 2026-09-29 16:20–17:00 (+08:00). §8.2 requires the cost of each scene to be measured at its
final object and material state before the delivery tier is fixed, and explicitly forbids
extrapolating from Italian Flat's 702 s/frame. This is that measurement.

## 1. Measured per-frame cost, uncontended

Tool: `tools/v56/measure_cost.py`. CPU only, 8 threads (FIXED), `use_persistent_data = True`,
compositing disabled, adaptive sampling, OpenImageDenoise, all tiers measured **inside one Blender
session** so the one-time texture decode and BVH build are attributed to the first frame rather than
smeared across tiers. Machine: 16 logical CPUs, 15.7 GB RAM. Scene opens in 4.7 s.

| tier | first frame | marginal per frame |
| --- | --- | --- |
| 960×540 / 16 spp | 197.19 s | **120.11 s** |
| 1280×720 / 16 spp | 236.04 s | **197.94 s** |
| 1280×720 / 16 spp, 3 bounces | 312.67 s | **178.63 s** |
| 1280×720 / 10 spp | 148.57 s | **126.46 s** |

Two earlier attempts at this measurement are **not** used and are archived: the first thrashed the
pagefile for 52 minutes and produced nothing (see `fog_compositor_trap.md`), and the second was
contended by a concurrent Blender process. Reporting a contended number would have made the whole
budget wrong, so it was re-measured on an idle machine. Raw evidence:
`outcomes/v56/cost_clean/`, `outcomes/v56/cost_levers/`.

## 2. Budget arithmetic (§8.2 formula)

```text
total = 1.25 x (A_frames x A_sec + B_frames x B_sec) + 2 h of encoding/transfer/checking
```

At 216 frames (A ≈ 96, B ≈ 120) and 20.9 h remaining:

| tier | projected total | fits? | headroom |
| --- | --- | --- | --- |
| 960×540 / 16 spp | 11.01 h | yes | +9.9 h |
| **1280×720 / 16 spp** | **16.85 h** | **yes** | **+4.07 h** |
| 1280×720 / 10 spp | 11.48 h | yes | +9.4 h |

## 3. Decision

**Deliver both videos at 1280×720 / 16 spp, 8 threads, CPU only, fixed denoise.**

Reasoning, in the order §8.1 gives:

1. §8.1's table makes 960×540/8–16 spp a **diagnostic tier that may NOT be delivered as a final
   video**, and names 1280×720/16–24 spp as the deliverable floor. So 540p is not available as the
   answer regardless of how comfortable its budget is.
2. 1280×720/16 fits with +4.07 h of headroom. It is the **highest tier that fits**, which is what
   §8.1 asks for ("优先选通过画质及预算的最高档").
3. 10 spp is below §8.1's stated floor for the deliverable tier, so it is held as a **fallback**
   only, to be used if and only if the clock runs short — not chosen now.

## 4. The risk this leaves, stated plainly

**+4.07 h of headroom is less than the cost of re-rendering one video.** At 197.94 s/frame, a full
re-render of B's 120 frames alone needs **6.60 h**, and A's 96 frames need 5.28 h. The headroom covers
only about 74 extra frames. Therefore:

- **the first full render must be correct**, which makes the §7.1 five-key-image check mandatory
  rather than optional: 5 images × 2 videos × ~200 s ≈ 0.6 h, which is affordable, and it is the only
  affordable way to catch a framing or contact error before committing 11.9 h of rendering;
- a mid-render failure cannot be absorbed by re-rendering from scratch, so the renderer is written to
  be **resumable**: it refuses to overwrite an existing frame and exits if frames are present, and
  every frame is its own file with its own timing record, so an interruption loses only the frames
  not yet written;
- if the physics is not finished in time to start the full render by roughly **02:00**, the fallback
  ladder in §8.2 applies in order — and it does not include dropping frames, changing the replay
  timeline, or reducing model/collision correctness.

## 5. What was NOT done, and why it is not needed

§8.2 permits skipping a full 32/64/128 sweep when existing evidence suffices. §8.1 removes the
1920×1080/64 tier from this round entirely ("本轮没有两段完整结果前不运行"), so only the two tiers
that could plausibly be delivered were measured, plus the two cost levers (bounce depth, sample
count) needed to judge the fallback. Measuring 1080p/64 would have cost hours and could not have
changed the decision.
