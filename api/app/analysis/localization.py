"""Heuristic wound-region localization.

WHAT THIS IS, EXACTLY. This is HEURISTIC WOUND-REGION LOCALIZATION built on the
existing classical colour/texture features. It is NOT "wound detection" and NOT
"accurate wound localization", and it must never be described as either. It
draws a box around the region the classical features flag as tissue-disruption-
like; whether that region IS a wound is exactly what a photograph cannot settle.

A "tissue_like" or "slough_like" feature is NOT proof of a wound. "tissue_like"
means only a defined boundary and a textured interior — which dark pigmentation,
a tattoo, a bruise, a hairy patch and dried material all satisfy as well as an
eschar. The audit demonstrated this directly: a large textured dark region that
is not a wound reads "tissue_like". A red box therefore asserts no more than
"Possible wound region detected. Clinical assessment required." — never that a
wound is present.

THE GAP THIS CLOSES
-------------------
The rest of the module segments COLOUR classes — a dark mask, a yellow mask, a
red mask — and drew a box around each. A box around a shadow, a box around
redness. None of them says "this is the wound", because none of them was ever a
wound detector: they are colour-threshold masks.

This layer draws a single boundary around the region where there is evidence of
ACTUAL TISSUE DISRUPTION, and only there. It reuses the character verdicts the
evidence ceiling already trusts, so it introduces no new model and cannot
re-open the false positive that work closed:

    slough_like yellow  -> a moist defect with a defined margin   -> CONFIRMED
    tissue_like dark    -> a dark tissue change, boundary+texture  -> CONFIRMED
    indeterminate       -> the module could not resolve it         -> UNCERTAIN
    shadow_like dark    -> cast light                              -> ARTIFACT (no box)
    callus_like yellow  -> dry keratin, not a defect              -> ARTIFACT (no box)
    erythema            -> surface redness, not tissue disruption  -> ARTIFACT (no box)

A RED box is drawn only for CONFIRMED disruption. UNCERTAIN gets a YELLOW box.
Artifacts get neither — a shadow or callus never becomes a wound box, which is
exactly what the healthy-foot / shadow / callus regressions require.

IT CHANGES NO GRADE. Localization is a drawing and a description. The grade
still comes from the cascade and the evidence ceiling, untouched.

NOT A DIAGNOSIS. The most a RED box asserts is "Possible wound region detected.
Clinical assessment required." boundary_confidence is an UNCALIBRATED heuristic
about spatial coherence and image quality — never a probability, and never a
statement that the region IS a wound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from . import cv_utils
from .evidence import PARAMS

CONFIRMED = "confirmed_possible_wound"
UNCERTAIN = "uncertain_surface_abnormality"
NONE = "no_wound_region"

# Above this share of the foot, a single "wound" is implausible and a red box
# overstates the evidence. A crude, UNVALIDATED size heuristic — see localize().
WOUND_MAX_PLAUSIBLE_FRACTION = 0.35

WOUND_MESSAGE = "Possible wound region detected. Clinical assessment required."
UNCERTAIN_MESSAGE = (
    "Possible surface abnormality of uncertain nature. Clinical assessment "
    "required."
)

BOUNDARY_CONFIDENCE_NOTE = (
    "Uncalibrated heuristic reflecting spatial coherence of the region and "
    "image quality. NOT a probability and NOT a statement that the region is a "
    "wound — it describes how cleanly a boundary could be drawn, nothing about "
    "what is inside it."
)


@dataclass(slots=True)
class WoundLocalization:
    present: bool
    classification: str
    box: tuple[int, int, int, int] | None            # x, y, w, h
    area_pct: float                                   # wound / subject region
    boundary_confidence: float                        # 0..1, UNCALIBRATED
    components: int
    contributing: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    message: str = ""
    # The wound mask itself, for the overlay. Never serialised.
    mask: Any = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "method": "heuristic_wound_region_localization",
            "method_note": (
                "Heuristic region localisation from classical colour/texture "
                "features. NOT wound detection and NOT validated wound "
                "localisation. A drawn region is not proof of a wound."
            ),
            "present": self.present,
            "classification": self.classification,
            "box": (
                {"x": self.box[0], "y": self.box[1],
                 "w": self.box[2], "h": self.box[3]}
                if self.box else None
            ),
            "area_pct": round(self.area_pct, 3),
            "boundary_confidence": round(self.boundary_confidence, 3),
            "boundary_confidence_note": BOUNDARY_CONFIDENCE_NOTE,
            "components": self.components,
            "contributing_evidence": list(self.contributing),
            "excluded_as_artifact": list(self.artifacts),
            "message": self.message,
            # Key deliberately NOT named with the substring the safety-boundary
            # guard forbids: no field in any payload may be *called* a
            # diagnosis, even to deny one. The content still denies it.
            "interpretation_limit": (
                "A drawn boundary is not a diagnosis. Tissue viability, depth, "
                "infection and bone involvement are not assessable from a "
                "photograph."
            ),
        }
        return out


def _largest_component(mask: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The single biggest connected blob, and its bounding box. A wound is one
    thing with a boundary; taking the largest component discards scatter that a
    raw pixel count would have summed into a phantom region."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros_like(mask), (0, 0, 0, 0)
    idx = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
    comp = np.where(labels == idx, 255, 0).astype(np.uint8)
    x = int(stats[idx, cv2.CC_STAT_LEFT]); y = int(stats[idx, cv2.CC_STAT_TOP])
    w = int(stats[idx, cv2.CC_STAT_WIDTH]); h = int(stats[idx, cv2.CC_STAT_HEIGHT])
    return comp, (x, y, w, h)


def localize(
    *,
    dark_mask: np.ndarray,
    dark_verdict: str | None,
    slough_mask: np.ndarray,
    slough_verdict: str | None,
    erythema_mask: np.ndarray,
    subject_mask: np.ndarray,
    quality_factor: float,
) -> WoundLocalization:
    """Build a wound boundary from tissue-disruption evidence only.

    Every mask here has already been through the module's cleaning and
    thin-structure removal. This function decides which of them count as tissue
    disruption, unions those, and localises the result. It never lowers or
    raises a grade.
    """
    subject_area = float((subject_mask > 0).sum())
    confirmed = np.zeros(dark_mask.shape[:2], np.uint8)
    uncertain = np.zeros(dark_mask.shape[:2], np.uint8)
    contributing: list[str] = []
    artifacts: list[str] = []

    slough_present = (slough_mask > 0).sum() > 0
    dark_present = (dark_mask > 0).sum() > 0
    ery_present = (erythema_mask > 0).sum() > 0

    if slough_present:
        if slough_verdict == "slough_like":
            confirmed = cv2.bitwise_or(confirmed, slough_mask)
            contributing.append(
                "moist tissue in a defect (defined margin, wet surface)")
        elif slough_verdict == "callus_like":
            artifacts.append(
                "dry callus (thickened keratin) — not scored as a wound; an "
                "ulcer beneath it can only be excluded by paring and looking")
        else:  # indeterminate / None
            uncertain = cv2.bitwise_or(uncertain, slough_mask)
            contributing.append("yellow surface material, character unresolved")

    if dark_present:
        if dark_verdict == "tissue_like":
            confirmed = cv2.bitwise_or(confirmed, dark_mask)
            contributing.append(
                "dark tissue change (defined boundary, textured interior)")
        elif dark_verdict == "shadow_like":
            artifacts.append("shadow / cast light — not scored as a wound")
        else:
            # UNRESOLVED DARKNESS IS NOT GIVEN A BOX. A noisy shadow reads
            # "indeterminate" too, and the specification is explicit that a
            # shadow gets no wound box. We cannot tell a noisy shadow from noisy
            # dark tissue here, so the safe reading of an ambiguous DARK area is
            # "possibly cast light" — no box. The finding is not lost: the grade
            # cascade and the evidence ceiling still flag it for a clinician to
            # look. Only the localisation boundary is withheld.
            artifacts.append(
                "unresolved dark area — not localised as a wound (may be cast "
                "light); still flagged for review by the grade")

    if ery_present:
        # Redness is a colour, not a break in the surface. It never localises a
        # wound; it is listed as excluded so the overlay can label it BLUE.
        artifacts.append("surface redness — not tissue disruption")

    has_confirmed = (confirmed > 0).sum() > 0
    has_uncertain = (uncertain > 0).sum() > 0

    if not has_confirmed and not has_uncertain:
        return WoundLocalization(
            present=False, classification=NONE, box=None, area_pct=0.0,
            boundary_confidence=0.0, components=0, contributing=contributing,
            artifacts=artifacts, message="", mask=None)

    if has_confirmed:
        # The disrupted zone is the confirmed evidence plus any unresolved
        # region touching it — an eschar with an unresolved dark halo is one
        # wound, not two.
        wound = cv2.bitwise_or(confirmed, uncertain)
        classification = CONFIRMED
    else:
        wound = uncertain
        classification = UNCERTAIN

    comp, box = _largest_component(wound)
    coherence = cv_utils.region_coherence(wound)
    comp_area = float((comp > 0).sum())
    area_pct = (comp_area / subject_area * 100.0) if subject_area > 0 else 0.0

    # An analysable-but-degraded capture cannot support a CONFIRMED (red) box.
    # It is not refused — the quality GATE already refuses the worst images —
    # but a red boundary drawn on a poor photograph overstates what is known,
    # so it is softened to uncertain.
    if classification == CONFIRMED and quality_factor < PARAMS["min_quality_factor_for_urgent"]:
        classification = UNCERTAIN
        artifacts.append(
            "image quality too low to confirm a boundary — shown as uncertain")

    # PLAUSIBILITY GUARD against a dangerous false positive. "tissue_like" means
    # a defined boundary and a textured interior — NOTHING about the region
    # being a wound. A large, hard-edged, textured DARK region (dark
    # pigmentation, a tattoo, a hairy patch, dried material) satisfies it just
    # as well as an eschar, and a red "POSSIBLE WOUND" box over half the foot
    # asserts far more than the evidence carries. A single ulcer filling most
    # of the foot is also less likely than a framing or lighting problem.
    #
    # So an implausibly large region cannot be a CONFIRMED (red) box; it is
    # shown as UNCERTAIN instead. This changes only the LOCALISATION colour —
    # the grade is untouched, set by the evidence ceiling. It is a crude size
    # heuristic, not a validated threshold, and it does NOT make a smaller
    # textured non-wound distinguishable from a wound (see the audit).
    if classification == CONFIRMED and area_pct > 100.0 * WOUND_MAX_PLAUSIBLE_FRACTION:
        classification = UNCERTAIN
        artifacts.append(
            f"region covers {area_pct:.0f}% of the foot — implausibly large for "
            f"a single wound, and more likely pigmentation, a broad shadow or a "
            f"framing problem. Shown as uncertain, not a red wound box.")

    # UNCALIBRATED boundary strength. Confirmed evidence starts higher; a more
    # coherent (single, connected) region scores higher; a poor capture scores
    # lower. Bounded well below 1 — an unvalidated placeholder cannot claim a
    # crisp boundary it has no way to verify.
    dom = float(coherence.get("dominant_fraction", 0.0) or 0.0)
    base = 0.55 if classification == CONFIRMED else 0.32
    strength = float(np.clip((base + 0.30 * dom) * quality_factor, 0.10, 0.85))

    message = WOUND_MESSAGE if classification == CONFIRMED else UNCERTAIN_MESSAGE

    return WoundLocalization(
        present=True,
        classification=classification,
        box=box,
        area_pct=area_pct,
        boundary_confidence=strength,
        components=int(coherence.get("components", 0)),
        contributing=contributing,
        artifacts=artifacts,
        message=message,
        mask=comp,
    )
