from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

from ..types import ModuleResult, QualityReport


@runtime_checkable
class ModelBackend(Protocol):
    """The one seam a trained model has to fit through.

    A new backend implements `analyze` and declares its `name`/`version`.
    Nothing in the API contract, the database schema or the UI changes when the
    active backend for a module changes -- see model_registry.
    """

    name: str
    version: str

    def supports(self, module: str) -> bool: ...

    def analyze(
        self,
        image_bgr: np.ndarray,
        module: str,
        quality: QualityReport,
        calibration: Any | None = None,
    ) -> ModuleResult: ...
    """`calibration` is the pipeline's Calibration for THIS image: whether a
    reference card was found, whether it was usable, and the scale derived
    from it. It reaches the backend because evidence strength is coupled to
    those prerequisites (see analysis.prerequisites) -- a score computed
    without knowing whether the frame could be measured at all cannot go down
    when it could not be.

    Optional, and defaulted, so a backend that does not use it -- and the
    existing three-argument call sites -- stay valid."""
