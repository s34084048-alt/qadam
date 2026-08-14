"""Module catalogue and grade -> routing map.

Routing is CONFIG, not code: changing where a grade sends a patient is a data
change here. Every `next_investigation` names a real, orderable test or a real
service. None of them is a diagnosis.
"""

from __future__ import annotations

from typing import Any

from ..safety import MODULE_LIMITATIONS, NO_FLAG_CAVEAT

# Colour hints are consumed by the UI and the burned-in overlay legend.
GRADE_STYLE = {
    "no_flag": {"color": "#1B873F", "label_en": "No flag", "label_ar": "لا توجد علامات"},
    "monitor": {"color": "#C79A00", "label_en": "Monitor", "label_ar": "متابعة"},
    "review": {"color": "#E06C00", "label_en": "Review", "label_ar": "مراجعة"},
    "urgent": {"color": "#C4262E", "label_en": "Urgent", "label_ar": "عاجل"},
}


MODULES: dict[str, dict[str, Any]] = {
    "foot": {
        "id": "foot",
        "label_en": "Diabetic foot",
        "label_ar": "القدم السكرية",
        "description_en": (
            "Screens the visible surface of the foot for erythema, tissue "
            "breakdown and necrotic tissue, and routes high-risk feet to a "
            "diabetic foot service."
        ),
        "description_ar": (
            "فحص سطح القدم الظاهر بحثاً عن احمرار أو تلف نسيجي أو نخر، "
            "وتوجيه القدم عالية الخطورة إلى خدمة القدم السكرية."
        ),
        "screens": [
            "surface erythema",
            "tissue breakdown / open wound bed",
            "necrotic or eschar tissue",
        ],
        "body_sites": ["dorsum", "plantar", "heel", "toes", "medial", "lateral"],
        "routing": {
            "no_flag": {
                "label": "No surface red flag",
                "routing_target": "Routine diabetic foot surveillance",
                "next_investigation": (
                    "No new investigation triggered by this image. Continue the "
                    "patient's scheduled foot check, including pulses, ABPI and "
                    "10 g monofilament testing, which this image cannot assess."
                ),
                "urgency": "Routine",
            },
            "monitor": {
                "label": "Monitor — re-image",
                "routing_target": "Same clinician, planned review",
                "next_investigation": (
                    "Re-image in 48–72 hours and document. Clinician to assess "
                    "footwear, offloading and perfusion at the next contact."
                ),
                "urgency": "48–72 hours",
            },
            "review": {
                "label": "Clinician review",
                "routing_target": "Podiatry / diabetic foot clinic",
                "next_investigation": (
                    "Book a podiatry or diabetic foot clinic assessment within "
                    "one week. Request perfusion assessment (pulses, ABPI or "
                    "toe pressures) and neuropathy testing."
                ),
                "urgency": "Within 1 week",
            },
            "urgent": {
                "label": "Urgent — same-day service",
                "routing_target": "Same-day diabetic foot service",
                "next_investigation": (
                    "Refer to the same-day diabetic foot service. Expect wound "
                    "assessment and probe-to-bone, plain X-ray of the foot if "
                    "osteomyelitis is suspected, vascular assessment and wound "
                    "swab if infection is suspected. Depth, bone involvement and "
                    "infection cannot be judged from this image."
                ),
                "urgency": "Same day",
            },
        },
    },
    "lab": {
        "id": "lab",
        "label_en": "Laboratory results",
        "label_ar": "نتائج المختبر",
        "description_en": (
            "Flags numeric laboratory results against reference ranges, "
            "computes standard derived indices, and routes on critical values. "
            "Takes typed values, not photographs — numbers are interpreted, "
            "the patient is not."
        ),
        "description_ar": (
            "يفحص نتائج المختبر الرقمية مقابل النطاقات المرجعية، ويحسب "
            "المؤشرات المشتقة القياسية، ويوجّه عند القيم الحرجة. يعتمد على قيم "
            "مُدخلة، لا على صور."
        ),
        "screens": [
            "values outside the reference range",
            "critical values requiring immediate contact",
            "derived indices (eGFR, anion gap, adjusted calcium, NLR, FIB-4)",
        ],
        "body_sites": ["not applicable"],
        "input_kind": "numeric",
        "routing": {
            "no_flag": {
                "label": "No flagged result",
                "routing_target": "Requesting clinician",
                "next_investigation": (
                    "No result fell outside the ranges applied. Send the panel "
                    "to the requesting clinician: a normal panel does not "
                    "answer the clinical question that prompted it, and does "
                    "not exclude disease the panel does not measure."
                ),
                "urgency": "Routine",
            },
            "monitor": {
                "label": "Minor abnormality — clinician to review",
                "routing_target": "Requesting clinician, routine review",
                "next_investigation": (
                    "Send to the requesting clinician with previous results "
                    "for comparison. Repeat testing is decided by the "
                    "clinician against the clinical picture and the trend."
                ),
                "urgency": "Routine review",
            },
            "review": {
                "label": "Several abnormalities — clinician review",
                "routing_target": "Clinician review with previous results",
                "next_investigation": (
                    "Arrange clinician review. Retrieve previous results, the "
                    "current medication list and observations beforehand — the "
                    "trend and the drugs explain more panels than the numbers "
                    "alone do."
                ),
                "urgency": "Within 1 week",
            },
            "urgent": {
                "label": "Critical value — contact a clinician now",
                "routing_target": "Immediate clinician contact",
                "next_investigation": (
                    "CONTACT A CLINICIAN NOW. Confirm the sample was valid — "
                    "haemolysis, a drip-arm sample or delayed transit are "
                    "common causes of a surprising result — and repeat "
                    "urgently if there is any doubt. Obtain an ECG and "
                    "observations where potassium, calcium or glucose is "
                    "critical. Treatment decisions belong to the clinician."
                ),
                "urgency": "Immediately",
            },
        },
    },
}


def module_ids() -> list[str]:
    return list(MODULES.keys())


def get_module(module: str) -> dict[str, Any]:
    if module not in MODULES:
        raise KeyError(module)
    return MODULES[module]


def routing_for(module: str, grade: str) -> dict[str, Any]:
    return MODULES[module]["routing"][grade]


def catalogue() -> list[dict[str, Any]]:
    """Public module catalogue, safety text attached."""
    out = []
    for mod in MODULES.values():
        out.append(
            {
                "id": mod["id"],
                "label": {"en": mod["label_en"], "ar": mod["label_ar"]},
                "description": {
                    "en": mod["description_en"],
                    "ar": mod["description_ar"],
                },
                "screens": mod["screens"],
                "body_sites": mod["body_sites"],
                "routing_only": mod.get("routing_only", False),
                # "image" or "numeric" — tells a client whether to offer a
                # camera or a value-entry form.
                "input_kind": mod.get("input_kind", "image"),
                "limitations": MODULE_LIMITATIONS.get(mod["id"], []),
                "no_flag_caveat": NO_FLAG_CAVEAT.get(mod["id"]),
                "routing": {
                    grade: {**spec, "color": GRADE_STYLE[grade]["color"]}
                    for grade, spec in mod["routing"].items()
                },
            }
        )
    return out
