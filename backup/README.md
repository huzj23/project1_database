# backup/

Local, git-tracked copies of small evidence files that `outcomes/` cannot hold, because `.gitignore`
excludes the whole `outcomes/` tree (it is large and mostly regenerable).

Only files that are (a) small, (b) not regenerable without re-running a solve, and (c) cited by a
stage report belong here. Large binary outputs -- rendered frames, videos, `.blend` replays, runtime
copies -- stay in `outcomes/` and are additionally copied to the local backup location recorded in
each stage report; they are deliberately not committed.

`backup/v55_stage08/` holds the stage-08 box selection measurements, which are small JSON derived
from the 140-asset GSO library on the server and which the stage-08 plan revision depends on.
