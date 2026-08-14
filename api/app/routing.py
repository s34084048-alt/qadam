"""Where a case is routed, and what that decision is allowed to rest on.

THE IMAGE IS NOT IN THIS FUNCTION, deliberately.

The photograph used to produce the grade. It cannot. Colour thresholds tuned by
hand hit a ceiling that this project measured directly: raising the reference to
catch a wound that fills the frame brought back the false "necrotic tissue on a
healthy toe"; lowering it again brought back the silent miss. Each fix bought
one error with the other, which is the signature of a ceiling rather than a bug.
A grade from that source is a confident number with nothing behind it.

What the decision rests on instead is what a clinician measured:

    routing = the more urgent of
        the IWGDF risk category   (monofilament, pulses, deformity, history)
        the follow-up answers     (probe-to-bone, fever, spreading erythema…)

Both are rules over findings a person obtained with their hands and their eyes.
Neither is a model. Neither degrades when the light changes.

The photograph keeps its place as the RECORD: calibrated colour, area in cm²
against a card of known size, and the series over time that shows whether the
wound is closing. Percentage area reduction across four weeks is an established
prognostic indicator in wound care, and it is a measurement rather than a
judgement, which is precisely why a camera can contribute to it.

NOTHING ASSESSED IS NOT THE SAME AS NOTHING WRONG. A case with no examination
and no answers returns `not_assessed`, never `no_flag`. The absence of an
assessment is the absence of information, and reporting it as reassurance is
the failure this whole platform is built to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .analysis.modules_config import GRADE_STYLE, routing_for
from .analysis.types import Grade

NOT_ASSESSED = "not_assessed"

IMAGE_EXCLUDED = (
    "The photograph does not contribute to this routing decision. It is kept "
    "as the record — calibrated colour, area in cm², and the series over time. "
    "Routing comes from the clinical examination and the follow-up answers, "
    "because those are measurements a person made rather than inferences from "
    "pixels."
)

NOTHING_YET = (
    "Nothing has been assessed for this case yet, so there is no routing "
    "decision. This is NOT a low-risk result — no examination has been "
    "recorded and no questions answered."
)


@dataclass(slots=True)
class Routing:
    """The case's decision, and an audit of what produced it."""

    assessed: bool = False
    grade: Grade | None = None
    label: str = ""
    urgency: str = ""
    routing_target: str = ""
    next_investigation: str = ""
    basis: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "assessed": self.assessed,
            "grade": str(self.grade) if self.grade else NOT_ASSESSED,
            "label": self.label,
            "urgency": self.urgency,
            "routing_target": self.routing_target,
            "next_investigation": self.next_investigation,
            "basis": list(self.basis),
            "missing": list(self.missing),
            "derived_from_image": False,
            "image_note": IMAGE_EXCLUDED,
        }
        if self.grade:
            out["color"] = GRADE_STYLE[str(self.grade)]["color"]
        else:
            out["note"] = NOTHING_YET
        return out


def decide(
    foot_risk: dict[str, Any] | None = None,
    follow_up: dict[str, Any] | None = None,
) -> Routing:
    """Combine the examination and the answers. The image is not an input.

    `foot_risk` is the latest FootRiskAssessment payload, `follow_up` the
    latest CaseFollowUp payload. Either may be absent.
    """
    contributions: list[tuple[Grade, dict[str, Any]]] = []
    missing: list[str] = []

    if foot_risk and foot_risk.get("grade"):
        grade = Grade(foot_risk["grade"])
        contributions.append((grade, {
            "source": "iwgdf_risk_category",
            "grade": str(grade),
            "detail": (
                f"IWGDF category {foot_risk.get('category')}"
                if foot_risk.get("category") is not None
                else "Risk category not produced — a required test was not done"
            ),
            "screening_interval": foot_risk.get("screening_interval", ""),
        }))
    else:
        missing.append(
            "No foot examination recorded. The IWGDF category — from the "
            "monofilament and the pulses — is what sets the surveillance "
            "interval, and it cannot be inferred from anything else here."
        )

    if follow_up and follow_up.get("answer_grade"):
        grade = Grade(follow_up["answer_grade"])
        contributions.append((grade, {
            "source": "follow_up_answers",
            "grade": str(grade),
            "detail": (
                f"{len(follow_up.get('triggers', []))} red flag(s) from the "
                "clinician's answers"
            ),
            "triggers": [t.get("finding") for t in follow_up.get("triggers", [])],
        }))
    else:
        missing.append(
            "No follow-up answers recorded. Probe-to-bone, fever and spreading "
            "erythema decide this case and none of them is visible in a "
            "photograph."
        )

    if not contributions:
        return Routing(assessed=False, missing=missing)

    grade = max((g for g, _ in contributions), key=lambda g: g.rank)
    spec = routing_for("foot", str(grade))
    return Routing(
        assessed=True,
        grade=grade,
        label=spec["label"],
        urgency=spec["urgency"],
        routing_target=spec["routing_target"],
        next_investigation=spec["next_investigation"],
        basis=[detail for _g, detail in contributions],
        missing=missing,
    )
