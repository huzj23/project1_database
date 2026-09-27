"""Rendering interfaces and Blender/Kubric adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RenderResult:
    rgb: np.ndarray
    depth: np.ndarray
    segmentation: np.ndarray
    diagnostics: dict[str, Any]
