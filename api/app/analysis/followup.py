"""Structured follow-up: the answers a camera cannot photograph.

The clinical layer already tells the clinician what to ask and examine
(`ask_and_check`). Until now those prompts went nowhere -- they were printed and
forgotten. This module makes them answerable, stores the answers, and lets the
answers change the routing.

That last part is the whole point. A photograph of a diabetic foot cannot see an
absent pulse, a positive probe-to-bone, a fever, or a wound that has been open
for three months. Those findings dominate the decision, and every one of them
comes from the clinician, not the camera.

THE COMBINATION RULE, and why it only goes one way
--------------------------------------------------
    final grade = max(image grade, answer grade)

Answers can RAISE urgency. They can never lower it.

The tempting behaviour is symmetry: if the clinician reports palpable pulses,
intact sensation and no fever, de-escalate the image's "urgent" to "monitor".
That would be wrong here for a reason specific to this product. The image grade
is produced from a measurement; the answers are free-form self-report, entered
by whoever is holding the phone, with no verification that the monofilament test
was performed correctly or at all. Letting unverified reassurance overwrite a
measured flag creates a one-click path to dismissing a finding -- which is
precisely the failure mode the safety boundary exists to prevent. Escalation has
no such asymmetry: a false escalation costs an unnecessary referral, a false
de-escalation costs a foot.

Reassuring answers are still recorded, still displayed, and still narrow the
differential. They just do not lower the flag.

BOUNDARY UNCHANGED. Nothing here diagnoses. An escalation produces a routing
grade and a differential prompt -- never a named condition asserted as fact, and
never a treatment or a medication. See test_safety_boundary.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import Grade

NOT_TESTED = "not_tested"
UNKNOWN = "unknown"


@dataclass(slots=True)
class Question:
    """One answerable prompt.

    `kind` is "choice", "yesno" or "number". Every choice question that
    describes a clinical test carries an explicit not-tested option: a form that
    forces a yes/no answer for a test nobody performed manufactures data.
    """

    id: str
    text: str
    kind: str
    options: list[str] = field(default_factory=list)
    unit: str | None = None
    why: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind,
            "options": list(self.options),
            "unit": self.unit,
            "why": self.why,
        }


@dataclass(slots=True)
class Trigger:
    """A red flag raised by one or more answers."""

    grade: Grade
    finding: str
    because: str
    consider: list[str] = field(default_factory=list)
    distinguished_by: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "grade": str(self.grade),
            "finding": self.finding,
            "because": self.because,
            "consider": list(self.consider),
            "distinguished_by": self.distinguished_by,
        }


YESNO = ["yes", "no", UNKNOWN]
TESTED = ["yes", "no", NOT_TESTED]


# --- question sets -----------------------------------------------------------

QUESTIONS: dict[str, list[Question]] = {
    "foot": [
        Question(
            "pedal_pulses", "Pedal pulses (dorsalis pedis and posterior tibial)",
            "choice", ["both_palpable", "one_absent", "both_absent", NOT_TESTED],
            why="Perfusion is the single strongest predictor of whether a foot "
                "wound heals, and it is invisible to a camera.",
        ),
        Question(
            "monofilament", "Protective sensation, 10 g monofilament",
            "choice", ["intact", "reduced", "absent", NOT_TESTED],
            why="Loss of protective sensation is why an ulcer forms unnoticed "
                "and why it keeps being walked on.",
        ),
        Question(
            "probe_to_bone", "Does a sterile probe reach bone in an open wound?",
            "choice", TESTED,
            why="A positive probe-to-bone substantially raises the probability "
                "of underlying bone infection, which changes the pathway.",
        ),
        Question(
            "systemic_signs",
            "Fever, rigors, tachycardia, vomiting or new confusion",
            "choice", YESNO,
            why="Systemic upset moves a foot infection from a clinic problem to "
                "a same-day hospital problem.",
        ),
        Question(
            "spreading_erythema",
            "Redness spreading more than 2 cm beyond the wound, or advancing "
            "hour by hour",
            "choice", YESNO,
            why="Rate of spread separates a stable wound margin from a "
                "progressing soft-tissue infection.",
        ),
        Question(
            "crepitus_odour_bullae",
            "Crepitus, foul odour, gas, blisters or blackened tissue",
            "choice", YESNO,
            why="These are the classic surface signs of a deep, rapidly "
                "destructive infection. They are a surgical emergency.",
        ),
        Question(
            "rest_pain", "Pain in the foot at rest, worse lying flat at night",
            "choice", YESNO,
            why="Ischaemic rest pain with tissue loss is the definition of a "
                "chronically threatened limb.",
        ),
        Question(
            "hot_swollen_no_wound",
            "Hot, swollen, red foot with intact skin in a neuropathic patient",
            "choice", YESNO,
            why="This pattern raises acute Charcot neuro-osteoarthropathy, "
                "where every day of continued walking causes further collapse.",
        ),
        Question(
            "purulent_discharge",
            "Purulent discharge from the wound",
            "choice", YESNO,
            why="Pus is the finding that separates a colonised wound from one "
                "that is actively infected, and it is not reliably visible in "
                "a photograph taken through a dressing.",
        ),
        Question(
            "open_ulcer", "Is there an open ulcer — skin broken through?",
            "choice", YESNO,
            why="Several of the rules below turn on this, and a photograph "
                "cannot separate an open wound from callus over intact skin. "
                "Only a look and a probe can.",
        ),
        Question(
            "glycaemic_control", "Recent HbA1c",
            "number", unit="%",
            why="Glycaemic control governs whether any wound closes at all, "
                "and it is the one input here that no examination of the foot "
                "itself provides.",
        ),
        Question(
            "duration_weeks", "How long has the lesion been present?",
            "number", unit="weeks",
            why="A wound open beyond about a month is not simply healing "
                "slowly; something is preventing it from healing.",
        ),
    ],
}


def questions_for(module: str) -> list[Question]:
    return list(QUESTIONS.get(module, []))


def _valid_ids(module: str) -> dict[str, Question]:
    return {q.id: q for q in QUESTIONS.get(module, [])}


# --- rules -------------------------------------------------------------------

def _num(answers: dict[str, Any], key: str) -> float | None:
    raw = answers.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _foot_rules(a: dict[str, Any]) -> list[Trigger]:
    out: list[Trigger] = []
    pulses = a.get("pedal_pulses")

    if a.get("crepitus_odour_bullae") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Crepitus, gas, foul odour, bullae or blackened tissue reported.",
            "This combination is the recognised surface presentation of a "
            "deep, rapidly spreading soft-tissue infection.",
            consider=["Necrotising soft-tissue infection",
                      "Gas-forming infection in a devitalised wound",
                      "Extensive wet gangrene"],
            distinguished_by="Immediate surgical assessment. Imaging must not "
                             "delay it.",
        ))

    if a.get("systemic_signs") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Systemic upset reported alongside a foot lesion.",
            "Fever, rigors, tachycardia, vomiting or new confusion move a "
            "foot infection out of the clinic setting.",
            consider=["Systemic response to a foot infection",
                      "Deep abscess or spreading infection",
                      "Hyperglycaemic decompensation"],
            distinguished_by="Same-day assessment with observations, "
                             "inflammatory markers, glucose and blood cultures.",
        ))

    if a.get("probe_to_bone") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Probe-to-bone positive in an open wound.",
            "A probe reaching bone substantially raises the probability that "
            "bone beneath the ulcer is involved.",
            consider=["Bone involvement beneath the ulcer",
                      "Deep soft-tissue infection without bone involvement",
                      "Exposed bone in a chronic non-infected wound"],
            distinguished_by="Plain radiograph now, MRI or bone biopsy where "
                             "the radiograph is not conclusive.",
        ))

    if a.get("spreading_erythema") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Erythema spreading beyond the wound margin.",
            "Extent and rate of spread are what separate a stable margin from "
            "a progressing infection, and a single image shows neither.",
            consider=["Spreading soft-tissue infection",
                      "Acute Charcot neuro-osteoarthropathy",
                      "Inflammatory response to trauma or pressure"],
            distinguished_by="Mark the margin with a pen, re-examine within "
                             "hours, and assess in person the same day.",
        ))

    if a.get("hot_swollen_no_wound") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Hot, swollen, red foot with intact skin in a neuropathic patient.",
            "This is the presentation in which acute Charcot "
            "neuro-osteoarthropathy is missed, and each day of continued "
            "walking causes further bone collapse.",
            consider=["Acute Charcot neuro-osteoarthropathy",
                      "Cellulitis", "Gout or acute inflammatory arthritis",
                      "Deep vein thrombosis"],
            distinguished_by="Same-day specialist foot assessment; radiographs "
                             "and MRI, with immediate offloading while the "
                             "question is being answered.",
        ))

    if pulses == "both_absent":
        out.append(Trigger(
            Grade.URGENT,
            "Neither pedal pulse palpable.",
            "Absent pulses with tissue loss is the pattern that defines a "
            "chronically threatened limb.",
            consider=["Peripheral arterial disease limiting healing",
                      "Oedema or swelling masking palpable pulses",
                      "Examiner-dependent false negative"],
            distinguished_by="Doppler waveforms, ankle-brachial or toe "
                             "pressures, and vascular assessment.",
        ))
    elif pulses == "one_absent":
        out.append(Trigger(
            Grade.REVIEW,
            "One pedal pulse not palpable.",
            "Reduced perfusion is the commonest reason a foot wound fails to "
            "heal on the expected trajectory.",
            consider=["Peripheral arterial disease",
                      "Anatomical variant or oedema masking the pulse"],
            distinguished_by="Doppler and ankle-brachial or toe pressures.",
        ))

    if a.get("rest_pain") == "yes":
        grade = Grade.URGENT if pulses in ("both_absent", "one_absent") else Grade.REVIEW
        out.append(Trigger(
            grade,
            "Rest pain, worse lying flat.",
            "Pain relieved by hanging the foot down points at perfusion "
            "rather than at the wound itself."
            + (" Reported here together with an absent pulse."
               if grade is Grade.URGENT else ""),
            consider=["Ischaemic rest pain",
                      "Painful diabetic neuropathy",
                      "Nocturnal cramp or musculoskeletal pain"],
            distinguished_by="Ankle-brachial and toe pressures; neuropathic "
                             "pain typically does not change with limb "
                             "position.",
        ))

    if a.get("monofilament") == "absent":
        out.append(Trigger(
            Grade.REVIEW,
            "Protective sensation absent on monofilament testing.",
            "A foot that cannot feel injury will keep being walked on, which "
            "is why these wounds recur in the same place.",
            consider=["Loss of protective sensation from diabetic neuropathy",
                      "Neuropathy from another cause",
                      "Test performed at the wrong sites or through callus"],
            distinguished_by="Repeat at standard sites with vibration testing; "
                             "structured risk stratification.",
        ))

    # --- combination rules -------------------------------------------------
    # Single findings are handled above. These are the PATTERNS: combinations
    # that mean more together than the sum of their parts, and that decide
    # where the patient goes today.
    ulcer = a.get("open_ulcer") == "yes"

    if ulcer and pulses in ("both_absent", "one_absent") and a.get("rest_pain") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Open ulcer with an absent pulse and rest pain.",
            "Tissue loss, absent perfusion and ischaemic rest pain together "
            "are the defining pattern of a chronically threatened limb. The "
            "wound will not close while the perfusion does not support it.",
            consider=["Chronic limb-threatening ischaemia",
                      "Neuroischaemic ulcer",
                      "Infection on a background of poor perfusion"],
            distinguished_by="Urgent vascular assessment — Doppler waveforms, "
                             "ankle and toe pressures — BEFORE any local wound "
                             "procedure is considered.",
        ))

    if ulcer and a.get("systemic_signs") == "yes" and (
            a.get("purulent_discharge") == "yes"
            or a.get("crepitus_odour_bullae") == "yes"):
        out.append(Trigger(
            Grade.URGENT,
            "Open ulcer with pus or foul odour AND systemic upset.",
            "Local infection with a systemic response is the combination that "
            "moves a foot from a clinic problem to a same-day hospital one, "
            "and it is the setting in which underlying bone involvement is "
            "most often found.",
            consider=["Deep soft-tissue infection",
                      "Bone involvement beneath the ulcer",
                      "Abscess requiring drainage",
                      "Systemic sepsis from a foot source"],
            distinguished_by="Same-day assessment with probe-to-bone, plain "
                             "radiograph, inflammatory markers and blood "
                             "cultures, and wound sampling taken properly "
                             "rather than by surface swab.",
        ))

    if a.get("purulent_discharge") == "yes" and not ulcer:
        out.append(Trigger(
            Grade.REVIEW,
            "Purulent discharge reported without a recorded open ulcer.",
            "Pus has to be coming from somewhere. A sinus, a deep space or an "
            "ulcer hidden under callus are all possibilities that a surface "
            "look can miss.",
            consider=["Ulcer concealed beneath callus",
                      "Sinus tract from a deeper focus",
                      "Infected fissure or nail fold"],
            distinguished_by="Direct inspection with callus pared back by a "
                             "trained clinician, and probing of any opening "
                             "that is found.",
        ))

    # A CONTRAINDICATION, not a recommendation. This platform never says what
    # to do TO a wound. It can say what must not be done, because "do not" is
    # protective in exactly the way an instruction is not — and this one is the
    # difference between a wound and an amputation. Sharp debridement of an
    # ischaemic foot removes tissue that has no blood supply to heal the
    # resulting defect.
    if ulcer and pulses in ("both_absent", "one_absent"):
        out.append(Trigger(
            Grade.URGENT,
            "DO NOT debride: an open ulcer with an absent or reduced pulse.",
            "Debridement of a foot that is not perfused creates a wound the "
            "circulation cannot close. Perfusion is assessed BEFORE any sharp "
            "procedure, not after it.",
            consider=["Perfusion inadequate for any local procedure",
                      "Pulse absent from oedema or examiner variation",
                      "Medial arterial calcification masking the true pressure"],
            distinguished_by="Vascular assessment first — Doppler waveforms, "
                             "toe pressures. The decision about any procedure "
                             "belongs to the clinician who has that result.",
        ))

    hba1c = _num(a, "glycaemic_control")
    if hba1c is not None and hba1c >= 9.0:
        out.append(Trigger(
            Grade.REVIEW,
            f"HbA1c {hba1c:g}%.",
            "Glycaemic control at this level works against healing whatever "
            "is done locally to the wound, and it is not something the foot "
            "examination or the photograph can show.",
            consider=["Wound failing to heal on metabolic grounds",
                      "Concurrent infection driving the glucose up",
                      "Treatment adherence or regimen no longer adequate"],
            distinguished_by="Diabetes review alongside the foot care, not "
                             "after it.",
        ))

    weeks = _num(a, "duration_weeks")
    if weeks is not None and weeks >= 4:
        out.append(Trigger(
            Grade.REVIEW,
            f"Lesion present for about {weeks:g} weeks.",
            "Beyond roughly a month a wound is not healing slowly, it is "
            "being prevented from healing.",
            consider=["Unrelieved pressure on the wound",
                      "Inadequate perfusion",
                      "Persisting infection or bone involvement"],
            distinguished_by="Offloading assessment, vascular studies, and "
                             "review of the wound bed by a foot service.",
        ))

    return out








_RULES = {
    "foot": _foot_rules,
}


# --- evaluation --------------------------------------------------------------

@dataclass(slots=True)
class FollowUpOutcome:
    module: str
    answer_grade: Grade
    triggers: list[Trigger]
    answered: dict[str, Any]
    unanswered: list[str]
    not_tested: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "answer_grade": str(self.answer_grade),
            "triggers": [t.to_json() for t in self.triggers],
            "answers": dict(self.answered),
            "unanswered": list(self.unanswered),
            "not_tested": list(self.not_tested),
            "rule": (
                "This grade comes from the answers alone. The photograph is "
                "not an input to it — see app/routing.py. The case is routed "
                "on the more urgent of these answers and the IWGDF risk "
                "category, both of which are findings a clinician obtained "
                "rather than inferences from pixels."
            ),
            "status": (
                "Clinician-entered findings, not measurements made by QADAM. "
                "They are stored as reported and are not verified."
            ),
        }


class UnknownFollowUpField(ValueError):
    def __init__(self, field_id: str, module: str, allowed: list[str]) -> None:
        super().__init__(field_id)
        self.field_id = field_id
        self.module = module
        self.allowed = allowed


class InvalidFollowUpAnswer(ValueError):
    def __init__(self, field_id: str, value: Any, allowed: list[str]) -> None:
        super().__init__(field_id)
        self.field_id = field_id
        self.value = value
        self.allowed = allowed


def validate(module: str, answers: dict[str, Any]) -> dict[str, Any]:
    """Reject unknown fields and out-of-vocabulary values.

    A silently ignored answer is worse than a rejected one: the clinician
    believes they reported an absent pulse and the record shows nothing.
    """
    known = _valid_ids(module)
    clean: dict[str, Any] = {}
    for key, value in answers.items():
        question = known.get(key)
        if question is None:
            raise UnknownFollowUpField(key, module, sorted(known))
        if value is None or value == "":
            continue
        if question.kind == "number":
            try:
                clean[key] = float(value)
            except (TypeError, ValueError):
                raise InvalidFollowUpAnswer(key, value, ["a number"])
            continue
        text = str(value)
        if question.options and text not in question.options:
            raise InvalidFollowUpAnswer(key, value, list(question.options))
        clean[key] = text
    return clean


def evaluate(module: str, answers: dict[str, Any]) -> FollowUpOutcome:
    """Grade the ANSWERS. The image is deliberately not a parameter.

    It used to be: the outcome was max(image grade, answer grade). That made a
    hand-tuned colour threshold a term in a clinical decision, and this project
    measured the ceiling on those thresholds directly. Routing now combines
    these answers with the IWGDF category instead — see app/routing.py.
    """
    clean = validate(module, answers)
    triggers = _RULES.get(module, lambda _a: [])(clean)
    triggers.sort(key=lambda t: -t.grade.rank)

    answer_grade = Grade.NO_FLAG
    for trigger in triggers:
        if trigger.grade.rank > answer_grade.rank:
            answer_grade = trigger.grade

    asked = _valid_ids(module)
    return FollowUpOutcome(
        module=module,
        answer_grade=answer_grade,
        triggers=triggers,
        answered=clean,
        unanswered=[qid for qid in asked if qid not in clean],
        not_tested=[qid for qid, val in clean.items()
                    if val in (NOT_TESTED, UNKNOWN)],
    )
