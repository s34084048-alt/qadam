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
            "duration_weeks", "How long has the lesion been present?",
            "number", unit="weeks",
            why="A wound open beyond about a month is not simply healing "
                "slowly; something is preventing it from healing.",
        ),
    ],
    "skin": [
        Question(
            "changing",
            "Has it changed in size, shape or colour in the last 3 months?",
            "choice", YESNO,
            why="Evolution over time is the strongest single feature in the "
                "ABCDE criteria, and a single photograph cannot show it.",
        ),
        Question(
            "bleeding_or_non_healing",
            "Does it bleed on its own, or has it failed to heal for 6 weeks?",
            "choice", YESNO,
            why="Spontaneous bleeding and failure to heal are the features "
                "that put a lesion on a suspected-cancer pathway.",
        ),
        Question(
            "symptomatic", "Itching, tenderness, burning or altered sensation",
            "choice", YESNO,
            why="Symptoms separate inflammatory from purely pigmentary causes.",
        ),
        Question(
            "new_after_40", "New lesion appearing after the age of 40",
            "choice", YESNO,
            why="A genuinely new pigmented lesion in later adulthood carries "
                "different prior odds from one present since childhood.",
        ),
        Question(
            "risk_history",
            "Previous skin cancer, immunosuppression, or heavy sun exposure",
            "choice", YESNO,
            why="Personal history and immune status move the threshold for "
                "referral more than appearance does.",
        ),
    ],
    "face": [
        Question(
            "spo2", "Measured SpO₂ on room air", "number", unit="%",
            why="This module is not a pulse oximeter. A real reading replaces "
                "the guess entirely, and outranks anything the image showed.",
        ),
        Question(
            "respiratory_distress",
            "Breathless at rest, using accessory muscles, or unable to speak "
            "in full sentences",
            "choice", YESNO,
            why="Work of breathing is visible in the room and not in a "
                "portrait photograph.",
        ),
        Question(
            "altered_consciousness", "Drowsy, confused or difficult to rouse",
            "choice", YESNO,
            why="Reduced consciousness changes the destination regardless of "
                "what any colour measurement says.",
        ),
        Question(
            "fast_positive",
            "FAST: facial droop, arm weakness or speech difficulty",
            "choice", YESNO,
            why="Facial asymmetry is not assessed by this module at all, and a "
                "normal-looking photograph does not exclude stroke.",
        ),
        Question(
            "dark_urine_pale_stool", "Dark urine or pale stools",
            "choice", YESNO,
            why="These separate a yellow cast from lighting out of a genuine "
                "hepatobiliary picture.",
        ),
    ],
    "eye": [
        Question(
            "vision_change", "Sudden loss or blurring of vision",
            "choice", YESNO,
            why="Visual acuity is not assessed by this module, and sudden loss "
                "is time-critical.",
        ),
        Question(
            "severe_pain_or_photophobia",
            "Severe eye pain, headache around the eye, or marked light "
            "sensitivity",
            "choice", YESNO,
            why="Pain of this kind separates a red eye that can wait from one "
                "that cannot.",
        ),
        Question(
            "trauma_or_chemical", "Trauma, foreign body, or chemical splash",
            "choice", YESNO,
            why="A chemical splash needs irrigation started immediately, "
                "before any referral is arranged.",
        ),
        Question(
            "head_injury_or_drowsy",
            "Head injury, drowsiness, drooping eyelid or double vision",
            "choice", YESNO,
            why="Unequal pupils mean something entirely different in this "
                "context, and a photograph cannot supply that context.",
        ),
        Question(
            "contact_lens", "Contact lens wearer", "choice", YESNO,
            why="A red, painful eye in a lens wearer is treated as a corneal "
                "emergency until proven otherwise.",
        ),
    ],
    "injury": [
        Question(
            "weight_bearing", "Can the patient bear weight or use the limb?",
            "choice", ["yes", "no", "not_applicable"],
            why="Inability to bear weight is a core element of the validated "
                "decision rules for whether imaging is needed.",
        ),
        Question(
            "bony_tenderness", "Focal tenderness directly over bone",
            "choice", TESTED,
            why="Point bony tenderness is what those same rules test for.",
        ),
        Question(
            "deformity_or_open_wound",
            "Visible deformity, or a wound overlying the injury",
            "choice", YESNO,
            why="An open wound over a suspected fracture changes both the "
                "urgency and the destination.",
        ),
        Question(
            "neurovascular",
            "Numbness, pins and needles, cold limb or absent distal pulse",
            "choice", YESNO,
            why="A neurovascular deficit distal to an injury is time-critical "
                "and is never visible in a photograph.",
        ),
        Question(
            "high_energy", "High-energy mechanism (fall from height, vehicle)",
            "choice", YESNO,
            why="Mechanism drives the imaging decision more than external "
                "appearance does.",
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


def _skin_rules(a: dict[str, Any]) -> list[Trigger]:
    out: list[Trigger] = []

    if a.get("bleeding_or_non_healing") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Lesion bleeds spontaneously or has not healed in 6 weeks.",
            "These two features are what place a lesion on a "
            "suspected-cancer referral pathway irrespective of appearance.",
            consider=["Non-healing lesion requiring histological diagnosis",
                      "Chronic traumatised or excoriated lesion",
                      "Infected or inflamed benign lesion"],
            distinguished_by="Histopathology. Nothing else settles it.",
        ))

    if a.get("changing") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "Reported change in size, shape or colour.",
            "Evolution over time is the strongest single ABCDE feature, and a "
            "single photograph cannot show it.",
            consider=["Evolving pigmented lesion",
                      "Seborrhoeic keratosis becoming raised",
                      "Post-inflammatory pigment change"],
            distinguished_by="Dermoscopy by a trained examiner, comparison "
                             "with earlier photographs, and biopsy if doubt "
                             "remains.",
        ))

    if a.get("new_after_40") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "New lesion appearing after the age of 40.",
            "A genuinely new pigmented lesion in later adulthood carries "
            "different prior odds from one present since childhood.",
            consider=["New melanocytic lesion",
                      "Seborrhoeic keratosis",
                      "Lentigo"],
            distinguished_by="Dermoscopy, and excision or biopsy where the "
                             "pattern is not clearly benign.",
        ))

    if a.get("risk_history") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "Previous skin cancer, immunosuppression or heavy sun exposure.",
            "Personal history and immune status shift the referral threshold "
            "more than the appearance of any single lesion.",
            consider=["Second primary skin cancer",
                      "Accelerated lesion behaviour under immunosuppression",
                      "Sun-damaged skin with multiple benign lesions"],
            distinguished_by="Full skin examination by a dermatologist rather "
                             "than assessment of this lesion alone.",
        ))

    return out


