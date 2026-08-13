"""Single source of truth for the QADAM safety boundary.

Every surface that shows or exports a result -- API payloads, PDF summaries,
burned-in image overlays, the web UI -- reads its disclaimer text from here.
Do not duplicate these strings elsewhere and do not weaken them.

The product performs SURFACE SCREENING AND TRIAGE ROUTING ONLY. It is an aid to
a clinician, never a replacement, and a human clinician confirms every
clinically significant output. It must never claim to diagnose internal
pathology from a photograph.
"""

from __future__ import annotations

# --- Universal notices -------------------------------------------------------

DISCLAIMER = (
    "Research/decision-support tool — not a diagnosis. "
    "Not a substitute for clinical assessment."
)

DEVICE_NOTICE = "NOT A MEDICAL DEVICE — not for clinical use."

HUMAN_IN_THE_LOOP = (
    "A qualified clinician must review and confirm every clinically significant "
    "output before any decision is made about a patient."
)

SCOPE_STATEMENT = (
    "QADAM analyses the visible surface of a photograph only. It cannot see "
    "beneath the skin. It does not diagnose, confirm or exclude any internal or "
    "sub-surface condition."
)

NO_TREATMENT_STATEMENT = (
    "QADAM does not recommend treatment or medication and takes no autonomous "
    "action on a patient. Its output is a suggested next investigation only."
)

INTENDED_USE = (
    "QADAM is a camera-based screening and triage-routing aid for "
    "use by a trained health worker on a consenting patient. It grades the "
    "visible surface appearance of a body region and recommends which real "
    "investigation or specialty to route the patient to. Every output requires "
    "confirmation by a qualified clinician. QADAM is not validated, not "
    "registered, and is not cleared by any regulator as a medical device."
)

# Explicit list of things the platform must never assert. Surfaced in the API so
# the boundary is visible to any integrator, and asserted in the test suite.
NEVER_CLAIMS = [
    "diagnosis of any condition",
    "fracture",
    "dislocation",
    "tendon rupture",
    "muscle tear",
    "internal bleeding",
    "any internal or sub-surface pathology",
    "retinal disease from a non-fundus photograph",
    "treatment or medication recommendation",
]

# --- Module-specific limitations --------------------------------------------

