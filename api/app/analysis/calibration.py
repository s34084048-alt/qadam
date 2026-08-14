"""Colour calibration from a neutral reference card held in the frame.

WHAT THIS FIXES. Colour in a phone photograph is not a measurement. Auto white
balance, tungsten versus daylight versus the screen the clinician is standing
under, and the camera's own rendering move apparent colour further than most
disease does. QADAM already defends against this by stating every threshold
RELATIVE to the patient's own skin in the same frame -- but that only makes a
single image internally consistent. It does nothing for the question a clinic
actually asks: is this wound redder than it was last week?

A neutral grey or white card in the frame answers that. The card's true colour
is known, so the correction that maps it back to neutral is known, and once the
same correction is applied to the whole frame, two images taken a week apart
under different lights become comparable.

WHAT THIS DOES NOT FIX. It does not turn the camera into a colorimeter, it does
not add a finding, and it does not move any threshold. Every disclaimer, every
limitation and every routing rule is unchanged. If no card is found, or the card
is unusable, analysis proceeds exactly as before and says so -- a missing card
is not an error.

The card is removed from the subject mask before any measurement. Otherwise a
large neutral rectangle next to the foot would either be measured as if it were
skin, or become the "subject" outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from . import cv_utils, scale as scale_mod

NOT_PRESENT = (
    "No colour reference card was detected in this image. Colours are "
    "therefore comparable within this image only, not between visits."
)

HOW_TO = (
    "Place a plain neutral grey or white card flat beside the area of "
    "interest, in the same light, filling roughly a tenth of the frame. Do not "
    "let it overlap the area being assessed, and keep it out of direct glare."
)


@dataclass(slots=True)
class Calibration:
    detected: bool = False
    applied: bool = False
    reason: str | None = None
    gains_bgr: list[float] = field(default_factory=list)
    illuminant_shift: float = 0.0
    card: dict[str, Any] = field(default_factory=dict)
    # The SAME card also fixes real-world size. Colour makes two visits
    # comparable in hue; scale makes them comparable in area, which is the
    # measurement wound care actually tracks.
    scale: "scale_mod.Scale" = field(default_factory=lambda: scale_mod.Scale())

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "detected": self.detected,
            "applied": self.applied,
            "how_to": HOW_TO,
            "note": (
                "A reference card makes colour comparable between visits. It "
                "does not make any finding diagnostic and does not change any "
                "threshold."
                if self.applied else NOT_PRESENT if not self.detected
                else "A card was detected but was not usable as a reference."
            ),
        }
        if self.reason:
            out["reason"] = self.reason
        if self.applied:
            out["gains_bgr"] = [round(g, 4) for g in self.gains_bgr]
            # How far the capture's illuminant sat from neutral, as a single
            # number a clinician can read: 0 % means the camera already had it
            # right, 20 % means one channel needed a fifth more than another.
            out["illuminant_shift_pct"] = round(self.illuminant_shift * 100, 1)
        if self.card:
            out["card"] = self.card
        out["scale"] = self.scale.to_json()
        return out


def calibrate(
    bgr: np.ndarray, subject_mask: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray | None, Calibration]:
    """Returns (image, subject_mask, calibration).

    On every failure path the ORIGINAL image and mask come back untouched. This
    function can degrade to a no-op and the rest of the pipeline is unaffected.
    """
    card = cv_utils.find_reference_card(bgr, subject_mask)
    if card is None:
        return bgr, subject_mask, Calibration(detected=False)

    card_mask = card.pop("mask")
    descriptor = {k: v for k, v in card.items() if k != "area_px"}
    descriptor["bbox"] = {
        "x": card["bbox"][0], "y": card["bbox"][1],
        "w": card["bbox"][2], "h": card["bbox"][3],
    }

    measured = scale_mod.from_card(card)

    gains, refusal = cv_utils.white_balance_gain(card)
    if gains is None:
        # Still exclude it from the subject: an unusable card is a piece of
        # cardboard in the frame, and measuring it as skin is the failure this
        # whole gate exists to avoid.
        return (bgr, _exclude_card(subject_mask, card_mask),
                Calibration(detected=True, applied=False, reason=refusal,
                            card=descriptor, scale=measured))

    corrected = cv_utils.apply_gain(bgr, gains)
    shift = float(gains.max() / max(float(gains.min()), 1e-6)) - 1.0
    return (
        corrected,
        _exclude_card(subject_mask, card_mask),
        Calibration(
            detected=True,
            applied=True,
            gains_bgr=[float(g) for g in gains],
            illuminant_shift=shift,
            card=descriptor,
            scale=measured,
        ),
    )


def _exclude_card(
    subject_mask: np.ndarray | None, card_mask: np.ndarray
) -> np.ndarray | None:
    """Remove the card, plus a margin, from the subject region.

    The margin matters: the card's own edge and the shadow it casts are neither
    card nor skin, and both would be measured as dark tissue.
    """
    if subject_mask is None:
        return None
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    grown = cv2.dilate(card_mask, kernel, iterations=2)
    out = subject_mask.copy()
    out[grown > 0] = 0
    # If removing the card left nothing to measure, the "subject" WAS the card.
    # Hand back an empty mask and let the module's subject gate refuse it,
    # rather than quietly measuring a rectangle of cardboard.
    return out