def _face_rules(a: dict[str, Any]) -> list[Trigger]:
    out: list[Trigger] = []

    spo2 = _num(a, "spo2")
    if spo2 is not None and spo2 < 92:
        out.append(Trigger(
            Grade.URGENT,
            f"Measured SpO₂ {spo2:g}% on room air.",
            "A real oximeter reading replaces every inference this module "
            "made from colour, and outranks it.",
            consider=["Hypoxaemia requiring immediate assessment",
                      "Poor probe trace, cold peripheries or nail polish",
                      "Chronically low baseline saturation"],
            distinguished_by="Repeat on a warm hand with a good waveform, and "
                             "assess the patient in person now.",
        ))

    if a.get("fast_positive") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "FAST positive: facial droop, arm weakness or speech difficulty.",
            "This module does not assess facial asymmetry at all, so a "
            "no-flag colour result says nothing about stroke.",
            consider=["Acute stroke", "Hypoglycaemia", "Bell's palsy",
                      "Seizure with post-ictal weakness"],
            distinguished_by="Emergency services now, with a capillary glucose "
                             "taken on the way.",
        ))

    if a.get("altered_consciousness") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Drowsy, confused or difficult to rouse.",
            "Reduced consciousness changes the destination regardless of any "
            "measurement made from a photograph.",
            consider=["Hypoxaemia or hypercapnia", "Sepsis",
                      "Hypoglycaemia", "Intracranial event"],
            distinguished_by="Immediate in-person assessment: observations, "
                             "capillary glucose, conscious level.",
        ))

    if a.get("respiratory_distress") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Breathless at rest or unable to speak in full sentences.",
            "Work of breathing is visible in the room and absent from a "
            "portrait photograph.",
            consider=["Acute respiratory failure",
                      "Cardiac failure", "Severe anaemia"],
            distinguished_by="SpO₂, respiratory rate and in-person assessment "
                             "now.",
        ))

    if a.get("dark_urine_pale_stool") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "Dark urine or pale stools reported.",
            "These separate a yellow cast caused by lighting from a genuine "
            "hepatobiliary picture.",
            consider=["Cholestatic pattern", "Hepatocellular pattern",
                      "Dehydration accounting for urine colour alone"],
            distinguished_by="Bilirubin with liver enzymes, and abdominal "
                             "ultrasound where obstruction is suspected.",
        ))

    return out


