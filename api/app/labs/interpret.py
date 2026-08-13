"""Lab panel interpretation.

Flags values against reference ranges, computes standard derived indices, and
produces the SAME structured output shape as the image modules: a triage grade,
a routed next investigation, and a differential list where every entry names
the test that separates the possibilities.

THE BOUNDARY IS UNCHANGED. A flagged result is a flag, not a diagnosis, and no
treatment is ever suggested. Where a result demands immediate action, that
action is an INVESTIGATION (an ECG, a repeat sample, a clinician review) —
never a drug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..analysis.clinical import ClinicalContext, Consideration
from ..analysis.modules_config import routing_for
from ..analysis.types import Grade, Triage
from .catalog import ANALYTES, GROUPS, REFERENCE_RANGE_CAVEAT, UnitError


@dataclass(slots=True)
class ResultValue:
    code: str
    name: str
    value: float
    unit: str
    submitted_value: float
    submitted_unit: str
    flag: str                      # normal | low | high
    critical: bool
    reference: dict[str, float | None]
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "value": round(self.value, 4),
            "unit": self.unit,
            "submitted": {"value": self.submitted_value,
                          "unit": self.submitted_unit},
            "converted": self.submitted_unit.strip() != self.unit,
            "flag": self.flag,
            "critical": self.critical,
            "reference": self.reference,
            "note": self.note,
        }


@dataclass(slots=True)
class LabInterpretation:
    results: list[ResultValue]
    derived: list[dict[str, Any]]
    triage: Triage
    clinical: ClinicalContext
    unrecognised: list[dict[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "results": [r.to_json() for r in self.results],
            "derived": self.derived,
            "triage": self.triage.to_json(),
            "clinical": self.clinical.to_json(),
            "unrecognised": self.unrecognised,
            "reference_range_caveat": REFERENCE_RANGE_CAVEAT,
        }


# --- derived indices ---------------------------------------------------------

def _egfr(creat_umol: float, age: int, sex: str | None) -> dict[str, Any] | None:
    """CKD-EPI 2021 creatinine equation — the race-free revision."""
    if not age or age < 18:
        return None
    scr = creat_umol / 88.4                      # mg/dL
    female = sex == "female"
    kappa = 0.7 if female else 0.9
    alpha = -0.241 if female else -0.302
    value = (142.0
             * min(scr / kappa, 1.0) ** alpha
             * max(scr / kappa, 1.0) ** -1.200
             * 0.9938 ** age
             * (1.012 if female else 1.0))
    if value >= 90:
        stage = "G1 (≥90) — normal or high, only CKD if other evidence"
    elif value >= 60:
        stage = "G2 (60–89) — mildly reduced, only CKD if other evidence"
    elif value >= 45:
        stage = "G3a (45–59) — mild to moderate reduction"
    elif value >= 30:
        stage = "G3b (30–44) — moderate to severe reduction"
    elif value >= 15:
        stage = "G4 (15–29) — severe reduction"
    else:
        stage = "G5 (<15) — kidney failure"
    return {
        "code": "egfr",
        "name": "eGFR (CKD-EPI 2021)",
        "value": round(value, 1),
        "unit": "mL/min/1.73m²",
        "interpretation": stage,
        "caveat": "A single eGFR cannot distinguish acute kidney injury from "
                  "chronic kidney disease — that needs previous results and "
                  "the clinical picture. It is unreliable in acute illness, at "
                  "extremes of muscle mass, and in pregnancy. CKD staging also "
                  "requires albuminuria and a result sustained over 3 months.",
    }


def _anion_gap(na: float, cl: float, hco3: float) -> dict[str, Any]:
    gap = na - (cl + hco3)
    return {
        "code": "anion_gap",
        "name": "Anion gap",
        "value": round(gap, 1),
        "unit": "mmol/L",
        "interpretation": ("raised" if gap > 16 else
                           "low" if gap < 8 else "within the usual range"),
        "caveat": "Calculated without potassium (usual range roughly 8–16). "
                  "A raised gap should be corrected for albumin, which lowers "
                  "it by about 2.5 mmol/L for every 10 g/L that albumin falls.",
    }


def _adjusted_calcium(ca: float, alb: float) -> dict[str, Any]:
    adjusted = ca + 0.02 * (40.0 - alb)
    return {
        "code": "ca_adjusted",
        "name": "Albumin-adjusted calcium",
        "value": round(adjusted, 2),
        "unit": "mmol/L",
        "interpretation": ("high" if adjusted > 2.60 else
                           "low" if adjusted < 2.20 else
                           "within the usual range"),
        "caveat": "The adjustment is an approximation and is unreliable in "
                  "critical illness. Ionised calcium is the definitive "
                  "measurement.",
    }


def _nlr(neut: float, lymph: float) -> dict[str, Any] | None:
    if lymph <= 0:
        return None
    ratio = neut / lymph
    return {
        "code": "nlr",
        "name": "Neutrophil-to-lymphocyte ratio",
        "value": round(ratio, 2),
        "unit": "ratio",
        "interpretation": ("markedly raised" if ratio >= 9 else
                           "raised" if ratio >= 4 else "unremarkable"),
        "caveat": "A non-specific marker of physiological stress. It rises in "
                  "infection, inflammation, trauma, malignancy and with "
                  "corticosteroids, and on its own it points nowhere.",
    }


def _fib4(age: int, ast: float, alt: float, plt: float) -> dict[str, Any] | None:
    if not age or alt <= 0 or plt <= 0:
        return None
    value = (age * ast) / (plt * (alt ** 0.5))
    return {
        "code": "fib4",
        "name": "FIB-4 index",
        "value": round(value, 2),
        "unit": "index",
        "interpretation": ("above the upper cut-off — advanced fibrosis not "
                           "excluded, specialist assessment indicated"
                           if value > 3.25 else
                           "indeterminate zone" if value >= 1.30 else
                           "below the lower cut-off — advanced fibrosis "
                           "unlikely"),
        "caveat": "A screening index for advanced liver fibrosis, validated in "
                  "adults aged 35–65 and unreliable outside that range. It is "
                  "not a measure of liver function and does not replace "
                  "elastography or biopsy.",
    }


def _urea_creat_ratio(urea: float, creat_umol: float) -> dict[str, Any] | None:
    if creat_umol <= 0:
        return None
    ratio = (urea * 1000.0) / creat_umol
    return {
        "code": "urea_creat_ratio",
        "name": "Urea:creatinine ratio",
        "value": round(ratio, 1),
        "unit": "ratio (mmol/L : mmol/L)",
        "interpretation": ("raised — seen in hypovolaemia, upper "
                           "gastrointestinal bleeding, high protein load and "
                           "corticosteroids" if ratio > 100 else
                           "unremarkable"),
        "caveat": "Suggestive only. Volume status is assessed clinically.",
    }


# --- interpretation ----------------------------------------------------------

def interpret(
    submitted: list[dict[str, Any]],
    *,
    age: int | None = None,
    sex: str | None = None,
) -> LabInterpretation:
    results: list[ResultValue] = []
    unrecognised: list[dict[str, str]] = []
    by_code: dict[str, float] = {}

    for item in submitted:
        code = str(item.get("code", "")).strip().lower()
        analyte = ANALYTES.get(code)
        if analyte is None:
            unrecognised.append({
                "code": code,
                "reason": "Not in the analyte catalogue. It is stored with the "
                          "panel but is not interpreted.",
            })
            continue
        raw = float(item["value"])
        unit = str(item.get("unit", analyte.unit))
        value = analyte.to_canonical(raw, unit)   # raises UnitError

        reference = analyte.reference(sex)
        flag = reference.flag(value)
        critical = bool(
            (analyte.critical_low is not None and value <= analyte.critical_low)
            or (analyte.critical_high is not None and value >= analyte.critical_high)
        )
        results.append(ResultValue(
            code=code, name=analyte.name, value=value, unit=analyte.unit,
            submitted_value=raw, submitted_unit=unit, flag=flag,
            critical=critical,
            reference={"low": reference.low, "high": reference.high},
            note=analyte.note,
        ))
        by_code[code] = value

    derived: list[dict[str, Any]] = []
    if "creat" in by_code and age:
        egfr = _egfr(by_code["creat"], age, sex)
        if egfr:
            derived.append(egfr)
    if {"na", "cl", "hco3"} <= by_code.keys():
        derived.append(_anion_gap(by_code["na"], by_code["cl"], by_code["hco3"]))
    if {"ca", "alb"} <= by_code.keys():
        derived.append(_adjusted_calcium(by_code["ca"], by_code["alb"]))
    if {"neut", "lymph"} <= by_code.keys():
        nlr = _nlr(by_code["neut"], by_code["lymph"])
        if nlr:
            derived.append(nlr)
    if {"ast", "alt", "plt"} <= by_code.keys() and age:
        fib4 = _fib4(age, by_code["ast"], by_code["alt"], by_code["plt"])
        if fib4:
            derived.append(fib4)
    if {"urea", "creat"} <= by_code.keys():
        ratio = _urea_creat_ratio(by_code["urea"], by_code["creat"])
        if ratio:
            derived.append(ratio)

    grade, rationale = _grade(results, derived)
    clinical = _clinical(results, derived, by_code, grade, sex)
    spec = routing_for("lab", str(grade))
    triage = Triage(
        grade=grade,
        label=spec["label"],
        confidence=1.0,   # arithmetic against a range, not a model prediction
        rationale=rationale,
        next_investigation=spec["next_investigation"],
        urgency=spec["urgency"],
        routing_target=spec["routing_target"],
    )
    return LabInterpretation(results=results, derived=derived, triage=triage,
                             clinical=clinical, unrecognised=unrecognised)


def _grade(results: list[ResultValue],
           derived: list[dict[str, Any]]) -> tuple[Grade, list[str]]:
    critical = [r for r in results if r.critical]
    abnormal = [r for r in results if r.flag != "normal" and not r.critical]
    rationale: list[str] = []

    if critical:
        rationale.append(
            "CRITICAL VALUE: "
            + "; ".join(f"{r.name} {r.value:g} {r.unit}" for r in critical)
            + ". Contact a clinician now and confirm the sample is valid."
        )
        grade = Grade.URGENT
    elif len(abnormal) >= 3:
        rationale.append(
            f"{len(abnormal)} results outside the reference range: "
            + ", ".join(r.name for r in abnormal) + "."
        )
        grade = Grade.REVIEW
    elif abnormal:
        rationale.append(
            "Outside the reference range: "
            + ", ".join(f"{r.name} ({r.flag})" for r in abnormal) + "."
        )
        grade = Grade.MONITOR
    else:
        rationale.append("No result fell outside the reference ranges applied.")
        grade = Grade.NO_FLAG

    egfr = next((d for d in derived if d["code"] == "egfr"), None)
    if egfr and egfr["value"] < 30 and grade.rank < Grade.REVIEW.rank:
        grade = Grade.REVIEW
        rationale.append(f"eGFR {egfr['value']} mL/min/1.73m² — {egfr['interpretation']}.")

    rationale.append(REFERENCE_RANGE_CAVEAT)
    rationale.append(
        "Numbers are interpreted here; the patient is not. A result is read "
        "against the clinical picture by a clinician."
    )
    return grade, rationale


def _clinical(results: list[ResultValue], derived: list[dict[str, Any]],
              by: dict[str, float], grade: Grade,
              sex: str | None) -> ClinicalContext:
    flags = {r.code: r.flag for r in results}
    ctx = ClinicalContext(
        severity_index={
            "name": "Results outside reference range",
            "value": sum(1 for r in results if r.flag != "normal"),
            "unit": f"of {len(results)} interpreted",
            "band": ("critical value present" if any(r.critical for r in results)
                     else "none" if all(r.flag == "normal" for r in results)
                     else "abnormalities present"),
            "components": {
                "critical": [r.name for r in results if r.critical],
                "out_of_range": [r.name for r in results if r.flag != "normal"],
            },
            "caveat": "A count of flags, not a severity score. One deranged "
                      "potassium outweighs five trivially abnormal results.",
        },
        scales={
            "derived_indices": {d["code"]: d for d in derived},
            "reference_ranges": REFERENCE_RANGE_CAVEAT,
        },
        ask_and_check=[
            "Was the sample taken and handled correctly? Haemolysis raises "
            "potassium, a drip-arm sample dilutes everything, and a delayed "
            "sample lowers glucose. Repeat before acting on a surprise.",
            "Are there previous results? A creatinine of 180 that was 175 last "
            "year means something entirely different from one that was 80 last "
            "week.",
            "What medicines is the patient taking, including over-the-counter "
            "and herbal ones?",
            "Was the patient fasting, and when was the sample taken?",
            "How is the patient clinically? Observations, hydration, and "
            "whether they look unwell.",
            "Is the patient pregnant? Many reference ranges shift in pregnancy.",
        ],
        not_assessable=[
            "Whether the abnormality is acute or long-standing, without "
            "previous results.",
            "Whether the sample was valid — haemolysis, contamination and "
            "delay are not visible in the number.",
            "The clinical significance of any result on its own, apart from "
            "the patient.",
            "Anything not measured. A normal panel does not exclude disease.",
        ],
    )

    hb_low = flags.get("hb") == "low"
    if hb_low and "mcv" in by:
        mcv = by["mcv"]
        if mcv < 80:
            ctx.considerations.append(Consideration(
                pattern="Anaemia with a low mean cell volume (microcytic)",
                overlaps_with=[
                    "iron deficiency — and then the cause of the iron loss",
                    "thalassaemia trait or another haemoglobinopathy",
                    "anaemia of chronic disease",
                    "sideroblastic anaemia or lead exposure",
                ],
                distinguished_by="Ferritin with iron studies, haemoglobin "
                                 "electrophoresis, and a blood film. In an "
                                 "adult, iron deficiency is a symptom — the "
                                 "source of blood loss must be found.",
            ))
        elif mcv > 100:
            ctx.considerations.append(Consideration(
                pattern="Anaemia with a raised mean cell volume (macrocytic)",
                overlaps_with=[
                    "B12 or folate deficiency",
                    "alcohol excess or liver disease",
                    "hypothyroidism",
                    "myelodysplasia",
                    "drugs — methotrexate, hydroxycarbamide, antiretrovirals",
                    "reticulocytosis from haemolysis or recent bleeding",
                ],
                distinguished_by="B12 and folate, TSH, a blood film, "
                                 "reticulocyte count, and a medication review.",
            ))
        else:
            ctx.considerations.append(Consideration(
                pattern="Anaemia with a normal mean cell volume (normocytic)",
                overlaps_with=[
                    "acute blood loss",
                    "anaemia of chronic disease",
                    "chronic kidney disease",
                    "haemolysis",
                    "bone marrow failure or infiltration",
                    "a mixed deficiency, where the indices cancel out",
                ],
                distinguished_by="Reticulocyte count, blood film, renal "
                                 "function, haptoglobin, LDH and bilirubin, "
                                 "and iron studies.",
            ))
    elif hb_low:
        ctx.considerations.append(Consideration(
            pattern="Anaemia, with no mean cell volume supplied",
            overlaps_with=["iron deficiency", "anaemia of chronic disease",
                           "B12 or folate deficiency", "blood loss",
                           "haemolysis", "renal anaemia"],
            distinguished_by="The MCV is the first branch point — request a "
                             "full blood count with indices, plus a blood film "
                             "and haematinics.",
        ))

    alt_high = flags.get("alt") == "high"
    alp_high = flags.get("alp") == "high"
    if alt_high and not alp_high:
        ctx.considerations.append(Consideration(
            pattern="Hepatocellular pattern — transaminases raised out of "
                    "proportion to alkaline phosphatase",
            overlaps_with=[
                "viral hepatitis",
                "drug-induced or alcohol-related liver injury",
                "metabolic dysfunction-associated fatty liver disease",
                "autoimmune hepatitis",
                "ischaemic hepatitis in a shocked patient",
                "coeliac disease or thyroid disease, which can raise ALT",
            ],
            distinguished_by="Viral hepatitis serology, an autoimmune screen, "
                             "a full medication and alcohol history, liver "
                             "ultrasound, and repeat testing. Synthetic "
                             "function — INR, albumin, bilirubin — matters "
                             "more than the height of the ALT.",
        ))
    elif alp_high and not alt_high:
        ctx.considerations.append(Consideration(
            pattern="Cholestatic pattern — alkaline phosphatase raised out of "
                    "proportion to transaminases",
            overlaps_with=[
                "biliary obstruction, including stones and tumour",
                "drug-induced cholestasis",
                "primary biliary cholangitis or sclerosing cholangitis",
                "infiltrative liver disease",
                "a BONE source rather than a liver one — Paget's disease, "
                "metastases, healing fracture, vitamin D deficiency",
                "pregnancy or normal adolescent growth",
            ],
            distinguished_by="GGT separates a liver source from a bone source: "
                             "a raised GGT points to the liver. Then liver "
                             "ultrasound, and calcium, phosphate and vitamin D "
                             "if bone is suspected.",
        ))

    if flags.get("k") in ("high", "low"):
        direction = flags["k"]
        ctx.considerations.append(Consideration(
            pattern=f"Potassium is {direction}",
            overlaps_with=(
                ["a haemolysed or delayed sample — the commonest cause of a "
                 "surprise high potassium",
                 "acute kidney injury or chronic kidney disease",
                 "drugs — ACE inhibitors, ARBs, spironolactone, NSAIDs, "
                 "trimethoprim",
                 "adrenal insufficiency",
                 "tissue breakdown — rhabdomyolysis, tumour lysis, burns",
                 "acidosis shifting potassium out of cells"]
                if direction == "high" else
                ["gastrointestinal loss — vomiting or diarrhoea",
                 "diuretics or other renal loss",
                 "poor intake",
                 "shift into cells — insulin, salbutamol, alkalosis",
                 "hyperaldosteronism",
                 "magnesium depletion, which makes potassium impossible to "
                 "correct until it is treated"]
            ),
            distinguished_by="A repeat sample taken cleanly and processed "
                             "promptly, an ECG, renal function, magnesium, and "
                             "a medication review. Where the cause is not "
                             "obvious, paired urine and serum electrolytes.",
        ))

    if flags.get("na") in ("high", "low"):
        low = flags["na"] == "low"
        ctx.considerations.append(Consideration(
            pattern=f"Sodium is {'low' if low else 'high'}",
            overlaps_with=(
                ["hypovolaemia — gastrointestinal or renal loss",
                 "SIADH",
                 "heart failure, liver failure or nephrotic syndrome",
                 "thiazide diuretics",
                 "hypothyroidism or adrenal insufficiency",
                 "pseudohyponatraemia from very high lipids or protein"]
                if low else
                ["water deficit — poor intake, especially in an older or "
                 "dependent patient",
                 "gastrointestinal or renal water loss",
                 "diabetes insipidus",
                 "osmotic diuresis from uncontrolled diabetes"]
            ),
            distinguished_by="Clinical assessment of volume status first, then "
                             "paired serum and urine osmolality with urine "
                             "sodium. Thyroid function and a short synacthen "
                             "test where indicated. How FAST the sodium "
                             "changed matters more than the number.",
        ))

    egfr = next((d for d in derived if d["code"] == "egfr"), None)
    if egfr and egfr["value"] < 60:
        ctx.considerations.append(Consideration(
            pattern=f"Reduced eGFR ({egfr['value']} mL/min/1.73m²)",
            overlaps_with=[
                "acute kidney injury — pre-renal, renal or post-renal",
                "chronic kidney disease",
                "acute-on-chronic kidney disease",
                "a spuriously low eGFR from high muscle mass, a recent meat "
                "meal, or creatinine-raising drugs that do not affect true "
                "filtration",
            ],
            distinguished_by="PREVIOUS creatinine results — this is the single "
                             "most useful thing and no equation replaces it. "
                             "Then urinalysis, urine albumin:creatinine ratio, "
                             "renal ultrasound to exclude obstruction, and a "
                             "medication review.",
        ))

    if flags.get("crp") == "high" or flags.get("wbc") in ("high", "low"):
        ctx.considerations.append(Consideration(
            pattern="Raised inflammatory markers",
            overlaps_with=[
                "bacterial or viral infection",
                "inflammatory or autoimmune disease",
                "tissue injury, surgery or infarction",
                "malignancy",
                "a normal post-operative or post-partum response",
            ],
            distinguished_by="The clinical picture, cultures taken BEFORE any "
                             "treatment, imaging directed at the suspected "
                             "site, and the trend on repeat testing. CRP tells "
                             "you inflammation is present, never where or why.",
        ))

    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No interpretable pattern in the results supplied",
            overlaps_with=[
                "genuinely unremarkable results",
                "disease that this panel does not measure",
                "an early or intermittent abnormality",
            ],
            distinguished_by="The clinical question that prompted the test. A "
                             "normal panel answers only what was asked.",
        ))

    if grade is Grade.URGENT:
        ctx.immediate_actions = [
            "Contact a clinician now with the result, and do not wait for the "
            "next appointment.",
            "Confirm the sample: was it haemolysed, taken from a drip arm, or "
            "delayed in transit? Repeat urgently if in any doubt.",
            "If potassium, calcium or glucose is critical, obtain an ECG and "
            "record observations while you contact the clinician.",
            "Do not start, stop or change any medicine on the basis of this "
            "result — that decision belongs to the clinician.",
        ]
    elif grade in (Grade.REVIEW, Grade.MONITOR):
        ctx.immediate_actions = [
            "Book the review and make sure the result reaches the clinician "
            "responsible for the patient.",
            "Retrieve previous results for comparison before the appointment.",
            "Record current observations and a medication list with the panel.",
            "Do not change any medicine on the basis of this result.",
        ]
    else:
        ctx.immediate_actions = [
            "File the result with the case and make sure the requesting "
            "clinician sees it.",
            "A normal panel does not close the clinical question that prompted "
            "it.",
        ]
    return ctx


__all__ = ["interpret", "LabInterpretation", "ResultValue", "UnitError",
           "GROUPS"]
