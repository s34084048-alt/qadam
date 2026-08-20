"""ONNX Runtime backend -- the slot a trained model drops into.

Nothing outside this file changes when a real model arrives: the API contract,
the database schema and the UI all consume `ModuleResult`. To activate, add a
row to `model_registry` with backend='onnx', an `artifact_uri`, and active=true
for the module, then implement `_postprocess` for that model's output heads.

The safety boundary is enforced here too: a trained model may only populate
surface findings and a triage grade. `next_investigation` continues to come
from the routing config, never from the model.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .. import localization, prerequisites
from ..modules_config import routing_for
from ..types import Grade, Lesion, ModuleResult, QualityReport, Triage


class OnnxBackendUnavailable(RuntimeError):
    pass


class OnnxBackend:
    name = "onnx"
    version = "0.0.0"
    backend_id = "onnx"

    def __init__(self, artifact_path: str, module: str, version: str = "0.0.0") -> None:
        try:
            import onnxruntime  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise OnnxBackendUnavailable(
                "onnxruntime is not installed. Install requirements-onnx.txt to "
                "enable the ONNX backend, or set the module's active "
                "model_registry row back to backend='classical_cv'."
            ) from exc
        import onnxruntime as ort

        self.module = module
        self.version = version
        self.artifact_path = artifact_path
        self._session = ort.InferenceSession(
            artifact_path, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name
        self._input_shape = self._session.get_inputs()[0].shape

    def supports(self, module: str) -> bool:
        return module == self.module

    # -- inference ----------------------------------------------------------

    def _preprocess(self, image_bgr: np.ndarray) -> np.ndarray:
        import cv2

        h = self._input_shape[2] if isinstance(self._input_shape[2], int) else 384
        w = self._input_shape[3] if isinstance(self._input_shape[3], int) else 384
        img = cv2.resize(image_bgr, (w, h), interpolation=cv2.INTER_AREA)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        return np.transpose(img, (2, 0, 1))[None, ...].astype(np.float32)

    def _postprocess(
        self, outputs: list[np.ndarray], image_bgr: np.ndarray, quality: QualityReport
    ) -> tuple[list[Lesion], Grade, float, list[str]]:
        """Model-specific. Implement per trained model.

        Must return SURFACE lesions plus a triage grade only. It must not
        return, and the platform will not accept, an internal diagnosis.
        """
        raise NotImplementedError(
            "Implement _postprocess for this model's output heads before "
            "activating the ONNX backend for this module."
        )

    def analyze(
        self,
        image_bgr: np.ndarray,
        module: str,
        quality: QualityReport,
        calibration: Any | None = None,
    ) -> ModuleResult:
        tensor = self._preprocess(image_bgr)
        outputs = self._session.run(None, {self._input_name: tensor})
        lesions, grade, confidence, rationale = self._postprocess(
            outputs, image_bgr, quality
        )
        # Confidence is always discounted by measured image quality, whatever
        # the model reports.
        confidence = float(np.clip(confidence * quality.confidence_factor, 0.05, 0.95))

        # The size-reference prerequisites are a property of the CAPTURE, not
        # of whichever model read it: a frame with no usable card cannot yield
        # cm2 or a between-visit comparison whatever produced the grade. So
        # they are applied here too, and itemised identically.
        #
        # The segmentation prerequisites are deliberately NOT asserted for this
        # backend. They are read off the classical widen/localisation steps,
        # and this backend does not run them; inventing an equivalent from a
        # model whose output heads are not yet defined would be fabricating a
        # check that never happened.
        confidence, adjustments = prerequisites.apply(
            confidence,
            prerequisites.evaluate(
                background_warning=None,
                subject_mask_was_degenerate=False,
                wound_classification=None,
                no_wound_region_marker=localization.NONE,
                calibration=calibration,
            ),
        )
        spec = routing_for(module, str(grade))
        triage = Triage(
            grade=grade,
            label=spec["label"],
            confidence=confidence,
            confidence_adjustments=adjustments,
            rationale=rationale,
            next_investigation=spec["next_investigation"],
            urgency=spec["urgency"],
            routing_target=spec["routing_target"],
        )
        return ModuleResult(
            lesions=lesions,
            triage=triage,
            features={"backend": "onnx", "artifact": self.artifact_path},
            model_version=f"{self.name}-{self.version}",
            backend=self.backend_id,
        )
