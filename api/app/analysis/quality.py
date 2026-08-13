"""Shared image-quality gate. Runs before any module analysis.

A failing image is rejected with re-capture guidance rather than analysed
badly. A partially-passing image discounts the confidence of whatever the
module reports.
"""

from __future__ import annotations

import numpy as np

from ..config import settings
from . import cv_utils
from .types import QualityCheck, QualityReport


def run_quality_gate(bgr: np.ndarray) -> QualityReport:
    h, w = bgr.shape[:2]
    mask, fraction = cv_utils.estimate_subject_mask(bgr)
    focus = cv_utils.focus_variance(bgr, mask)
    exposure = cv_utils.exposure_mean(bgr, mask)
    short_side = min(h, w)

    checks = [
        QualityCheck(
            name="resolution",
            passed=short_side >= settings.quality_min_short_side,
            value=float(short_side),
            threshold=float(settings.quality_min_short_side),
            hint=(
                "Image is too small. Move closer and capture at a higher "
                f"resolution — the shorter side must be at least "
                f"{settings.quality_min_short_side} px."
            ),
        ),
        QualityCheck(
            name="focus",
            passed=focus >= settings.quality_min_focus_var,
            value=focus,
            threshold=float(settings.quality_min_focus_var),
            hint=(
                "The subject is out of focus. Hold the camera steady about "
                "20–30 cm away, tap to focus on the area of interest, and "
                "re-capture."
            ),
        ),
        QualityCheck(
            name="exposure",
            passed=(
                settings.quality_exposure_min <= exposure <= settings.quality_exposure_max
            ),
            value=exposure,
            threshold=float(settings.quality_exposure_min),
            hint=(
                "Lighting is too dark. Use even, indirect light on the subject "
                "and avoid shadows."
                if exposure < settings.quality_exposure_min
                else
                "The image is over-exposed or has glare. Move away from direct "
                "light or flash and re-capture."
            ),
        ),
        QualityCheck(
            name="subject_present",
            passed=fraction >= settings.quality_min_subject_fraction,
            value=fraction,
            threshold=float(settings.quality_min_subject_fraction),
            hint=(
                "The area of interest fills too little of the frame. Fill "
                "roughly half the frame with the area being assessed, on a "
                "plain background."
            ),
        ),
    ]

    passed = all(c.passed for c in checks)

    # Confidence is discounted as measurements approach their thresholds, and
    # heavily when a check fails outright.
    factor = 1.0
    for c in checks:
        if not c.passed:
            factor *= 0.55
    if focus < settings.quality_min_focus_var * 2:
        factor *= 0.9
    if fraction < settings.quality_min_subject_fraction * 2:
        factor *= 0.9
    factor = float(np.clip(factor, 0.2, 1.0))

    return QualityReport(
        passed=passed,
        checks=checks,
        width=w,
        height=h,
        subject_fraction=fraction,
        focus_var=focus,
        exposure_mean=exposure,
        confidence_factor=factor,
        mask=mask,
    )
