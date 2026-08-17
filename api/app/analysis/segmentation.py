"""Model-agnostic wound-segmentation interface.

WHY THIS EXISTS
---------------
The heuristic localiser cannot distinguish a moderately sized dark/textured
non-wound from a true ulcer — that is a property of colour/texture features, not
a bug to patch. A real, validated segmentation model is the only thing that
closes it. This module is the SEAM that model will drop into: a single interface
that today's heuristic implements and a future model implements identically, so
the model can replace the heuristic WITHOUT touching the safety pipeline.

Nothing here is a model, and nothing here is downloaded. It is the contract.

THE FIVE CONCEPTS, KEPT APART
-----------------------------
This file draws the line the task asks for. Each concept lives in its own place
and none may masquerade as another:

    A. Wound SEGMENTATION      -> this file + a provider. "Where is the region?"
    B. Visual FEATURE detection -> cv_utils (masks) + classical.py. "What
                                   colours/textures are present?"
    C. EVIDENCE assessment     -> evidence.py. "What may those features claim?"
    D. TRIAGE                  -> classical._foot cascade + routing.py. "What
                                   grade / where does the patient go?"
    E. Clinical INTERPRETATION -> clinical.py + the human. "What does it mean?"

A segmentation result is A ONLY. It carries a region and a provenance. It holds
NO grade, NO diagnosis, and NO clinical claim, and the safety pipeline never
lets it acquire one: the grade is set by C and D from B, entirely independent of
this result's score. A provider that returns segmentation_score=0.99 changes no
grade, bypasses no evidence rule, and removes no clinical-review requirement.
test_segmentation_interface.py asserts exactly that.

THE HEURISTIC IS NOT WOUND DETECTION. HeuristicLocalizationProvider wraps the
existing heuristic localiser unchanged. Its method is
"heuristic_wound_region_localization", is_calibrated is False, and it says so in
every payload. Calling it "wound detection" or "accurate localisation" is
forbidden here as everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from . import localization


# --- the interface input ------------------------------------------------------

@dataclass(slots=True)
class SegmentationInput:
    """Everything any provider might need, so the two are interchangeable.

    A real model reads `image_bgr` + `subject_mask`. The heuristic reads the
    already-computed `classical_features`. Each provider uses what it needs and
    ignores the rest; the caller does not know or care which."""

    image_bgr: np.ndarray
    subject_mask: np.ndarray
    quality_factor: float
    # Pre-computed classical masks and character verdicts. A real segmentation
    # model may ignore these entirely, or use them as weak priors.
    classical_features: dict[str, Any] = field(default_factory=dict)


# --- the interface result -----------------------------------------------------

# Shared classification vocabulary, owned by the heuristic layer and reused so
# both providers speak the same language.
CONFIRMED = localization.CONFIRMED
UNCERTAIN = localization.UNCERTAIN
NONE = localization.NONE


@dataclass(slots=True)
class WoundSegmentationResult:
    """The contract every provider returns. Concept A only — a region and its
    provenance. It deliberately holds no grade and no diagnosis."""

    present: bool
    classification: str                       # CONFIRMED | UNCERTAIN | NONE
    bounding_box: tuple[int, int, int, int] | None
    area_pct: float
    # 0..1. For the heuristic this is an UNCALIBRATED boundary heuristic; for a
    # future model it is whatever that model reports, and is_calibrated says
    # whether it may be read as a probability.
    segmentation_score: float
    is_calibrated: bool
    method: str
    model_version: str
    calibration_status: str
    dataset_version: str | None = None
    limitations: list[str] = field(default_factory=list)
    mask: Any = None                          # np.ndarray, never serialised
    # Provider-specific rich detail. For the heuristic this is the full
    # WoundLocalization (contributing evidence, excluded artifacts, messages),
    # which the overlay and the existing `wound_localization` payload use. A
    # real provider may leave it None.
    detail: Any = None

    def provenance(self) -> dict[str, Any]:
        """The interface + provenance view. Visible in internal/admin output."""
        return {
            "present": self.present,
            "classification": self.classification,
            "bounding_box": (
                {"x": self.bounding_box[0], "y": self.bounding_box[1],
                 "w": self.bounding_box[2], "h": self.bounding_box[3]}
                if self.bounding_box else None
            ),
            "area_pct": round(self.area_pct, 3),
            "segmentation_score": round(self.segmentation_score, 3),
            "is_calibrated": self.is_calibrated,
            "method": self.method,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
            "calibration_status": self.calibration_status,
            "limitations": list(self.limitations),
            "score_meaning": (
                "A calibrated probability that the region is a wound."
                if self.is_calibrated else
                "UNCALIBRATED. Not a probability and not proof of a wound — a "
                "region score only. The grade for this case does not come from "
                "here."
            ),
            "does_not_carry": [
                "a grade", "a diagnosis", "a clinical decision",
            ],
        }


# --- the provider interface ---------------------------------------------------

class WoundSegmentationProvider(Protocol):
    """The one method a segmentation provider implements. A future
    RealSegmentationProvider implements exactly this and drops in unchanged."""

    method: str
    model_version: str
    is_calibrated: bool

    def segment(self, inp: SegmentationInput) -> WoundSegmentationResult: ...


# --- today's provider: the heuristic, wrapped, unchanged ----------------------

class HeuristicLocalizationProvider:
    """The current heuristic localiser behind the interface.

    It changes NOTHING about the heuristic: it calls `localization.localize`
    exactly as the backend did and adapts the result into the interface. This
    is NOT wound detection and is not calibrated, and it declares so."""

    method = "heuristic_wound_region_localization"
    model_version = "heuristic-classical-1.0"
    is_calibrated = False
    calibration_status = "uncalibrated_heuristic"
    dataset_version = None

    def segment(self, inp: SegmentationInput) -> WoundSegmentationResult:
        cf = inp.classical_features
        wl = localization.localize(
            dark_mask=cf["dark_mask"],
            dark_verdict=cf.get("dark_verdict"),
            slough_mask=cf["slough_mask"],
            slough_verdict=cf.get("slough_verdict"),
            erythema_mask=cf["erythema_mask"],
            subject_mask=inp.subject_mask,
            quality_factor=inp.quality_factor,
        )
        return WoundSegmentationResult(
            present=wl.present,
            classification=wl.classification,
            bounding_box=wl.box,
            area_pct=wl.area_pct,
            segmentation_score=wl.boundary_confidence,
            is_calibrated=False,
            method=self.method,
            model_version=self.model_version,
            calibration_status=self.calibration_status,
            dataset_version=self.dataset_version,
            limitations=[
                "Heuristic on classical colour/texture features — NOT wound "
                "detection and NOT validated localisation.",
                "Cannot distinguish a moderately sized dark/textured non-wound "
                "(pigmentation, tattoo, bruise, dried material) from a true "
                "ulcer or eschar.",
                "Never run on a real photograph; behaviour is characterised on "
                "synthetic images only.",
            ],
            mask=wl.mask,
            detail=wl,
        )


# --- the future provider: declared, deliberately not implemented --------------

class RealSegmentationProvider:
    """A validated wound-segmentation model. NOT IMPLEMENTED.

    This class marks the seam and pins the interface. When a model trained on
    real, labelled wound images exists, it is implemented HERE — nothing in the
    safety pipeline changes. Until then every method raises, so it cannot be
    wired in by accident.

    A real provider must set is_calibrated only if its score is calibrated
    against held-out labelled data, and must carry dataset_version and a
    calibration_status describing how."""

    method = "real_wound_segmentation"
    model_version = "unimplemented"
    is_calibrated = False

    def segment(self, inp: SegmentationInput) -> WoundSegmentationResult:
        raise NotImplementedError(
            "RealSegmentationProvider is a placeholder for a future validated "
            "model. It is intentionally not implemented — see segmentation.py "
            "and the data requirements in the audit report."
        )


# --- provider selection -------------------------------------------------------
#
# A module global so the backend binds the provider at call time (not import
# time), which lets a test substitute a provider without touching the backend.

_PROVIDER: WoundSegmentationProvider = HeuristicLocalizationProvider()


def active_provider() -> WoundSegmentationProvider:
    return _PROVIDER


def set_provider(provider: WoundSegmentationProvider) -> WoundSegmentationProvider:
    """Swap the active provider, returning the previous one so a caller (a test)
    can restore it. There is deliberately no config that selects a provider by
    name yet — only the heuristic exists, and a real one is wired in explicitly
    when it is built and validated."""
    global _PROVIDER
    previous = _PROVIDER
    _PROVIDER = provider
    return previous
