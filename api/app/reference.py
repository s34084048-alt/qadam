"""Emergency positioning reference.

DELIBERATELY IMAGE-INDEPENDENT. Nothing here is generated from, selected by, or
altered by any photograph or analysis result. It is a fixed reference card.

That is the whole point. A casualty's spinal status cannot be read from a
photograph, and a tool that appeared to do so — telling a first responder that
a neck "looks fine" after a crash — could paralyse or kill someone. The safe
form of the emergency use case is protocol guidance that does not pretend to
assess the patient at all. The responder assesses; this reminds them of the
sequence.

Content is standard, widely taught first-response doctrine restricted to
RECOGNITION and POSITIONING. It contains no medication, no procedures, and no
wound care. It does not replace training, and it does not replace local
protocol.
"""

from __future__ import annotations

from typing import Any

DISCLAIMER = (
    "General reference for trained responders. NOT advice about any specific "
    "patient. Not generated from any image. Call emergency services first, "
    "work within your training, and follow your local protocol."
)

# --- diagrams ----------------------------------------------------------------
# Inline SVG, stroke: currentColor so they work on light and dark backgrounds.

_SVG_HEAD = (
    '<svg viewBox="0 0 320 140" xmlns="http://www.w3.org/2000/svg" '
    'fill="none" stroke="currentColor" stroke-width="2.5" '
    'stroke-linecap="round" stroke-linejoin="round" role="img">'
)

DIAGRAMS: dict[str, str] = {
    "in_line_stabilisation": _SVG_HEAD + (
        # supine casualty, rescuer kneeling above the head
        '<line x1="70" y1="95" x2="270" y2="95"/>'
        '<circle cx="60" cy="95" r="20"/>'
        '<line x1="150" y1="95" x2="150" y2="118"/>'
        '<line x1="210" y1="95" x2="210" y2="118"/>'
        # rescuer hands either side of the head
        '<path d="M40 70 q-14 25 0 50"/>'
        '<path d="M80 70 q14 25 0 50"/>'
        '<line x1="30" y1="60" x2="52" y2="74"/>'
        '<line x1="90" y1="60" x2="68" y2="74"/>'
        # neutral-alignment guide
        '<line x1="60" y1="95" x2="290" y2="95" stroke-dasharray="5 6" '
        'stroke-width="1.5" opacity="0.55"/>'
        '<text x="150" y="30" font-size="13" stroke="none" fill="currentColor">'
        'Head held in line with the body — no pulling</text>'
        '</svg>'
    ),
    "recovery_position": _SVG_HEAD + (
        # side-lying, top knee drawn up, head tilted back on the lower arm
        '<circle cx="66" cy="72" r="19"/>'
        '<path d="M84 78 q50 12 96 6"/>'
        '<path d="M84 92 q54 20 100 6"/>'
        '<path d="M180 84 q34 -4 40 22 q4 24 -22 26"/>'
        '<path d="M110 96 q22 34 54 30"/>'
        '<path d="M96 64 q34 -6 52 14"/>'
        '<text x="150" y="26" font-size="13" stroke="none" fill="currentColor">'
        'Airway open and pointing down — only if NO spinal concern</text>'
        '</svg>'
    ),
    "log_roll": _SVG_HEAD + (
        '<line x1="80" y1="92" x2="260" y2="92"/>'
        '<circle cx="66" cy="92" r="17"/>'
        # four pairs of hands along the body, head first
        '<path d="M52 64 q-10 28 0 56" stroke-width="2"/>'
        '<path d="M82 64 q10 28 0 56" stroke-width="2"/>'
        '<line x1="130" y1="66" x2="130" y2="84"/>'
        '<line x1="180" y1="66" x2="180" y2="84"/>'
        '<line x1="230" y1="66" x2="230" y2="84"/>'
        '<path d="M120 116 q40 16 100 0" stroke-dasharray="6 6" '
        'stroke-width="1.5" opacity="0.6"/>'
        '<text x="150" y="28" font-size="13" stroke="none" fill="currentColor">'
        'Four people. The one at the head counts and commands</text>'
        '<text x="150" y="136" font-size="12" stroke="none" fill="currentColor" '
        'opacity="0.75">Head, shoulders and pelvis turn as one unit</text>'
        '</svg>'
    ),
}


