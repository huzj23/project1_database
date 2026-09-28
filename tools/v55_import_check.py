import sys
sys.path.insert(0, "src")
from physim import contracts, safe_output
from physim.render.blender_backend import purge_stale_frames
from physim.physics import SimulationResult, BodyState
import inspect

print("all imports OK")
print("contract schema :", contracts.SCHEMA_VERSION)
print("output schema   :", contracts.OUTPUT_SCHEMA_VERSION)
print("purge signature :", inspect.signature(purge_stale_frames))
print("legacy result   :", SimulationResult.__name__, "support_trajectory default =",
      SimulationResult.__dataclass_fields__["support_trajectory"].default)
