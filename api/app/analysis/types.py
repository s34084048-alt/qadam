from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SubjectMismatch(ValueError):
    """The image does not contain what this module needs.

    Raised BEFORE any measurement. Without it a module happily measures
    whatever it is given: a photograph of a foot sent to the eye module scored
    the warm tone of skin as scleral yellowing and answered "urgent - same-day
    medical review" at 0.85 confidence. Confident output from an input the
    module cannot interpret is the worst failure this platform can produce.
    """

    def __init__(self, module: str, reason: str, hint: str) -> None:
        super().__init__(reason)
        self.module = module
        self.reason = reason
        self.hint = hint


class Grade(StrEnum):
    """Triage grades, ordered least to most urgent."""

    NO_FLAG = "no_flag"
    MONITOR = "monitor"
    REVIEW = "review"
    URGENT = "urgent"

    @property
    def rank(self) -> int:
        return {"no_flag": 0, "monitor": 1, "review": 2, "urgent": 3}[self.value]


@dataclass(slots=True)
class Lesion:
    """A typed SURFACE finding. `kind` names what is visible on the skin or
    anterior eye -- never an internal structure or a diagnosis."""

    kind: str
    area_pct: float          # % of the detected subject region
    severity: float          # 0..1, how pronounced the visible feature is
    bbox: tuple[int, int, int, int]     # x, y, w, h in image pixels
    centroid: tuple[int, int]
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "area_pct": round(self.area_pct, 3),
            "severity": round(self.severity, 3),
            "bbox": {
                "x": self.bbox[0], "y": self.bbox[1],
                "w": self.bbox[2], "h": self.bbox[3],
            },
            "centroid": {"x": self.centroid[0], "y": self.centroid[1]},
            "description": self.description,
        }


@dataclass(slots=True)
class Triage:
    grade: Grade
    label: str
    confidence: float
    rationale: list[str] = field(default_factory=list)
    next_investigation: str = ""
    urgency: str = ""            # human-readable timeframe
    routing_target: str = ""     # who/where the patient goes
    # Every cap and penalty applied to `confidence` by analysis.prerequisites,
    # in the order applied. The number alone cannot say why it is what it is,
    # and a reader who is not shown the reason has to take it on trust.
    # Carried as a value on the result, never as state on the backend.
    confidence_adjustments: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "grade": str(self.grade),
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "rationale": list(self.rationale),
            "next_investigation": self.next_investigation,
            "urgency": self.urgency,
            "routing_target": self.routing_target,
            "confidence_adjustments": list(self.confidence_adjustments),
        }


@dataclass(slots=True)
class ModuleResult:
    lesions: list[Lesion]
    triage: Triage
    features: dict[str, Any] = field(default_factory=dict)
    model_version: str = "unknown"
    backend: str = "unknown"
    # Differential prompts, protective actions and what to examine. Attached by
    # the pipeline, so every backend -- including a trained one -- gets it.
    clinical: dict[str, Any] | None = None


@dataclass(slots=True)
class QualityCheck:
    name: str
    passed: bool
    value: float
    threshold: float
    hint: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": round(float(self.value), 3),
            "threshold": round(float(self.threshold), 3),
            "hint": self.hint,
        }


@dataclass(slots=True)
class QualityReport:
    passed: bool
    checks: list[QualityCheck]
    width: int
    height: int
    subject_fraction: float
    focus_var: float
    exposure_mean: float
    confidence_factor: float   # 0..1, multiplied into analysis confidence
    mask: Any = None           # np.ndarray subject mask; never serialized

    @property
    def failures(self) -> list[QualityCheck]:
        return [c for c in self.checks if not c.passed]

    def to_json(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "width": self.width,
            "height": self.height,
            "subject_fraction": round(self.subject_fraction, 4),
            "focus_var": round(self.focus_var, 2),
            "exposure_mean": round(self.exposure_mean, 2),
            "confidence_factor": round(self.confidence_factor, 3),
            "checks": [c.to_json() for c in self.checks],
            "hints": [c.hint for c in self.checks if not c.passed],
        }
