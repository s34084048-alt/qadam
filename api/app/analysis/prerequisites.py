"""What has to be true for the evidence-strength number to mean anything.

THE PROBLEM THIS EXISTS TO FIX.

`_conf` in the classical backend computes evidence strength as
`0.45 + 0.40 * evidence`, discounted by image quality and clipped to
[0.15, 0.85]. It reads NOTHING about whether the measurement it is scoring was
possible in the first place. Observed consequences:

  * 0.85 on a run where the segmentation had explicitly failed -- the foot
    could not be separated from the background, so every percentage was
    measured against the whole frame, and the score was the maximum the
    heuristic can emit.
  * 0.53 on a healthy foot where the "dark area" driving the score was
    background pixels.

Both numbers were arithmetically correct and both were meaningless. A score
that cannot go down when its own preconditions fail is not a confidence signal,
it is decoration -- and on a screening tool the failure it decorates is the
reassuring one.

WHAT THIS MODULE DOES. It turns three preconditions into structural
adjustments: a hard cap when the region measured is not trustworthy, and
penalties when the frame lacks a usable size reference. Every adjustment is
itemised and carried to the UI, so the number is accompanied by the reason it
is what it is.

ON THE CONSTANTS BELOW. This project has no labelled clinical images, so none
of these is fitted -- they are reasoned choices within the 0.15-0.85 band the
score already occupies, and each one says so. They are ordered by how badly the
failure undermines the measurement, which is the only property here that is
defensible from first principles. The numbers themselves are guesses and are
marked as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- the reason codes --------------------------------------------------------

# Segmentation failures. Any one of these means the pixels that were measured
# are not reliably the pixels that should have been measured.
SEG_BACKGROUND_SAME_COLOUR = "segmentation_failed_background_same_colour"
SEG_DEGENERATE_MASK = "segmentation_failed_no_subject_found"
SEG_NO_WOUND_REGION = "segmentation_found_no_wound_region"

CARD_UNUSABLE = "reference_card_seen_but_unusable"
NO_SIZE_REFERENCE = "no_size_reference_in_frame"

# --- the constants -----------------------------------------------------------

# Hard cap applied when ANY segmentation prerequisite failed.
#
# The score's own range is [0.15, 0.85]. A cap has to land clearly in the
# bottom of that band, because the thing being prevented is a failed
# measurement presenting as a moderately confident one. 0.30 sits a quarter of
# the way up the band -- above the floor, so a capped result is still
# distinguishable from the worst case, and well below the 0.50 that a reader
# would parse as "even odds".
#
# GUESS. Not fitted to anything; there is no labelled data to fit it to. What
# is defensible is the direction and the ordering, not the value. If it is ever
# calibrated, this comment is the record of what it replaced.
SEGMENTATION_FAILED_CAP = 0.30

# Penalty when a reference card WAS found but could not be used -- too small to
# measure from (< MIN_CARD_LONG_PX), too tilted (> MAX_ASPECT_ERROR), or
# rejected as a colour reference.
#
# Larger than the missing-card penalty below, deliberately. A card that was
# seen and rejected means the frame contains a known object the pipeline could
# not interpret: the capture geometry or the lighting is questionable, and that
# bears on every colour and area measured from the same frame, not just on the
# absolute scale. A card that is simply absent says nothing about the rest of
# the capture.
#
# GUESS, as above. The ordering against NO_SIZE_REFERENCE_PENALTY is the
# reasoned part; 0.10 itself is chosen to be material without, on its own,
# dominating the evidence term.
CARD_UNUSABLE_PENALTY = 0.10

# Penalty when there is no size reference in the frame at all.
#
# The narrowest of the three failures. Areas remain valid as a share of the
# imaged region; what is lost is cm² and therefore any comparison with another
# visit, because moving the camera changes every percentage. That is a real
# limitation and the score should reflect it, but it does not make the current
# reading wrong.
#
# GUESS. Half the card-unusable penalty, for the ordering reason above.
NO_SIZE_REFERENCE_PENALTY = 0.05

# The existing floor from `_conf`. Adjustments may not drive the score below
# it: reporting a near-zero strength would imply a precision about our own
# uncertainty that we do not have either.
FLOOR = 0.15


# --- what the caller reports -------------------------------------------------

@dataclass(slots=True)
class Prerequisites:
    """The preconditions as observed for ONE analysis.

    Built and passed as a value, never stored on a backend -- the backends are
    module-level singletons serving concurrent analyses, and per-analysis state
    on `self` is exactly the bug fixed in the commit before this one.
    """

    # Which segmentation failures fired. Any non-empty list triggers the cap.
    segmentation_failures: list[str] = field(default_factory=list)
    # Set when a card was detected but could not be used; the string is the
    # pipeline's own reason, shown to the user verbatim.
    card_unusable_reason: str | None = None
    # True when no reference card was detected at all.
    no_size_reference: bool = False


def evaluate(
    *,
    background_warning: dict[str, Any] | None,
    subject_mask_was_degenerate: bool,
    wound_classification: str | None,
    no_wound_region_marker: str,
    calibration: Any | None,
) -> Prerequisites:
    """Read the three preconditions off one analysis's own state.

    Kept as a pure function of explicit arguments so it can be tested without
    running the pipeline, and so no caller is tempted to reach for shared
    state to answer these questions.
    """
    failures: list[str] = []
    if background_warning:
        failures.append(SEG_BACKGROUND_SAME_COLOUR)
    if subject_mask_was_degenerate:
        failures.append(SEG_DEGENERATE_MASK)
    if wound_classification == no_wound_region_marker:
        failures.append(SEG_NO_WOUND_REGION)

    card_unusable_reason: str | None = None
    no_size_reference = False
    if calibration is not None:
        scale = getattr(calibration, "scale", None)
        scale_available = bool(getattr(scale, "available", False))
        if not calibration.detected:
            # No card in the frame. Areas stay valid as a share of the imaged
            # region; cm² and between-visit comparison are what is lost.
            no_size_reference = True
        elif not scale_available or not calibration.applied:
            # Seen and rejected. Prefer the scale module's reason (it names the
            # geometry problem -- tilt, or too few pixels) and fall back to the
            # colour refusal when the card failed only as a colour reference.
            card_unusable_reason = (
                getattr(scale, "reason", None) or calibration.reason
                or "A reference card was detected but could not be used."
            )

    return Prerequisites(
        segmentation_failures=failures,
        card_unusable_reason=card_unusable_reason,
        no_size_reference=no_size_reference,
    )


# --- applying them -----------------------------------------------------------

_SEGMENTATION_DETAIL = {
    SEG_BACKGROUND_SAME_COLOUR: (
        "The foot could not be separated from the background, so the "
        "percentages were measured against the whole frame rather than the "
        "foot."
    ),
    SEG_DEGENERATE_MASK: (
        "No subject region could be found in this image, so the whole frame "
        "was measured instead."
    ),
    SEG_NO_WOUND_REGION: (
        "No wound region was isolated in this image. That is also what an "
        "unbroken foot looks like to this module, and the two cannot be told "
        "apart from a photograph."
    ),
}


def apply(
    confidence: float, prereqs: Prerequisites
) -> tuple[float, list[dict[str, Any]]]:
    """Return the adjusted score and an itemisation of every adjustment.

    Order is cap first, then penalties, then the floor. A cap is a statement
    about the measurement being untrustworthy, so it binds before anything
    that merely narrows what the measurement can be compared with.

    The itemisation is the point of this function as much as the number is. A
    reader must be able to see WHY the score is what it is, so each entry
    carries the reason code, the human-readable detail, and the arithmetic.
    """
    adjustments: list[dict[str, Any]] = []
    adjusted = float(confidence)

    if prereqs.segmentation_failures and adjusted > SEGMENTATION_FAILED_CAP:
        adjustments.append({
            "kind": "cap",
            "reason": "segmentation_failed",
            "detail": (
                "A prerequisite for measuring this image failed, so the "
                "evidence strength is capped. "
                + " ".join(_SEGMENTATION_DETAIL[f]
                           for f in prereqs.segmentation_failures)
            ),
            "triggered_by": list(prereqs.segmentation_failures),
            "from": round(adjusted, 3),
            "to": SEGMENTATION_FAILED_CAP,
        })
        adjusted = SEGMENTATION_FAILED_CAP
    elif prereqs.segmentation_failures:
        # The cap applies but the score was already at or below it. Still
        # itemised: the prerequisite failed, and a reader must see that it was
        # checked, not infer it from a number that happens to look low.
        adjustments.append({
            "kind": "cap",
            "reason": "segmentation_failed",
            "detail": (
                "A prerequisite for measuring this image failed. The evidence "
                "strength was already at or below the cap, so no reduction "
                "was needed. "
                + " ".join(_SEGMENTATION_DETAIL[f]
                           for f in prereqs.segmentation_failures)
            ),
            "triggered_by": list(prereqs.segmentation_failures),
            "from": round(adjusted, 3),
            "to": round(adjusted, 3),
        })

    for reason, detail, penalty in _penalties(prereqs):
        before = adjusted
        adjusted = max(FLOOR, adjusted - penalty)
        adjustments.append({
            "kind": "penalty",
            "reason": reason,
            "detail": detail,
            "penalty": penalty,
            "from": round(before, 3),
            "to": round(adjusted, 3),
        })

    return float(max(FLOOR, adjusted)), adjustments


def _penalties(prereqs: Prerequisites):
    if prereqs.card_unusable_reason:
        yield (
            CARD_UNUSABLE,
            "A reference card was in the frame but could not be used: "
            f"{prereqs.card_unusable_reason}",
            CARD_UNUSABLE_PENALTY,
        )
    if prereqs.no_size_reference:
        yield (
            NO_SIZE_REFERENCE,
            "There is no size reference in the frame, so areas are a share of "
            "the imaged region only and cannot be compared with another "
            "visit.",
            NO_SIZE_REFERENCE_PENALTY,
        )
