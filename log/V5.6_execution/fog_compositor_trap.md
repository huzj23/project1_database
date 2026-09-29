# V5.6: the Hidden Alley fog compositor blowup, and why it must be disabled before any render

Discovered (again) 2026-09-29 ~15:35 (+08:00), during the first attempt at the §8.2 render-cost
measurement. Cost: about 50 minutes of wall time and most of the machine's memory, with **zero
frames produced**.

## 1. What happened

`tools/v56/measure_cost.py` was launched at 14:42 to measure the per-frame cost of the Hidden Alley
scene, which §8.2 requires before the delivery tier can be fixed. At 15:34, 52 minutes later, it had
written **no frames at all** — the output directory contained only the empty tier directory. The
process showed:

| measurement | value |
| --- | --- |
| private memory | **25,793 MB** |
| peak pagefile usage | **26,469 MB** |
| physical RAM | 15.69 GB total, **0.45 GB free** |
| CPU consumed over 52 min | ~3600 s (about 1.15 s/s, i.e. roughly one core) |
| wall-clock progress | none |

Under one core of CPU with that much memory pressure is the signature of **paging, not computing**.
The process was alive and busily faulting pages in and out, and would have taken an unbounded time to
produce anything.

## 2. The cause, and the fact that this was already known

The Hidden Alley source scene's compositor **renders a second volumetric Fog scene**. This was
already discovered and recorded on 2026-09-28 in
`tools/v5_audit_render_hidden_alley_local.ps1`:

> ```powershell
> # The source compositor renders a second volumetric Fog scene and exceeded
> # 25 GiB private memory without producing a file.  For asset review, keep
> # the authored scene/camera/lights/materials but disable only compositing.
> --samples 16 --disable-compositing --workspace $workspace
> ```

and the reference implementation sets it with one line:

```python
if args.disable_compositing:
    scene.render.use_compositing = False
```

My `measure_cost.py` — and `tools/v56/render.py` — were both **missing that line**. The 25,793 MB
figure matches the earlier "25 GiB" record almost exactly, so this is the same phenomenon, not a new
one.

**This is a real defect I introduced, not an environment problem.** The prior work had already paid
for this lesson and written it down, and my new script did not read it. It is recorded here on the
same terms as the deletion incidents: the first occurrence is the cheap one, and the point of writing
it down is that the second occurrence is expensive.

## 3. Why it would have been much worse if it had gone unnoticed

The cost measurement was the **least** dangerous place for this to appear:

- `render.py` is the script that renders both delivered videos. With compositing enabled, every
  attempt to render video A would have thrashed the machine for an hour and produced nothing, and —
  worse — a partially successful run could have written frames whose **fog compositing differs from
  the accepted asset-review render**, silently breaking §4's requirement that the fog compositor stay
  off and that the 7 author lights, World and materials be preserved.
- The failure mode is not a crash. It is a process that stays alive, consumes the whole machine, and
  reports nothing. Without checking memory and CPU directly it looks like a slow render rather than a
  broken one.

## 4. The fix, applied to both scripts

`scene.render.use_compositing = False`, set immediately after the render engine and before any
sampling configuration, in both `tools/v56/measure_cost.py` and `tools/v56/render.py`, each with a
comment recording the measured blowup and the fact that it reproduces a known finding. What this does
**not** touch:

- geometry — no object, mesh, or modifier is altered;
- lighting — all 7 author lights are preserved;
- the World (`flower_hillside`) and all 125 materials;
- the camera.

Only the compositing step is skipped. This is exactly the state the accepted baseline image
`outcomes/v5_asset_review/scenes/hidden_alley.png` was rendered in, so the two are comparable, and it
is the state §4 requires.

The cost measurement was re-run from scratch after the fix. The failed run's directory was **moved**,
not deleted, to `remove/v56_cost_thrash_compositor_20260929T075050Z/` — and that move is itself worth
noting: the archiver refused to report success, printing

> `FAILURE: outcomes\v56\cost contained no files, so nothing was archived and nothing was moved. An
> archive that moves nothing must not report success.`

because the directory was empty. That is the fix from `deletion_incident_05.md` working as intended:
the tool that once reported vacuous success on an empty source now refuses to.

## 5. The general lesson, stated so it is reusable

The scene carries a **latent, non-obvious, expensive** configuration: a compositor that renders a
second volumetric scene. Any new script that renders this scene must disable it, and the only reason
it is safe to have three separate scripts each doing so independently is that the requirement is
written down in all three. A shared render-setup helper would remove the class of error; until then,
the requirement is duplicated deliberately and each copy cites the measurement.
