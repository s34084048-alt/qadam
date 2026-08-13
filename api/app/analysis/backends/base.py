from __future__ import annotations

from typing import Protocol, runtime_checkable

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
        self, image_bgr: np.ndarray, module: str, quality: QualityReport
    ) -> ModuleResult: ...
