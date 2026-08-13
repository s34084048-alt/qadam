"""Analyte catalogue: canonical units, reference ranges and critical values.

TWO THINGS THIS FILE TAKES SERIOUSLY.

Units. Glucose 5 mmol/L and glucose 5 mg/dL are not the same patient — one is
normal and one is a medical emergency. Every value therefore arrives WITH a
unit, is converted to the canonical unit, and is rejected outright if the unit
is unrecognised. Guessing the unit is not an option.

Reference ranges. These are common adult ranges, and they are NOT universal:
every laboratory sets its own from its own assay and population. The reporting
laboratory's range always takes precedence, and the interpretation output says
so. Ranges here exist so an out-of-range value can be flagged for a human, not
so a number can be declared normal on this file's authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


class UnitError(ValueError):
    """The submitted unit is not one this analyte accepts."""


@dataclass(frozen=True, slots=True)
class Range:
    low: float | None = None
    high: float | None = None

    def flag(self, value: float) -> str:
        if self.low is not None and value < self.low:
            return "low"
        if self.high is not None and value > self.high:
            return "high"
        return "normal"


@dataclass(frozen=True, slots=True)
class Analyte:
    code: str
    name: str
    unit: str                                   # canonical
    ref: Range                                  # default / male
    ref_female: Range | None = None
    # Values at which a clinician is contacted immediately, whatever else is
    # going on. Deliberately conservative and widely quoted.
    critical_low: float | None = None
    critical_high: float | None = None
    group: str = "other"
    # unit -> factor that converts INTO the canonical unit
    conversions: dict[str, float] = field(default_factory=dict)
    note: str = ""

    def reference(self, sex: str | None) -> Range:
        if sex == "female" and self.ref_female is not None:
            return self.ref_female
        return self.ref

    def to_canonical(self, value: float, unit: str) -> float:
        cleaned = unit.strip().replace("μ", "µ").replace(" ", "")
        canonical = self.unit.replace(" ", "")
        if cleaned.lower() == canonical.lower():
            return value
        for accepted, factor in self.conversions.items():
            if cleaned.lower() == accepted.replace(" ", "").lower():
                return value * factor
        raise UnitError(
            f"{self.name} was submitted in '{unit}', which is not a unit this "
            f"analyte accepts. Use {self.unit}"
            + (f", or one of: {', '.join(self.conversions)}."
               if self.conversions else ".")
        )


ANALYTES: dict[str, Analyte] = {a.code: a for a in [
    # --- full blood count ----------------------------------------------------
    Analyte("hb", "Haemoglobin", "g/L", Range(130, 170), Range(120, 155),
            critical_low=70, critical_high=200, group="fbc",
            conversions={"g/dL": 10.0}),
    Analyte("wbc", "White cell count", "10^9/L", Range(4.0, 11.0),
            critical_low=1.0, critical_high=30.0, group="fbc",
            conversions={"10^3/uL": 1.0, "K/uL": 1.0}),
    Analyte("neut", "Neutrophils", "10^9/L", Range(2.0, 7.5),
            critical_low=0.5, group="fbc",
            note="Below 0.5 with fever is neutropenic sepsis until proven "
                 "otherwise — an emergency.",
            conversions={"10^3/uL": 1.0, "K/uL": 1.0}),
    Analyte("lymph", "Lymphocytes", "10^9/L", Range(1.0, 4.0), group="fbc",
            conversions={"10^3/uL": 1.0, "K/uL": 1.0}),
    Analyte("plt", "Platelets", "10^9/L", Range(150, 400),
            critical_low=20, critical_high=1000, group="fbc",
            conversions={"10^3/uL": 1.0, "K/uL": 1.0}),
    Analyte("mcv", "Mean cell volume", "fL", Range(80, 100), group="fbc"),

    # --- urea and electrolytes ----------------------------------------------
    Analyte("na", "Sodium", "mmol/L", Range(135, 145),
            critical_low=120, critical_high=155, group="ue",
            conversions={"mEq/L": 1.0}),
    Analyte("k", "Potassium", "mmol/L", Range(3.5, 5.3),
            critical_low=2.5, critical_high=6.5, group="ue",
            note="A potassium outside the critical range needs an ECG "
                 "immediately, and haemolysis of the sample must be excluded.",
            conversions={"mEq/L": 1.0}),
    Analyte("cl", "Chloride", "mmol/L", Range(98, 107), group="ue",
            conversions={"mEq/L": 1.0}),
    Analyte("hco3", "Bicarbonate", "mmol/L", Range(22, 29),
            critical_low=10, group="ue", conversions={"mEq/L": 1.0}),
    Analyte("urea", "Urea", "mmol/L", Range(2.5, 7.8), group="ue",
            conversions={"BUN mg/dL": 0.357}),
    Analyte("creat", "Creatinine", "umol/L", Range(60, 110), Range(45, 90),
            critical_high=400, group="ue",
            conversions={"mg/dL": 88.4}),

    # --- liver ---------------------------------------------------------------
    Analyte("bili", "Bilirubin (total)", "umol/L", Range(None, 21),
            critical_high=100, group="lft", conversions={"mg/dL": 17.1}),
    Analyte("alt", "ALT", "U/L", Range(None, 41), Range(None, 33), group="lft",
            critical_high=1000),
    Analyte("ast", "AST", "U/L", Range(None, 40), group="lft"),
    Analyte("alp", "Alkaline phosphatase", "U/L", Range(30, 130), group="lft"),
    Analyte("ggt", "GGT", "U/L", Range(None, 60), Range(None, 40), group="lft"),
    Analyte("alb", "Albumin", "g/L", Range(35, 50), group="lft",
            conversions={"g/dL": 10.0}),

    # --- metabolic and inflammatory -----------------------------------------
    Analyte("gluc", "Glucose (random)", "mmol/L", Range(3.9, 7.8),
            critical_low=2.5, critical_high=25.0, group="metabolic",
            conversions={"mg/dL": 0.0555}),
    Analyte("hba1c", "HbA1c", "mmol/mol", Range(None, 42), group="metabolic",
            note="42–47 mmol/mol is the at-risk band; 48 or above meets the "
                 "diabetes threshold on a laboratory sample, and the diagnosis "
                 "is made by a clinician, usually on two results.",
            conversions={"%": 10.929}),
    Analyte("ca", "Calcium (total)", "mmol/L", Range(2.20, 2.60),
            critical_low=1.8, critical_high=3.0, group="metabolic",
            note="Interpret the ALBUMIN-ADJUSTED value, which is computed when "
                 "albumin is supplied.",
            conversions={"mg/dL": 0.2495}),
    Analyte("crp", "C-reactive protein", "mg/L", Range(None, 5),
            group="inflammatory"),
    Analyte("inr", "INR", "ratio", Range(0.8, 1.2), critical_high=5.0,
            group="coagulation",
            note="This range applies to a patient NOT on an anticoagulant. On "
                 "warfarin the target range is set by the indication."),
    Analyte("tsh", "TSH", "mU/L", Range(0.4, 4.0), group="endocrine"),
    Analyte("ferritin", "Ferritin", "ug/L", Range(30, 400), Range(15, 200),
            group="haematinics",
            note="Ferritin is an acute-phase protein: it rises with "
                 "inflammation and can be normal despite iron deficiency."),
    Analyte("trop", "Troponin", "ng/L", Range(None, None), group="cardiac",
            note="NO REFERENCE RANGE IS APPLIED. Troponin thresholds are "
                 "specific to the assay and the laboratory, and differ between "
                 "sexes and between high-sensitivity and conventional assays. "
                 "Use the reporting laboratory's cut-off and the local chest "
                 "pain pathway."),
]}

GROUPS = {
    "fbc": "Full blood count",
    "ue": "Urea and electrolytes",
    "lft": "Liver function",
    "metabolic": "Metabolic",
    "inflammatory": "Inflammatory markers",
    "coagulation": "Coagulation",
    "endocrine": "Endocrine",
    "haematinics": "Haematinics",
    "cardiac": "Cardiac markers",
    "other": "Other",
}

REFERENCE_RANGE_CAVEAT = (
    "Reference ranges shown are common adult values and are NOT universal. "
    "Every laboratory sets its own from its own assay and population, and the "
    "reporting laboratory's range always takes precedence. A value inside "
    "these ranges has not been declared normal — it has only failed to trigger "
    "a flag."
)


def catalogue() -> list[dict]:
    out = []
    for analyte in ANALYTES.values():
        out.append({
            "code": analyte.code,
            "name": analyte.name,
            "unit": analyte.unit,
            "accepted_units": [analyte.unit, *analyte.conversions],
            "group": analyte.group,
            "group_label": GROUPS[analyte.group],
            "reference": {"low": analyte.ref.low, "high": analyte.ref.high},
            "reference_female": (
                {"low": analyte.ref_female.low, "high": analyte.ref_female.high}
                if analyte.ref_female else None
            ),
            "critical_low": analyte.critical_low,
            "critical_high": analyte.critical_high,
            "note": analyte.note,
        })
    return out