MODULE_LIMITATIONS: dict[str, list[str]] = {
    "foot": [
        SCOPE_STATEMENT,
        "Surface appearance only. Depth of an ulcer, bone involvement, "
        "osteomyelitis and deep infection cannot be assessed from a photograph.",
        "Perfusion and neuropathy must be assessed clinically (pulses, ABPI, "
        "monofilament) — they are not visible to a camera.",
    ],
    "skin": [
        SCOPE_STATEMENT,
        "Surface appearance only. This is not a dermatoscopic assessment and it "
        "cannot determine whether a lesion is benign or malignant. Only "
        "histopathology can do that.",
        "A low-concern result does not exclude skin cancer. Any lesion that "
        "changes, bleeds or concerns the patient or clinician warrants review "
        "regardless of the QADAM grade.",
    ],
    "eye": [
        SCOPE_STATEMENT,
        "ANTERIOR SURFACE ONLY. Retinal disease — including diabetic "
        "retinopathy, macular degeneration and glaucomatous optic nerve change "
        "— is NOT assessable without a fundus camera and is entirely outside "
        "the scope of this module.",
        "Visual acuity and intraocular pressure are not assessed. Sudden "
        "visual loss, trauma or severe pain is a clinical emergency "
        "irrespective of this result.",
        "PUPIL SIZE IS MEASURED, PUPIL REACTION IS NOT. A still photograph "
        "cannot show whether a pupil constricts to light, and reaction matters "
        "more than size. The swinging-flashlight test for a relative afferent "
        "pupillary defect, and whether unequal pupils become more unequal in "
        "bright or in dim light, both require a clinician with a torch.",
        "Pupil sizes are estimated by assuming an iris diameter of 11.7 mm. "
        "Individual irises vary by roughly ±0.5 mm, so every millimetre figure "
        "carries at least that much uncertainty, plus any error from camera "
        "angle. Unequal pupils with head injury, reduced consciousness, "
        "drooping eyelid or double vision are an emergency regardless of what "
        "this measurement says.",
    ],
    "face": [
        SCOPE_STATEMENT,
        "COLOUR IN A PHOTOGRAPH IS NOT RELIABLE. Camera auto white-balance, "
        "screen light, tungsten or fluorescent lighting and make-up all shift "
        "apparent colour more than illness does. Only relative comparisons "
        "between facial regions are reported, and even those are indicative "
        "only.",
        "This module is NOT a pulse oximeter. Apparent lip colour cannot "
        "measure oxygen saturation, and a normal-looking photograph does not "
        "exclude hypoxaemia. If cyanosis is suspected clinically, measure SpO₂ "
        "immediately — do not wait for or rely on this result.",
        "Anaemia cannot be graded from a face photograph. Conjunctival, palmar "
        "and nail-bed assessment plus a full blood count are required.",
        "Facial asymmetry is not assessed here and a normal appearance does "
        "NOT exclude stroke. If stroke is suspected, perform a FAST "
        "assessment in person and call emergency services immediately.",
    ],
    "injury": [
        SCOPE_STATEMENT,
        "ROUTING ONLY. This module detects external red flags (bruising, "
        "asymmetric swelling, visible deformity) and tells you which "
        "investigation to obtain. It does NOT diagnose injury.",
        "It CANNOT confirm or exclude fracture, dislocation, tendon or muscle "
        "rupture, internal bleeding or any other internal injury. Only imaging "
        "(X-ray, ultrasound, CT) and clinical assessment can do that.",
    ],
}

# Appended to a "no flag" result. For the injury module this is mandatory: an
# absent external red flag says nothing about the inside of the limb.
NO_FLAG_CAVEAT: dict[str, str] = {
    "foot": (
        "A no-flag result does not exclude deep infection, ischaemia or "
        "neuropathy. Continue routine diabetic foot surveillance."
    ),
    "skin": (
        "A no-flag result does not exclude skin cancer or any other skin "
        "disease. Re-image or refer if the lesion changes."
    ),
    "eye": (
        "A no-flag result covers the anterior surface only and does not exclude "
        "retinal or intraocular disease."
    ),
    "face": (
        "A no-flag result does not exclude hypoxaemia, anaemia, jaundice or "
        "stroke. Facial colour in a photograph is dominated by lighting and "
        "white balance. Measure SpO₂ and act on the clinical picture, not on "
        "this image."
    ),
    "injury": (
        "A NO-FLAG RESULT DOES NOT EXCLUDE INTERNAL INJURY. Fracture, "
        "dislocation, tendon rupture and internal bleeding can all be present "
        "with an unremarkable external appearance. If the mechanism of injury, "
        "the pain or the loss of function suggests injury, obtain imaging and "
        "clinical assessment regardless of this result."
    ),
}


def safety_block(module: str | None = None, grade: str | None = None) -> dict:
    """Build the safety payload embedded in every result and export."""
    block: dict = {
        "disclaimer": DISCLAIMER,
        "device_notice": DEVICE_NOTICE,
        "human_in_the_loop": HUMAN_IN_THE_LOOP,
        "scope": SCOPE_STATEMENT,
        "no_treatment": NO_TREATMENT_STATEMENT,
        "intended_use": INTENDED_USE,
        "clinical_use": False,
        "never_claims": list(NEVER_CLAIMS),
    }
    if module:
        block["module_limitations"] = list(MODULE_LIMITATIONS.get(module, []))
        if grade == "no_flag":
            caveat = NO_FLAG_CAVEAT.get(module)
            if caveat:
                block["no_flag_caveat"] = caveat
    return block