# --- content -----------------------------------------------------------------

TOPICS: list[dict[str, Any]] = [
    {
        "id": "priorities",
        "title": "Order of priorities before anything else",
        "steps": [
            "DANGER. Do not become a second casualty. Traffic, fire, "
            "electricity, water, unstable structures, hostile scene.",
            "CATASTROPHIC BLEEDING. Life-threatening external bleeding is "
            "controlled before anything else — direct, firm, sustained "
            "pressure on the wound.",
            "RESPONSE. Speak and gently squeeze the shoulders. Do not shake, "
            "and do not move the head.",
            "AIRWAY. In trauma, open the airway with a JAW THRUST while the "
            "head is held still, not by tilting the head back.",
            "BREATHING. Look, listen and feel for up to 10 seconds. Not "
            "breathing normally, or only gasping, means start CPR.",
            "CIRCULATION, then keep them warm.",
            "Call emergency services early and put the phone on speaker so "
            "your hands stay free.",
        ],
        "warnings": [
            "CPR and a blocked airway both override spinal precautions. A "
            "protected spine on a patient who is not breathing achieves "
            "nothing.",
        ],
    },
    {
        "id": "do_not_move",
        "title": "When NOT to move someone — suspected spinal injury",
        "steps": [
            "Suspect spinal injury from the MECHANISM, not from how the "
            "patient looks: fall from height or down stairs, road traffic "
            "collision, diving into shallow water, any high-energy impact, "
            "sports collision, and any fall in an older or frail person.",
            "Also suspect it if there is neck or back pain, tenderness over "
            "the spine, numbness, tingling, weakness, a head injury, reduced "
            "consciousness, or intoxication that makes the patient unreliable.",
            "LEAVE THE PATIENT WHERE THEY ARE, in the position found. Reassure "
            "them and tell them not to move.",
            "Hold the head still in line with the body — manual in-line "
            "stabilisation — and keep holding until someone with equipment "
            "takes over.",
            "Keep them warm. Monitor breathing and consciousness continuously.",
        ],
        "warnings": [
            "A patient who is walking and talking can still have an unstable "
            "spinal injury.",
            "Normal movement and normal sensation do NOT exclude a spinal "
            "fracture.",
            "No photograph, and no application, can assess a spine. Only "
            "imaging and clinical assessment can.",
        ],
        "move_only_if": [
            "The scene is immediately dangerous — fire, drowning, traffic, "
            "collapse, gas.",
            "The airway cannot be kept open in the position they are in.",
            "CPR is needed and cannot be performed where they lie.",
        ],
    },
    {
        "id": "in_line_stabilisation",
        "title": "Manual in-line stabilisation of the head and neck",
        "diagram": "in_line_stabilisation",
        "steps": [
            "Kneel or lie behind the top of the patient's head.",
            "Place a hand on each side of the head, spreading your fingers "
            "over the ears and along the jaw. Rest your elbows on the ground "
            "or on your knees so you can hold the position without tiring.",
            "Hold the head STILL in a neutral line with the body — nose in "
            "line with the navel, eyes facing forward.",
            "If the head is not already neutral, guide it gently towards "
            "neutral and STOP immediately if there is resistance, increased "
            "pain, or any new numbness, tingling or weakness. If any of those "
            "happen, hold it where it is.",
            "Do not let go until a trained team takes over the head, or the "
            "patient is fully immobilised.",
            "Talk to the patient the whole time. Tell them not to nod or shake "
            "their head to answer — ask them to speak or squeeze your finger.",
        ],
        "warnings": [
            "NEVER apply traction. Do not pull on the head or neck.",
            "Do not force the head into alignment.",
            "Do not remove a motorcycle helmet unless the airway cannot be "
            "managed with it on — and then only with two people, one holding "
            "the neck throughout.",
        ],
    },
    {
        "id": "recovery_position",
        "title": "Recovery position — unconscious and breathing normally",
        "diagram": "recovery_position",
        "steps": [
            "Use it only when the patient is unconscious, breathing normally, "
            "and there is NO suspicion of spinal injury.",
            "Kneel beside them. Place the nearer arm out at right angles, "
            "elbow bent, palm upwards.",
            "Bring the far arm across the chest and hold the back of that hand "
            "against the nearer cheek.",
            "With your other hand, pull up the far knee until the foot is flat "
            "on the ground.",
            "Pull on the raised knee to roll them towards you onto their side.",
            "Adjust the upper leg so hip and knee are bent at right angles.",
            "Tilt the head back gently to keep the airway open, and adjust the "
            "hand under the cheek so the head stays tilted and the mouth "
            "points slightly down to drain.",
            "Check breathing continuously. Turn them onto the other side after "
            "about 30 minutes if help has not arrived.",
        ],
        "warnings": [
            "If spinal injury is suspected AND the patient is unconscious but "
            "breathing, the airway still comes first — use a jaw thrust with "
            "the head held in line, and only turn them if you cannot keep the "
            "airway open otherwise. If you must turn them, log roll.",
        ],
    },
    {
        "id": "log_roll",
        "title": "Log roll — turning someone with a suspected spinal injury",
        "diagram": "log_roll",
        "steps": [
            "Only if you must: to clear the airway, to manage vomiting, "
            "because of immediate danger, or on instruction from the emergency "
            "service.",
            "You need at least FOUR people. One is dedicated to the head and "
            "neck and does nothing else.",
            "The person at the head holds in-line stabilisation and IS IN "
            "COMMAND — they count and they call the roll.",
            "The other three kneel on the same side: at the shoulders and "
            "chest, at the hips, and at the legs. Reach across and take firm "
            "hold of the far side.",
            "Brief everyone before moving: agree exactly what will happen and "
            "on which count.",
            "On the command, roll the patient towards the team as ONE UNIT — "
            "head, shoulders, pelvis and legs moving together, spine kept in "
            "line, no twisting and no bending.",
            "Roll only as far as needed, and hold the position. Return the "
            "same way on the same command.",
        ],
        "warnings": [
            "Never roll someone with a suspected spinal injury single-handed "
            "unless their life depends on it right now.",
            "Twisting or bending the spine during the roll is the harm this "
            "technique exists to prevent.",
        ],
    },
    {
        "id": "handover",
        "title": "Handover to the ambulance or receiving team",
        "steps": [
            "MECHANISM: exactly what happened, including height, speed, and "
            "what the patient struck.",
            "Where they were found and in what position, and whether anyone "
            "moved them — and why.",
            "Level of consciousness when you arrived and any change since.",
            "Whether they have moved their limbs, and any numbness, tingling "
            "or weakness they reported, with the time.",
            "Observations with times: breathing rate, pulse, SpO₂ if you have "
            "an oximeter, pupils.",
            "How long in-line stabilisation has been held, and by whom.",
        ],
        "warnings": [
            "The mechanism of injury is the single most useful thing you can "
            "hand over. Say it first.",
        ],
    },
]


def emergency_reference() -> dict[str, Any]:
    return {
        "kind": "static_reference",
        "image_independent": True,
        "generated_from_image": False,
        "title": "Emergency positioning and movement — responder reference",
        "disclaimer": DISCLAIMER,
        "why_static": (
            "A casualty cannot be assessed from a photograph. Spinal status, "
            "internal injury and level of consciousness are not visible to a "
            "camera, and a tool that appeared to judge them would be dangerous. "
            "This reference therefore does not look at any image and does not "
            "change based on any analysis — you assess the patient, this "
            "reminds you of the sequence.",
        ),
        "topics": TOPICS,
        "diagrams": DIAGRAMS,
    }
