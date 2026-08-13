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
    "skin": {
        "id": "skin",
        "label_en": "Skin lesion",
        "label_ar": "آفة جلدية",
        "description_en": (
            "Screens a photographed skin lesion for pigment irregularity, "
            "border irregularity, colour variation and inflammation, and routes "
            "concerning lesions to dermatology."
        ),
        "description_ar": (
            "فحص آفة جلدية مصوّرة بحثاً عن عدم انتظام الصبغة والحدود وتنوع "
            "الألوان والالتهاب، وتوجيه الآفات المقلقة إلى الأمراض الجلدية."
        ),
        "screens": [
            "pigment irregularity",
            "border irregularity",
            "colour variation",
            "inflammation / erythema",
        ],
        "body_sites": ["head/neck", "trunk", "upper limb", "lower limb", "hand", "foot"],
        "routing": {
            "no_flag": {
                "label": "No flag on this image",
                "routing_target": "Routine skin self-check",
                "next_investigation": (
                    "No referral triggered by this image. Advise the patient to "
                    "re-present if the lesion changes in size, shape, colour, or "
                    "if it bleeds or itches."
                ),
                "urgency": "Routine",
            },
            "monitor": {
                "label": "Monitor — re-image",
                "routing_target": "Same clinician, planned review",
                "next_investigation": (
                    "Re-image in 4–8 weeks with a size marker in frame and "
                    "compare. Refer earlier if the lesion changes."
                ),
                "urgency": "4–8 weeks",
            },
            "review": {
                "label": "Dermatology review",
                "routing_target": "Dermatology / teledermatology",
                "next_investigation": (
                    "Refer for dermatology or teledermatology review with "
                    "dermoscopy. Only dermoscopic assessment and, where "
                    "indicated, biopsy with histopathology can characterise this "
                    "lesion."
                ),
                "urgency": "Within 2–4 weeks",
            },
            "urgent": {
                "label": "Urgent dermatology referral",
                "routing_target": "Urgent dermatology pathway",
                "next_investigation": (
                    "Refer on the urgent (suspected-cancer) dermatology pathway "
                    "for dermoscopy and consideration of excision biopsy. "
                    "Histopathology is the only test that can determine what "
                    "this lesion is."
                ),
                "urgency": "Within 2 weeks",
            },
        },
    },
    "eye": {
        "id": "eye",
        "label_en": "Eye — anterior surface",
        "label_ar": "العين — السطح الأمامي",
        "description_en": (
            "Screens the anterior ocular surface for redness and scleral or "
            "skin yellowing (possible jaundice). Does NOT assess the retina."
        ),
        "description_ar": (
            "فحص سطح العين الأمامي بحثاً عن احمرار أو اصفرار الصلبة أو الجلد "
            "(يرقان محتمل). لا يقيّم الشبكية."
        ),
        "screens": [
            "ocular redness",
            "scleral yellowing (possible jaundice)",
            "periocular skin yellowing",
        ],
        "body_sites": ["right eye", "left eye"],
        "routing": {
            "no_flag": {
                "label": "No anterior-surface flag",
                "routing_target": "Routine care",
                "next_investigation": (
                    "No investigation triggered by this image. Retinal screening "
                    "remains due on its own schedule and requires a fundus "
                    "camera or slit-lamp examination."
                ),
                "urgency": "Routine",
            },
            "monitor": {
                "label": "Monitor — re-image",
                "routing_target": "Same clinician, planned review",
                "next_investigation": (
                    "Re-image in 24–48 hours. Seek same-day review if pain, "
                    "photophobia, discharge or any change in vision develops."
                ),
                "urgency": "24–48 hours",
            },
            "review": {
                "label": "Eye review",
                "routing_target": "Optometry / ophthalmology",
                "next_investigation": (
                    "Arrange optometry or ophthalmology review with slit-lamp "
                    "examination and visual acuity within one week."
                ),
                "urgency": "Within 1 week",
            },
            "urgent": {
                "label": "Urgent — same-day medical review",
                "routing_target": "Same-day medical review",
                "next_investigation": (
                    "Arrange same-day medical review. If yellowing is confirmed "
                    "clinically, expect liver function tests including bilirubin "
                    "(conjugated and unconjugated), FBC and a liver ultrasound "
                    "as directed by the clinician. A photograph cannot confirm "
                    "jaundice or its cause."
                ),
                "urgency": "Same day",
            },
        },
    },
    "face": {
        "id": "face",
        "label_en": "Face — colour screening",
        "label_ar": "الوجه — فحص اللون",
        "description_en": (
            "Screens facial colour for pallor, blue discolouration of the lips "
            "(possible central cyanosis) and yellowing (possible jaundice). "
            "Colour is compared BETWEEN facial regions, because absolute "
            "colour in a photograph is dominated by lighting and white balance."
        ),
        "description_ar": (
            "فحص لون الوجه بحثاً عن شحوب أو ازرقاق الشفتين (زرقة مركزية "
            "محتملة) أو اصفرار (يرقان محتمل). تُقارن الألوان بين مناطق الوجه، "
            "لأن اللون المطلق في الصورة تحكمه الإضاءة وموازنة البياض."
        ),
        "screens": [
            "blue discolouration of the lips (possible central cyanosis)",
            "yellowing of sclera and skin (possible jaundice)",
            "pallor of the lips relative to the face",
            "facial flushing / plethora",
        ],
        "body_sites": ["face — front, even lighting"],
        "routing": {
            "no_flag": {
                "label": "No colour flag on this image",
                "routing_target": "Routine care",
                "next_investigation": (
                    "No investigation triggered by this image. If the patient "
                    "is breathless, drowsy or unwell, measure SpO₂ and vital "
                    "signs regardless — facial colour in a photograph is not a "
                    "substitute for observations."
                ),
                "urgency": "Routine",
            },
            "monitor": {
                "label": "Monitor — recheck",
                "routing_target": "Same clinician, planned review",
                "next_investigation": (
                    "Record vital signs including SpO₂, and re-image in even, "
                    "indirect daylight for comparison. Escalate if the patient "
                    "becomes breathless, confused or unwell."
                ),
                "urgency": "24–48 hours",
            },
            "review": {
                "label": "Clinician review",
                "routing_target": "Clinician assessment with bedside tests",
                "next_investigation": (
                    "Arrange clinician review within one week with vital signs, "
                    "SpO₂, and a full blood count. Assess conjunctivae, palms "
                    "and nail beds directly — pallor is judged there, not from "
                    "a photograph."
                ),
                "urgency": "Within 1 week",
            },
            "urgent": {
                "label": "Urgent — measure SpO₂ and review today",
                "routing_target": "Same-day medical review",
                "next_investigation": (
                    "MEASURE SpO₂ WITH A PULSE OXIMETER NOW, and record "
                    "respiratory rate, heart rate and level of consciousness. "
                    "Arrange same-day medical review. If yellowing is confirmed "
                    "clinically, expect liver function tests including "
                    "bilirubin, FBC and liver ultrasound as directed. A "
                    "photograph cannot measure oxygen saturation or bilirubin."
                ),
                "urgency": "Immediately / same day",
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
    "injury": {
        "id": "injury",
        "label_en": "Injury — red-flag routing",
        "label_ar": "إصابة — توجيه العلامات الحمراء",
        "description_en": (
            "ROUTING ONLY. Detects external red flags — bruising, asymmetric "
            "swelling, visible deformity — and tells you which imaging or "
            "clinician to go to. It cannot confirm or exclude internal injury."
        ),
        "description_ar": (
            "توجيه فقط. يكتشف العلامات الخارجية — كدمات، تورم غير متماثل، "
            "تشوه ظاهر — ويحدد التصوير أو الطبيب المطلوب. لا يمكنه تأكيد أو "
            "استبعاد الإصابة الداخلية."
        ),
        "screens": [
            "bruising / discolouration",
            "asymmetric swelling",
            "visible contour deformity",
        ],
        "body_sites": [
            "shoulder", "elbow", "wrist", "hand", "hip", "knee", "ankle", "foot",
        ],
        "routing_only": True,
        "routing": {
            "no_flag": {
                "label": "No external red flag",
                "routing_target": "Clinician judgement",
                "next_investigation": (
                    "No external red flag was detected. THIS DOES NOT EXCLUDE "
                    "INTERNAL INJURY. If the mechanism of injury, pain, or loss "
                    "of function suggests injury, obtain imaging (X-ray or "
                    "ultrasound) and clinical assessment regardless of this "
                    "result."
                ),
                "urgency": "Clinician judgement",
            },
            "monitor": {
                "label": "Monitor — re-assess",
                "routing_target": "Clinician review if not settling",
                "next_investigation": (
                    "Re-assess and re-image in 24–48 hours. Obtain X-ray or "
                    "ultrasound and clinician review now if there is inability "
                    "to weight-bear or use the limb, worsening pain, numbness, "
                    "or the limb is cold or pale."
                ),
                "urgency": "24–48 hours",
            },
            "review": {
                "label": "Imaging + clinician review",
                "routing_target": "X-ray / ultrasound and clinician",
                "next_investigation": (
                    "Obtain plain X-ray of the affected region, and ultrasound "
                    "if soft-tissue injury is suspected, with clinician "
                    "assessment. Imaging — not this photograph — establishes "
                    "whether a fracture, dislocation or soft-tissue rupture is "
                    "present."
                ),
                "urgency": "Same day",
            },
            "urgent": {
                "label": "Urgent — imaging and clinician now",
                "routing_target": "Emergency department / urgent imaging",
                "next_investigation": (
                    "Send for urgent clinical assessment with immediate plain "
                    "X-ray (and further imaging as directed). Check distal "
                    "neurovascular status. Only imaging and examination can "
                    "establish what the underlying injury is."
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
