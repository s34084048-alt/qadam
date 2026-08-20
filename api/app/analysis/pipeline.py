"""Pure, synchronous analysis pipeline: bytes in, findings out.

Deliberately free of database, storage, HTTP and auth concerns so the exact
same function can run inline in the request (today) or inside a Celery/RQ
worker (tomorrow) with no change to the API contract. See runner.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import calibration, clarify, clinical, cv_utils, input_gate
from .backends import get_backend
from .input_gate import InputRejection
from .overlay import render_overlay
from .quality import run_quality_gate
from .modules_config import routing_for
from .types import (Grade, ModuleResult, QualityReport,
                    SubjectMismatch)


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
    # Set when the pre-analysis input gate refused the frame. When this is set
    # there is no result, no overlay and no grade -- by construction, because
    # `execute` returns before a backend is ever reached.
    input_rejection: InputRejection | None = None

    @property
    def input_rejected(self) -> bool:
        return self.input_rejection is not None

    @property
    def quality_rejected(self) -> bool:
        """A quality-gate refusal specifically.

        An input-gate rejection also leaves `result` as None, and a caller that
        reported it as a quality failure would tell the user to re-take a photo
        that can never pass -- a stock image does not become a capture by being
        photographed again.
        """
        return self.result is None and self.input_rejection is None


# Which measured percentages describe an AREA on the subject, and so can be
# converted to cm² once a size reference exists.
_AREA_FEATURES = ("dark_area_pct", "breakdown_pct", "erythema_pct")


def _ungraded_quality(image: np.ndarray, w: int, h: int) -> QualityReport:
    """A placeholder report for a frame the input gate refused before the
    quality gate ran.

    Its checks are empty on purpose. Publishing focus and exposure numbers for
    an image that was never accepted as a capture would invite a reader to
    conclude the picture was fine -- and the finding is that it is not a
    capture at all, whatever its focus was.
    """
    return QualityReport(
        passed=False, checks=[], width=w, height=h, subject_fraction=0.0,
        focus_var=0.0, exposure_mean=0.0, confidence_factor=0.0, mask=None,
    )


def _measurements(result, cal) -> dict:
    """Percentages as measured, plus cm² when the frame carried a size
    reference. Serial comparison is only valid on the cm² figures."""
    subject_px = float(result.features.get("subject_area_px", 0.0))
    out: dict = {
        "scale": cal.scale.to_json(),
        "areas": {},
        "comparable_between_visits": bool(cal.scale.available),
        "caveat": (
            "Areas in cm² are derived from a card of known size in the frame "
            "and assume it lies flat in the same plane as the wound. They are "
            "a measurement of the visible surface, not of depth or volume."
            if cal.scale.available else
            "No size reference in this image, so areas are a percentage of the "
            "imaged region only. Do NOT compare them with another visit — "
            "moving the camera changes them."
        ),
    }
    for name in _AREA_FEATURES:
        pct = result.features.get(name)
        if pct is None:
            continue
        entry: dict = {"percent_of_region": pct}
        if cal.scale.available and subject_px > 0:
            entry["cm2"] = round(
                cal.scale.area_cm2(subject_px * float(pct) / 100.0) or 0.0, 3)
        out["areas"][name] = entry
    return out


def execute(job: AnalysisJob) -> AnalysisOutput:
    """Quality gate, then module analysis, then overlay. CPU-bound."""
    image = cv_utils.decode_image(job.image_bytes)
    if image is None:
        raise UnreadableImage(
            "The uploaded file could not be decoded as an image."
        )

    h, w = image.shape[:2]

    # -- the input gate, part one: is this a photograph of this patient? ------
    # Before the quality gate, because these two questions are answerable on a
    # frame the quality gate would condemn, and because a watermarked stock
    # image should be refused for being one rather than sent back for a
    # re-capture that cannot fix it.
    refusal = input_gate.check_provenance(image)
    if refusal is not None:
        return AnalysisOutput(quality=_ungraded_quality(image, w, h), width=w,
                              height=h, input_rejection=refusal)

    quality = run_quality_gate(image)

    # A failing image is never analysed. Analysing a photo we know is unusable
    # would produce a confident-looking result from nothing.
    if not quality.passed:
        return AnalysisOutput(quality=quality, width=w, height=h)

    # -- the input gate, part two: is enough of the subject in frame? ---------
    # After the quality gate. An underexposed frame reads as having no subject
    # in it, and "move closer" is the wrong instruction for a photograph that
    # needs more light. See input_gate.check_framing.
    refusal = input_gate.check_framing(image)
    if refusal is not None:
        return AnalysisOutput(quality=quality, width=w, height=h,
                              input_rejection=refusal)

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
        # `cal` is computed above, before any measurement, and is passed in
        # because evidence strength is coupled to it: whether a usable size
        # reference was in the frame is a precondition for the score meaning
        # anything. See analysis.prerequisites.
        result = backend.analyze(image, job.module, quality, cal)
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
            image, result.lesions, result.triage, quality, job.module,
            features=result.features,
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

    # Real-world size, when the card gave one. Percentages are a fraction of
    # the imaged region and change with camera distance, so they cannot be
    # compared between visits; cm² can. Both are reported, and the absence of
    # cm² is stated rather than left to be inferred.
    result.features["measurement"] = _measurements(result, cal)

    # The card as a light meter. Underexposure compresses every dark-area
    # comparison toward the bottom of the range, so a foot photographed in poor
    # light produces dark regions that are dark because of the lamp.
    lighting = calibration.lighting_from_card(
        cal.card, result.features.get("subject_L_median"))
    result.features["lighting"] = lighting
    if lighting.get("assessable") and not lighting.get("adequate"):
        result.triage.rationale.insert(0, lighting["note"])

        # THE SAME RULE AS THE SHADOW ONE, from a different measurement. A dark
        # area in a capture the card proves was underexposed is not evidence of
        # anything on its own, so it raises no urgent flag — and the guard is
        # identical: tissue loss anywhere in the frame disarms it, because a
        # badly lit ulcer is still an ulcer.
        features = result.features
        no_tissue_loss = float(features.get("breakdown_pct", 0.0)) < 0.4
        darkness_drove_it = float(features.get("dark_area_pct", 0.0)) > 0
        if no_tissue_loss and darkness_drove_it and result.triage.grade.rank >= 2:
            spec = routing_for(job.module, str(Grade.MONITOR))
            result.triage.grade = Grade.MONITOR
            result.triage.label = spec["label"]
            result.triage.urgency = spec["urgency"]
            result.triage.routing_target = spec["routing_target"]
            result.triage.next_investigation = spec["next_investigation"]
            result.triage.confidence = min(result.triage.confidence, 0.3)
            result.features["re_image_required"] = {
                "reason": "The reference card shows the capture was "
                          "underexposed, and there is no tissue loss in the "
                          "frame. A dark area here is not evidence on its own.",
                "instruction": lighting.get(
                    "advice", "Re-take with more light."),
            }
            result.triage.rationale.insert(
                0, "No urgent flag is raised from darkness in an "
                   "underexposed image. RE-IMAGE with more light.")
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

    # The one or two questions that would actually change this answer. Built
    # last, so every measurement and every caveat above is available to them.
    result.features["clarifying_questions"] = clarify.build(result.features)

    # What the percentages are a percentage OF. When the mask is the whole
    # frame — a close-up, or a widened segmentation — an area is diluted by
    # whatever background is in shot, and a diluted number that looks like a
    # measurement is how something gets missed.
    subject_px = float(result.features.get("subject_area_px", 0.0))
    frame_px = float(w * h)
    covers = subject_px / frame_px if frame_px else 0.0
    result.features["denominator"] = {
        "measured_against": "whole frame" if covers > 0.97 else "segmented foot region",
        "region_share_of_frame": round(covers, 3),
        "note": (
            "Percentages are a share of the WHOLE FRAME, because the foot "
            "could not be separated from the background. Any background in "
            "shot dilutes them, so an area is understated."
            if covers > 0.97 else
            "Percentages are a share of the segmented foot region, not of the "
            "photograph."
        ),
    }

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
