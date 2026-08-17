"""What the pixels support, kept separate from what the pixels are.

THE FAILURE THIS FILE EXISTS FOR
--------------------------------
A visually healthy foot was graded URGENT. Two independent paths produced it,
both measured and reproduced before this file was written:

  1. `dark_region_character` returned "indeterminate" -- its two measurements
     disagreed -- and the shadow rule tested for "shadow_like" exactly. Anything
     else fell straight through to the urgent branch. So the module was MOST
     confident precisely where it had just declared itself unable to tell, which
     is backwards. A noisy handheld photograph of a shadow between two toes
     reached "urgent" at 0.68 confidence.

  2. `yellow_region_character` returned "callus_like" and NOTHING CONSUMED IT.
     Dry thickened keratin -- extremely common on a diabetic foot, and not a
     wound -- was counted as tissue breakdown and crossed the urgent threshold
     at 0.85 confidence, the highest figure the model can express.

Both are the same bug in different clothes: AREA AND COLOUR WERE TREATED AS
EVIDENCE OF A THING. They are not. They are evidence that some pixels differ
from other pixels.

THE RULE THIS FILE IMPOSES
--------------------------
A measurement may only support the urgent grade when the evidence is
sufficient AND coherent AND the image was good enough to read. Otherwise the
finding is still reported -- nothing here deletes a finding -- but it is capped
at a grade that means "a person needs to look at this", which is the honest
consequence of not knowing.

NOTHING HERE RAISES A GRADE. Every rule in this file can only lower a ceiling.
A file that could escalate would be a file that could invent an emergency.

WHAT IS DELIBERATELY ASYMMETRIC
-------------------------------
Ambiguity about a DARK area resolves toward caution about the ALARM: the
competing explanation (cast light) is benign and is the single most common
thing in a foot photograph. Ambiguity about a YELLOW area resolves toward
caution about the PATIENT: the competing explanation (callus) is not benign,
because an ulcer very often lies underneath callus and cannot be seen until it
is pared back. So "indeterminate" caps the dark path and does not cap the
yellow one. That asymmetry is clinical, not statistical, and it is asserted in
test_evidence_gate.py so it cannot be "tidied up" into symmetry later.

THESE ARE RESEARCH PARAMETERS, NOT VALIDATED CLINICAL THRESHOLDS.
No value in this file was derived from labelled clinical images, because this
project has none. They are stated, inspectable and versioned so that a
validation study can report exactly what was in force -- and so that when one
is run, they can be replaced by measured values rather than argued about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import Grade

# --- research parameters -----------------------------------------------------
#
# Every one of these is a judgement about SPATIAL and OPTICAL structure, not
# about disease. None is a medical threshold and none may be presented as one.

PARAMS: dict[str, float] = {
    # A wound is one connected thing. Below this share in the largest connected
    # component the region is a scatter, and a scatter that sums to a big
    # percentage is still a scatter.
    "breakdown_min_dominant_fraction": 0.55,
    "dark_min_dominant_fraction": 0.50,
    # Quality discount below which the capture cannot support an urgent visual
    # claim. The quality gate's own pass/fail is separate and stricter: this is
    # the band where the image is analysable but not reliable.
    "min_quality_factor_for_urgent": 0.60,
}

PARAM_STATUS = (
    "Configurable research parameters. Not derived from labelled clinical "
    "images and not clinically validated. They govern spatial coherence and "
    "image reliability, not disease. Developed on SYNTHETIC scenarios only; the "
    "clinical sensitivity and specificity of the resulting grades are UNKNOWN. "
    "Any evidence-strength score attached to a grade is an uncalibrated "
    "heuristic and must not be interpreted as a probability. This system is "
    "NOT clinically validated."
)

# What no photograph settles, stated once and attached to every report.
NOT_DETERMINABLE = [
    "tissue viability",
    "depth of any defect",
    "skin or limb temperature",
    "perfusion and arterial supply",
    "sensation and neuropathy",
    "infection",
    "bone involvement",
]

NORMAL = "no_significant_visual_abnormality"
ABNORMAL = "potentially_abnormal_appearance"
UNREADABLE = "insufficient_image_quality"

APPEARANCE_MEANING = {
    NORMAL: (
        "No significant visual abnormality was detected in this image. This is "
        "NOT a finding that the patient is healthy, and it is not a "
        "examination. It means the surface measurements in this photograph did "
        "not isolate anything to report."
    ),
    ABNORMAL: (
        "Something in this image differs enough from the surrounding skin to be "
        "worth a clinician's eyes. What it IS has not been determined."
    ),
    UNREADABLE: (
        "Insufficient image quality for reliable visual assessment. No visual "
        "interpretation is offered from this capture."
    ),
}


@dataclass(slots=True)
class Finding:
    """One measured surface feature, and the ceiling its evidence supports."""

    kind: str
    observed: str                       # purely visual, no clinical noun
    ceiling: Grade
    sufficient_for_urgent: bool
    limits: list[str] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "observed": self.observed,
            "ceiling": str(self.ceiling),
            "sufficient_for_urgent": self.sufficient_for_urgent,
            "limits": list(self.limits),
            "measurements": dict(self.measurements),
        }


@dataclass(slots=True)
class Report:
    appearance: str
    ceiling: Grade
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "appearance": self.appearance,
            "appearance_meaning": APPEARANCE_MEANING[self.appearance],
            "ceiling": str(self.ceiling),
            "ceiling_meaning": (
                "The most urgent grade the VISUAL evidence in this image can "
                "support. The grade shown may be lower. It can never be higher."
            ),
            "findings": [f.to_json() for f in self.findings],
            "notes": list(self.notes),
            "cannot_be_determined_from_a_photograph": list(NOT_DETERMINABLE),
            "parameters": dict(PARAMS),
            "parameter_status": PARAM_STATUS,
            "separation": (
                "'observed' is what the pixels show. It is not a diagnosis, and "
                "no entry here names a disease."
            ),
        }


def _quality_ok(quality_factor: float) -> bool:
    return quality_factor >= PARAMS["min_quality_factor_for_urgent"]


def _breakdown(f: dict, quality_factor: float) -> Finding:
    """Yellow-on-surface. Slough in a defect, or dry keratin on intact skin?"""
    pct = float(f.get("breakdown_pct", 0.0) or 0.0)
    character = (f.get("yellow_area_character") or {}).get("verdict")
    coherence = f.get("breakdown_coherence") or {}
    dominant = float(coherence.get("dominant_fraction", 0.0) or 0.0)

    limits: list[str] = []
    ok = True

    if dominant < PARAMS["breakdown_min_dominant_fraction"]:
        ok = False
        limits.append(
            f"The yellow area is not one region: its largest connected piece is "
            f"{dominant * 100:.0f}% of the total, across "
            f"{coherence.get('components', 0)} separate pieces. A wound has a "
            f"boundary; scattered colour variation does not. The percentage "
            f"alone cannot tell them apart, so it does not support an urgent "
            f"visual grade."
        )

    if character == "callus_like":
        ok = False
        limits.append(
            "The surface has no edge at skin level and is dry — consistent with "
            "thickened keratin rather than tissue in an open defect. THIS IS "
            "NOT REASSURANCE: an ulcer frequently lies underneath callus and is "
            "invisible until it is pared back. It is a reason to have someone "
            "look and pare, not a reason to raise a same-day alarm from a "
            "photograph."
        )

    if not _quality_ok(quality_factor):
        ok = False
        limits.append(
            "Image quality is insufficient for reliable visual assessment, so "
            "no urgent visual grade is raised from it."
        )

    return Finding(
        kind="tissue_breakdown",
        observed=(
            f"Yellow surface material over {pct:.1f}% of the imaged region."
            if pct > 0 else "No yellow surface material isolated."
        ),
        ceiling=Grade.URGENT if ok else Grade.REVIEW,
        sufficient_for_urgent=ok,
        limits=limits,
        measurements={"area_pct": pct, "character": character,
                      "coherence": coherence},
    )


def _dark(f: dict, quality_factor: float) -> Finding:
    """Dark-on-surface. The path that produced the healthy-toe false positive."""
    pct = float(f.get("dark_area_pct", 0.0) or 0.0)
    character = (f.get("dark_area_character") or {}).get("verdict")
    coherence = f.get("dark_coherence") or {}
    dominant = float(coherence.get("dominant_fraction", 0.0) or 0.0)

    limits: list[str] = []
    ok = True

    # THE FAIL-OPEN THAT CAUSED THE FALSE POSITIVE. Only a positive reading of
    # "this is on the skin" supports an urgent visual grade. "indeterminate"
    # means the two measurements disagreed, and disagreement is not evidence.
    if character != "tissue_like":
        ok = False
        limits.append(
            "The darkness reads as cast light rather than a change in the "
            "tissue."
            if character == "shadow_like" else
            "The boundary and surface measurements disagree, so this module "
            "cannot tell a shadow from something on the skin here. "
            "Disagreement is not evidence, and no urgent visual grade is "
            "raised from it."
        )

    if dominant < PARAMS["dark_min_dominant_fraction"]:
        ok = False
        limits.append(
            f"The dark area is not one region: its largest connected piece is "
            f"{dominant * 100:.0f}% of the total, across "
            f"{coherence.get('components', 0)} separate pieces."
        )

    if not _quality_ok(quality_factor):
        ok = False
        limits.append(
            "Image quality is insufficient for reliable visual assessment, so "
            "no urgent visual grade is raised from it."
        )

    return Finding(
        kind="dark_area",
        observed=(
            f"Area {pct:.1f}% of the imaged region is markedly darker than the "
            f"surrounding skin."
            if pct > 0 else "No discrete dark area isolated."
        ),
        ceiling=Grade.URGENT if ok else Grade.REVIEW,
        sufficient_for_urgent=ok,
        limits=limits,
        measurements={"area_pct": pct, "character": character,
                      "coherence": coherence},
    )


def _erythema(f: dict) -> Finding:
    """Redness. Never urgent from a photograph, and this is not a new limit --
    the module has never let erythema exceed REVIEW. It is stated explicitly
    here so the reason survives a future edit."""
    pct = float(f.get("erythema_pct", 0.0) or 0.0)
    return Finding(
        kind="erythema",
        observed=(
            f"Surface redness over {pct:.1f}% of the imaged region."
            if pct > 0 else "No surface redness isolated."
        ),
        ceiling=Grade.REVIEW,
        sufficient_for_urgent=False,
        limits=[
            "Redness in a photograph is a colour, and colour is set as much by "
            "the lamp and the camera's white balance as by the skin. It cannot "
            "establish warmth, infection or inflammation, none of which is "
            "visible. Temperature is NOT inferable from an image."
        ],
        measurements={"area_pct": pct},
    )


def assess(features: dict, quality_factor: float = 1.0) -> Report:
    """The evidence ceiling for one analysed image.

    Called by the backend after measurement and before grading. Returns the
    most urgent grade the visual evidence supports; the backend grades at or
    below it.
    """
    dark_pct = float(features.get("dark_area_pct", 0.0) or 0.0)
    brk_pct = float(features.get("breakdown_pct", 0.0) or 0.0)
    ery_pct = float(features.get("erythema_pct", 0.0) or 0.0)

    findings = [
        _dark(features, quality_factor),
        _breakdown(features, quality_factor),
        _erythema(features),
    ]

    anything_isolated = dark_pct > 0 or brk_pct > 0 or ery_pct > 0
    if not _quality_ok(quality_factor):
        appearance = UNREADABLE
    elif anything_isolated:
        appearance = ABNORMAL
    else:
        appearance = NORMAL

    # The ceiling is the most urgent any single finding can justify. A finding
    # with zero area justifies nothing, so it is excluded -- otherwise an empty
    # erythema finding would hold the ceiling at REVIEW on a blank image.
    live = [
        fnd for fnd in findings
        if float(fnd.measurements.get("area_pct", 0.0) or 0.0) > 0
    ]
    if not live:
        ceiling = Grade.NO_FLAG
    else:
        ceiling = max(
            (fnd.ceiling if fnd.sufficient_for_urgent else Grade.REVIEW
             for fnd in live),
            key=lambda g: g.rank,
        )

    notes: list[str] = []
    if appearance == UNREADABLE:
        notes.append(APPEARANCE_MEANING[UNREADABLE])
        ceiling = min(ceiling, Grade.REVIEW, key=lambda g: g.rank)
    if appearance == NORMAL:
        notes.append(
            "No significant visual abnormality detected. This is not a "
            "statement that the foot is healthy: neuropathy, ischaemia and "
            "infection are all invisible in a photograph, and the routing "
            "decision for this case comes from the examination, not from here."
        )

    return Report(appearance=appearance, ceiling=ceiling, findings=findings,
                  notes=notes)