def _eye_rules(a: dict[str, Any]) -> list[Trigger]:
    out: list[Trigger] = []

    if a.get("trauma_or_chemical") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Trauma, foreign body or chemical splash reported.",
            "A chemical injury is one of the few eye presentations where "
            "irrigation must begin before anything else, including referral.",
            consider=["Chemical injury to the ocular surface",
                      "Corneal abrasion or retained foreign body",
                      "Penetrating injury"],
            distinguished_by="Immediate copious irrigation for any chemical "
                             "exposure, then same-day ophthalmic assessment "
                             "with slit lamp and fluorescein.",
        ))

    if a.get("vision_change") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Sudden loss or blurring of vision.",
            "Visual acuity is not assessed by this module, and sudden loss is "
            "time-critical whatever the anterior surface looks like.",
            consider=["Retinal or optic nerve cause not visible to this module",
                      "Acute angle-closure glaucoma",
                      "Corneal or anterior chamber cause"],
            distinguished_by="Same-day ophthalmic assessment: acuity, "
                             "intraocular pressure and dilated fundus "
                             "examination.",
        ))

    if a.get("severe_pain_or_photophobia") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Severe eye pain, peri-ocular headache or marked photophobia.",
            "Pain of this character is what separates a red eye that can wait "
            "from one that cannot.",
            consider=["Acute angle-closure glaucoma", "Anterior uveitis",
                      "Keratitis or corneal ulcer", "Scleritis"],
            distinguished_by="Slit-lamp examination and intraocular pressure "
                             "the same day.",
        ))

    if a.get("head_injury_or_drowsy") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Head injury, drowsiness, ptosis or double vision.",
            "Unequal pupils mean something entirely different in this "
            "context, and no photograph can supply that context.",
            consider=["Intracranial cause of pupil asymmetry",
                      "Third nerve palsy", "Horner syndrome",
                      "Long-standing physiological anisocoria"],
            distinguished_by="Emergency assessment with conscious level and "
                             "urgent brain imaging.",
        ))

    if a.get("contact_lens") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "Contact lens wearer.",
            "A red or painful eye in a lens wearer is handled as a corneal "
            "problem until proven otherwise.",
            consider=["Microbial keratitis", "Contact lens overwear",
                      "Allergic or giant papillary conjunctivitis"],
            distinguished_by="Same-day slit lamp with fluorescein; corneal "
                             "scrape where an infiltrate is seen.",
        ))

    return out


