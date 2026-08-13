"""Pure, synchronous analysis pipeline: bytes in, findings out.

Deliberately free of database, storage, HTTP and auth concerns so the exact
same function can run inline in the request (today) or inside a Celery/RQ
worker (tomorrow) with no change to the API contract. See runner.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import calibration, clinical, cv_utils
from .backends import get_backend
from .overlay import render_overlay
from .quality import run_quality_gate
from .types import ModuleResult, QualityReport, SubjectMismatch


class UnreadableImage(ValueError):
    pass


@dataclass(slots=True)
class AnalysisJob:
    image_bytes: bytes
    module: str
    backend_id: str = "classical_cv"
    artifact_uri: str | None = None
    model_version: str = "0.0.0"
    render_overlay: bool = True


@dataclass(slots=True)
class AnalysisOutput:
    quality: QualityReport
    width: int
    height: int
    result: ModuleResult | None = None
    overlay_png: bytes | None = None
    fallback_reason: str | None = None
    notes: list[str] = field(default_factory=list)
    subject_error: SubjectMismatch | None = None
    calibration: dict | None = None

    @property
    def quality_rejected(self) -> bool:
        return self.result is None


def execute(job: AnalysisJob) -> AnalysisOutput:
    """Quality gate, then module analysis, then overlay. CPU-bound."""
    image = cv_utils.decode_image(job.image_bytes)
    if image is None:
        raise UnreadableImage(
            "The uploaded file could not be decoded as an image."
        )

    h, w = image.shape[:2]
    quality = run_quality_gate(image)

    # A failing image is never analysed. Analysing a photo we know is unusable
    # would produce a confident-looking result from nothing.
    if not quality.passed:
        return AnalysisOutput(quality=quality, width=w, height=h)

    # Colour calibration sits AFTER the quality gate and BEFORE any module
    # measurement. The quality checks (focus, exposure, framing) describe the
    # capture as it was actually taken, so correcting colour first would report
    # an exposure the camera never produced. Everything downstream measures
    # colour, so it all runs on the corrected frame.
    image, calibrated_mask, cal = calibration.calibrate(image, quality.mask)
    quality.mask = calibrated_mask

    fallback_reason = None
    try:
        backend = get_backend(
            job.module, job.backend_id, job.artifact_uri, job.model_version
        )
    except Exception as exc:  # model artifact missing / runtime unavailable
        fallback_reason = (
            f"Configured '{job.backend_id}' backend unavailable ({exc}); "
            "fell back to the classical-CV placeholder."
        )
        backend = get_backend(job.module, "classical_cv")

    try:
        result = backend.analyze(image, job.module, quality)
    except SubjectMismatch as mismatch:
        # Not a quality problem -- the picture may be perfectly sharp. It is
        # simply not a picture of what this module assesses.
        return AnalysisOutput(quality=quality, width=w, height=h,
                              subject_error=mismatch,
                              calibration=cal.to_json())

    # Attached here rather than inside a backend: the clinical layer is a
    # property of the module, not of whichever model produced the grade, so a
    # trained model inherits it unchanged.
    context = clinical.build(job.module, result.triage.grade, result.features,
                             result.lesions)
    result.clinical = context.to_json() if context else None

    overlay_png = None
    if job.render_overlay:
        annotated = render_overlay(
            image, result.lesions, result.triage, quality, job.module
        )
        overlay_png = cv_utils.encode_png(annotated)

    notes: list[str] = []
    if fallback_reason:
        notes.append(fallback_reason)
        result.triage.rationale.append(fallback_reason)

    # Recorded in the rationale, not just in a side channel: whether the colours
    # this grade was derived from were corrected is part of how the grade was
    # reached, and a later reader needs to see it without digging.
    result.features["colour_calibration"] = cal.to_json()
    if cal.applied:
        result.triage.rationale.append(
            "Colours were corrected using a neutral reference card in the "
            f"frame (illuminant shift {cal.illuminant_shift * 100:.0f}%), so "
            "they are comparable with other calibrated images of this patient."
        )
    elif cal.detected and cal.reason:
        result.triage.rationale.append(
            f"A reference card was seen but not used: {cal.reason}"
        )

    return AnalysisOutput(
        quality=quality,
        width=w,
        height=h,
        result=result,
        overlay_png=overlay_png,
        fallback_reason=fallback_reason,
        notes=notes,
        calibration=cal.to_json(),
    )
