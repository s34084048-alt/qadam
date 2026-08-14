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
}

# Appended to a "no flag" result. For the injury module this is mandatory: an
# absent external red flag says nothing about the inside of the limb.
NO_FLAG_CAVEAT: dict[str, str] = {
    "foot": (
        "A no-flag result does not exclude deep infection, ischaemia or "
        "neuropathy. Continue routine diabetic foot surveillance."
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