def _injury_rules(a: dict[str, Any]) -> list[Trigger]:
    """Routing only. Nothing here asserts that a fracture is or is not present.

    Every trigger below produces the same kind of output as the rest of the
    injury module: a destination and an investigation to obtain.
    """
    out: list[Trigger] = []

    if a.get("neurovascular") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Numbness, pins and needles, cold limb or absent distal pulse.",
            "A deficit distal to an injury is time-critical and is not "
            "visible in a photograph.",
            consider=["Vascular compromise distal to the injury",
                      "Nerve involvement",
                      "Compartment syndrome",
                      "Positional or pressure-related symptoms"],
            distinguished_by="Immediate in-person assessment with pulses, "
                             "capillary refill and sensation; imaging as "
                             "directed by that assessment.",
        ))

    if a.get("deformity_or_open_wound") == "yes":
        out.append(Trigger(
            Grade.URGENT,
            "Visible deformity, or a wound overlying the injured area.",
            "A wound over an injured area changes both the urgency and the "
            "destination.",
            consider=["Open injury requiring surgical assessment",
                      "Soft-tissue laceration over an uninjured bone",
                      "Pre-existing deformity"],
            distinguished_by="Radiographs and in-person surgical assessment. "
                             "QADAM cannot confirm or exclude any bone or "
                             "joint injury.",
        ))

    if a.get("weight_bearing") == "no" or a.get("bony_tenderness") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "Unable to bear weight, or focal tenderness over bone.",
            "These are the elements the validated decision rules use to "
            "decide whether imaging is needed.",
            consider=["Injury requiring radiographs",
                      "Soft-tissue injury with guarding",
                      "Pain limiting a reliable examination"],
            distinguished_by="Radiographs, interpreted with the mechanism and "
                             "the in-person examination.",
        ))

    if a.get("high_energy") == "yes":
        out.append(Trigger(
            Grade.REVIEW,
            "High-energy mechanism reported.",
            "Mechanism drives the imaging decision more than external "
            "appearance does.",
            consider=["Injury disproportionate to external appearance",
                      "Multiple sites of injury",
                      "Isolated low-risk injury despite the mechanism"],
            distinguished_by="Structured in-person assessment and imaging "
                             "chosen from the mechanism.",
        ))

    return out


_RULES = {
    "foot": _foot_rules,
    "skin": _skin_rules,
    "face": _face_rules,
    "eye": _eye_rules,
    "injury": _injury_rules,
}


# --- evaluation --------------------------------------------------------------

@dataclass(slots=True)
class FollowUpOutcome:
    module: str
    image_grade: Grade
    answer_grade: Grade
    combined_grade: Grade
    escalated: bool
    triggers: list[Trigger]
    answered: dict[str, Any]
    unanswered: list[str]
    not_tested: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "image_grade": str(self.image_grade),
            "answer_grade": str(self.answer_grade),
            "combined_grade": str(self.combined_grade),
            "escalated": self.escalated,
            "triggers": [t.to_json() for t in self.triggers],
            "answers": dict(self.answered),
            "unanswered": list(self.unanswered),
            "not_tested": list(self.not_tested),
            "rule": (
                "The combined grade is the more urgent of the image grade and "
                "the answer grade. Answers can raise urgency; they never lower "
                "it. Reassuring answers are recorded and shown, but a "
                "measured image flag is not withdrawn because a test was "
                "reported as normal."
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


def evaluate(module: str, image_grade: Grade,
             answers: dict[str, Any]) -> FollowUpOutcome:
    clean = validate(module, answers)
    triggers = _RULES.get(module, lambda _a: [])(clean)
    triggers.sort(key=lambda t: -t.grade.rank)

    answer_grade = Grade.NO_FLAG
    for trigger in triggers:
        if trigger.grade.rank > answer_grade.rank:
            answer_grade = trigger.grade

    combined = image_grade if image_grade.rank >= answer_grade.rank else answer_grade

    asked = _valid_ids(module)
    return FollowUpOutcome(
        module=module,
        image_grade=image_grade,
        answer_grade=answer_grade,
        combined_grade=combined,
        escalated=combined.rank > image_grade.rank,
        triggers=triggers,
        answered=clean,
        unanswered=[qid for qid in asked if qid not in clean],
        not_tested=[qid for qid, val in clean.items()
                    if val in (NOT_TESTED, UNKNOWN)],
    )
