"""IWGDF diabetic foot risk stratification.

This is the module that makes diabetic foot screening a product rather than a
photograph. The internationally used stratification is built on four things:

    loss of protective sensation (LOPS)
    peripheral artery disease (PAD)
    foot deformity
    history of ulcer, amputation, or end-stage renal disease

NONE of these is visible in a photograph. LOPS needs a 10 g monofilament, PAD
needs pulses and ankle or toe pressures, and history needs asking. So this is
STRUCTURED CLINICAL ENTRY, not inference: the health worker performs the
examination and records what they found, and a published rule turns it into a
risk category and a screening interval.

THE MOST IMPORTANT BEHAVIOUR IN THIS FILE is what happens when the sensory or
vascular test was NOT performed. It refuses to stratify, and says which test is
missing. That is the exact failure mode of photo-led foot screening: the
picture looks unremarkable, nobody tests sensation, and a neuropathic foot is
recorded as low risk. An absent test is not a negative test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .analysis.clinical import ClinicalContext, Consideration
from .analysis.types import Grade

Finding = Literal["present", "absent", "not_tested"]

SOURCE = (
    "Risk categories and screening intervals follow the IWGDF diabetic foot "
    "risk stratification. The category is produced by a published rule applied "
    "to findings a clinician recorded — it is not inferred from any image."
)

# category -> (label, screening interval, routing)
CATEGORIES: dict[int, dict[str, str]] = {
    0: {
        "label": "Very low risk",
        "criteria": "No loss of protective sensation and no peripheral artery "
                    "disease.",
        "interval": "Screening once a year",
        "routing": "Routine annual foot screening",
    },
    1: {
        "label": "Low risk",
        "criteria": "Loss of protective sensation OR peripheral artery disease.",
        "interval": "Screening every 6–12 months",
        "routing": "Foot protection service / trained screener",
    },
    2: {
        "label": "Moderate risk",
        "criteria": "LOPS + PAD, or LOPS + foot deformity, or PAD + foot "
                    "deformity.",
        "interval": "Screening every 3–6 months",
        "routing": "Foot protection service, podiatry-led",
    },
    3: {
        "label": "High risk",
        "criteria": "LOPS or PAD, together with a history of foot ulcer, "
                    "lower-extremity amputation, or end-stage renal disease.",
        "interval": "Screening every 1–3 months",
        "routing": "Multidisciplinary diabetic foot service",
    },
}


@dataclass(slots=True)
class RiskAssessment:
    category: int | None
    label: str
    complete: bool
    missing_tests: list[str] = field(default_factory=list)
    screening_interval: str = ""
    routing_target: str = ""
    grade: Grade = Grade.NO_FLAG
    rationale: list[str] = field(default_factory=list)
    clinical: ClinicalContext | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "label": self.label,
            "complete": self.complete,
            "missing_tests": list(self.missing_tests),
            "criteria": (CATEGORIES[self.category]["criteria"]
                         if self.category is not None else None),
            "screening_interval": self.screening_interval,
            "routing_target": self.routing_target,
            "grade": str(self.grade),
            "rationale": list(self.rationale),
            "clinical": self.clinical.to_json() if self.clinical else None,
            "source": SOURCE,
            "derived_from_image": False,
        }


def _is(value: Finding) -> bool:
    return value == "present"


def stratify(
    *,
    lops: Finding,
    pad: Finding,
    deformity: Finding,
    previous_ulcer: Finding,
    previous_amputation: Finding,
    end_stage_renal_disease: Finding,
) -> RiskAssessment:
    """Apply the IWGDF rule. Refuses to guess at an untested foot."""

    # --- the refusal path ---------------------------------------------------
    missing: list[str] = []
    if lops == "not_tested":
        missing.append(
            "Loss of protective sensation — test with a 10 g monofilament at "
            "the standard sites (and/or 128 Hz tuning fork, or Ipswich touch "
            "test where no monofilament is available)."
        )
    if pad == "not_tested":
        missing.append(
            "Peripheral artery disease — palpate dorsalis pedis and posterior "
            "tibial pulses, and measure ankle-brachial or toe pressures where "
            "pulses are absent or the history suggests it."
        )

    if missing:
        clinical = _clinical_incomplete(missing)
        return RiskAssessment(
            category=None,
            label="Cannot be stratified — required test not performed",
            complete=False,
            missing_tests=missing,
            screening_interval="Not determined. Complete the assessment.",
            routing_target="Return for the missing test before the interval "
                           "is set",
            grade=Grade.REVIEW,
            rationale=[
                "The risk category was NOT produced because a required test "
                "was not performed.",
                "AN ABSENT TEST IS NOT A NEGATIVE TEST. A foot with untested "
                "sensation cannot be called low risk, and this is exactly how "
                "neuropathic feet are missed.",
                *missing,
            ],
            clinical=clinical,
        )

    # --- the rule -----------------------------------------------------------
    has_lops, has_pad = _is(lops), _is(pad)
    has_deformity = _is(deformity)
    history = {
        "previous foot ulcer": _is(previous_ulcer),
        "lower-extremity amputation": _is(previous_amputation),
        "end-stage renal disease": _is(end_stage_renal_disease),
    }
    history_present = [name for name, value in history.items() if value]

    if (has_lops or has_pad) and history_present:
        category = 3
    elif ((has_lops and has_pad)
          or (has_lops and has_deformity)
          or (has_pad and has_deformity)):
        category = 2
    elif has_lops or has_pad:
        category = 1
    else:
        category = 0

    spec = CATEGORIES[category]
    grade = {0: Grade.NO_FLAG, 1: Grade.MONITOR,
             2: Grade.REVIEW, 3: Grade.URGENT}[category]

    rationale = [
        f"IWGDF risk category {category} — {spec['label']}.",
        f"Basis: {spec['criteria']}",
        "Loss of protective sensation: "
        + ("present" if has_lops else "absent (tested)"),
        "Peripheral artery disease: "
        + ("present" if has_pad else "absent (tested)"),
        "Foot deformity: " + ("present" if has_deformity
                              else "absent" if deformity == "absent"
                              else "not recorded"),
    ]
    if history_present:
        rationale.append("History: " + ", ".join(history_present) + ".")

    # A previous ulcer without LOPS or PAD does not meet the category-3 rule,
    # but it is unusual enough to be worth a clinician's eye rather than
    # letting the arithmetic quietly file it as low risk.
    if history_present and not (has_lops or has_pad):
        rationale.append(
            "NOTE: a history of "
            + ", ".join(history_present)
            + " was recorded without loss of protective sensation or "
              "peripheral artery disease. That combination is unusual — "
              "confirm the history and consider repeating the sensory and "
              "vascular tests before accepting this category."
        )
        grade = Grade.REVIEW

    return RiskAssessment(
        category=category,
        label=spec["label"],
        complete=True,
        screening_interval=spec["interval"],
        routing_target=spec["routing"],
        grade=grade,
        rationale=rationale,
        clinical=_clinical_complete(category, has_lops, has_pad, has_deformity,
                                    history_present),
    )


# --- clinical layer ----------------------------------------------------------

_ALWAYS_ASK = [
    "Inspect BOTH feet, including between every toe and the heels.",
    "Footwear: does it fit, is there a foreign object inside, is there a wear "
    "pattern suggesting abnormal pressure?",
    "Can the patient see and reach their own feet to inspect them?",
    "Glycaemic control, smoking, and renal function.",
    "Who checks the feet between appointments, and does the patient know what "
    "to report and to whom?",
]

_NEVER_FROM_IMAGE = [
    "Loss of protective sensation. A monofilament is required.",
    "Peripheral artery disease. Pulses and ankle or toe pressures are required.",
    "Wound depth, bone involvement, and infection.",
    "Whether a foot deformity is rigid or correctable.",
]


def _clinical_incomplete(missing: list[str]) -> ClinicalContext:
    return ClinicalContext(
        severity_index=None,
        considerations=[Consideration(
            pattern="Risk stratification attempted without a required test",
            overlaps_with=[
                "a genuinely low-risk foot",
                "a neuropathic foot that has not been tested",
                "an ischaemic foot that has not been tested",
            ],
            distinguished_by="Performing the missing test. Until it is done, "
                             "these are indistinguishable, and the difference "
                             "between them is the difference between an annual "
                             "check and a monthly one.",
        )],
        immediate_actions=[
            "Complete the missing test before setting a screening interval.",
            "Do not record this foot as low risk in the meantime.",
            *[f"Outstanding: {m}" for m in missing],
        ],
        ask_and_check=_ALWAYS_ASK,
        not_assessable=_NEVER_FROM_IMAGE,
        scales={"IWGDF": {"status": "incomplete", "source": SOURCE}},
    )


def _clinical_complete(category: int, lops: bool, pad: bool, deformity: bool,
                       history: list[str]) -> ClinicalContext:
    ctx = ClinicalContext(
        severity_index={
            "name": "IWGDF risk category",
            "value": category,
            "unit": "of 3",
            "band": CATEGORIES[category]["label"],
            "components": {
                "loss_of_protective_sensation": lops,
                "peripheral_artery_disease": pad,
                "foot_deformity": deformity,
                "history": history,
            },
            "caveat": "A category set from clinical findings, not from an "
                      "image. It sets the screening interval; it does not "
                      "describe the foot today. A category-0 foot with a new "
                      "ulcer is still an emergency.",
        },
        scales={"IWGDF": {
            "category": category,
            "criteria": CATEGORIES[category]["criteria"],
            "screening_interval": CATEGORIES[category]["interval"],
            "source": SOURCE,
        }},
        ask_and_check=_ALWAYS_ASK,
        not_assessable=_NEVER_FROM_IMAGE,
    )

    if lops:
        ctx.considerations.append(Consideration(
            pattern="Loss of protective sensation",
            overlaps_with=[
                "diabetic peripheral neuropathy",
                "vitamin B12 deficiency, which is common on metformin",
                "alcohol-related neuropathy",
                "hypothyroidism",
                "another cause entirely — neuropathy in a person with diabetes "
                "is not always diabetic neuropathy",
            ],
            distinguished_by="B12 and folate, thyroid function, an alcohol "
                             "history, and neurological examination. An "
                             "asymmetric or rapidly progressive pattern points "
                             "away from diabetic neuropathy.",
        ))
    if pad:
        ctx.considerations.append(Consideration(
            pattern="Peripheral artery disease",
            overlaps_with=[
                "atherosclerotic peripheral artery disease",
                "medial arterial calcification, which falsely RAISES the "
                "ankle-brachial index and can hide severe disease",
                "acute limb ischaemia, if the change is sudden",
            ],
            distinguished_by="Toe pressures or toe-brachial index, which are "
                             "reliable when the ankle index is falsely high in "
                             "diabetes, plus duplex ultrasound and vascular "
                             "opinion. A cold, pale, painful foot is an "
                             "emergency, not a screening finding.",
        ))
    if deformity:
        ctx.considerations.append(Consideration(
            pattern="Foot deformity",
            overlaps_with=[
                "claw or hammer toes from motor neuropathy",
                "hallux valgus or other structural deformity",
                "Charcot neuroarthropathy — a hot, swollen, deformed foot that "
                "is frequently mistaken for infection",
                "previous surgery or trauma",
            ],
            distinguished_by="Comparing skin temperature between the feet, "
                             "weight-bearing X-rays, and specialist assessment. "
                             "A warm swollen foot in a neuropathic patient is "
                             "Charcot until proven otherwise, and missing it "
                             "costs the foot.",
        ))
    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No neuropathy, arterial disease or deformity recorded",
            overlaps_with=[
                "a genuinely low-risk foot",
                "early neuropathy below the sensitivity of a monofilament",
                "arterial disease masked by a falsely high ankle-brachial index",
            ],
            distinguished_by="Repeat screening at the stated interval, and "
                             "immediate re-assessment if the patient reports "
                             "numbness, burning, rest pain, or any new lesion.",
        ))

    ctx.immediate_actions = [
        f"Set the next screening date: {CATEGORIES[category]['interval'].lower()}.",
        "Give footwear and self-inspection advice appropriate to the category, "
        "and check the patient can actually see and reach their feet.",
        "Tell the patient explicitly what to report and to whom, and how fast.",
    ]
    if category >= 2:
        ctx.immediate_actions.insert(
            0, "Refer to the foot protection or diabetic foot service — this "
               "category is not managed by screening alone.")
    if category == 3:
        ctx.immediate_actions.insert(
            0, "Any new lesion in a category-3 foot is a same-day problem, not "
               "a next-appointment problem.")
    return ctx
