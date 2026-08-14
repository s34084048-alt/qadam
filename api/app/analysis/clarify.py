"""The questions worth asking about THIS image.

A static report is read once and filed. A specialist asks the one or two
questions that would actually change the answer — and on a photograph the most
valuable question is almost always the one that tests whether the finding is
real.

Each question here names what it would SETTLE. That is the point: "re-take it
with the flash on" is advice, but "re-take it with the flash on, and if the
dark area disappears it was a shadow" is an experiment with a result. The
clinician performs it in ten seconds and knows something the platform could not
tell them.

At most two are returned. A list of eight questions is a form, and forms get
skipped.

NOTHING HERE IS A FINDING. Every entry is an open question, and none of them
asserts what the answer will be.
"""

from __future__ import annotations

from typing import Any

MAX_QUESTIONS = 2


def _dark_area(features: dict[str, Any]) -> float:
    return float(features.get("dark_area_pct", 0.0) or 0.0)


def _breakdown(features: dict[str, Any]) -> float:
    return float(features.get("breakdown_pct", 0.0) or 0.0)


def build(features: dict[str, Any]) -> list[dict[str, str]]:
    """Ordered by how much the answer would change, most first."""
    out: list[dict[str, str]] = []

    character = features.get("dark_area_character") or {}
    verdict = character.get("verdict")
    dark = _dark_area(features)
    breakdown = _breakdown(features)
    lighting = features.get("lighting") or {}
    scale = ((features.get("measurement") or {}).get("scale") or {})

    # 1. The dark area, when there is one. This is the single most valuable
    #    experiment available: it costs one photograph and it settles the
    #    question the module cannot.
    if dark > 0 and verdict in ("shadow_like", "indeterminate"):
        out.append({
            "ask": (
                "Re-take the photograph from about 30 cm with the flash ON, "
                "in the open, with the toes held apart. Does the dark area "
                "disappear?"
            ),
            "settles": (
                "A dark area that moves or vanishes under direct light was "
                "cast shadow. One that stays in the same place is on the skin, "
                "and only then is it worth examining as tissue."
            ),
            "because": (
                "The measurements read this darkness as "
                f"{'cast light' if verdict == 'shadow_like' else 'ambiguous'}, "
                "and no photograph can settle it on its own."
            ),
        })

    # 2. Callus, when the yellow area reads as dry keratin. This does NOT
    #    lower anything -- an ulcer under callus is invisible until it is
    #    pared back, and that is precisely why it is worth asking.
    yellow = (features.get("yellow_area_character") or {}).get("verdict")
    if breakdown > 0 and yellow == "callus_like":
        out.append({
            "ask": ("Is the skin actually broken here, or is this thickened "
                    "callus over intact skin? If callus, can it be pared back "
                    "to look underneath?"),
            "settles": (
                "The measurement reads this as dry keratin rather than moist "
                "tissue in a defect — but an ulcer very often lies UNDER "
                "callus and is invisible until it is pared. Only looking "
                "settles it."
            ),
            "because": (
                "Callus and slough are both yellow and both sit on the "
                "surface, so the colour threshold that finds one finds the "
                "other."
            ),
        })

    # 3. Depth, whenever there is a break in the surface. A photograph is
    #    perpendicular to the only axis that matters here.
    if breakdown > 0:
        out.append({
            "ask": (
                "Can a sterile probe be passed into the wound — does it reach "
                "bone, and does it track under the wound edge?"
            ),
            "settles": (
                "A positive probe-to-bone substantially raises the probability "
                "of underlying bone infection and changes the pathway today. "
                "Undermining changes the true size of the wound."
            ),
            "because": (
                "Apparent tissue breakdown covers "
                f"{breakdown:.1f}% of the imaged region, and depth is the one "
                "dimension a photograph has none of."
            ),
        })

    # 4. Poor light, measured against the card rather than guessed.
    if lighting.get("assessable") and not lighting.get("adequate"):
        out.append({
            "ask": ("Re-take with more light — flash on, or in daylight — with "
                    "the card and the foot lit the same way."),
            "settles": (
                "Underexposure darkens everything in the frame, so dark areas "
                "in this capture are partly the lamp. A correctly exposed "
                "photograph separates the two."
            ),
            "because": lighting.get("note", ""),
        })

    # 5. No size reference. Not urgent for today's decision, but it is what
    #    makes the NEXT visit comparable, so it is worth one line.
    if not scale.get("available") and (dark > 0 or breakdown > 0):
        out.append({
            "ask": ("Place a bank or ID card flat beside the area, in the same "
                    "light, and take one more photograph."),
            "settles": (
                "It fixes both the colour and the real size, so this wound can "
                "be measured in cm² and compared with the next visit. Without "
                "it the percentages cannot be compared between visits at all."
            ),
            "because": "No size reference was found in this frame.",
        })

    # 6. Nothing measured. The useful question is then about change over time,
    #    which a single photograph cannot show.
    if not out:
        out.append({
            "ask": ("Has the appearance of this area changed in the last 48 "
                    "hours — colour, size, or new pain?"),
            "settles": (
                "A single photograph has no time axis. Change is what "
                "separates a stable foot from one that is deteriorating, and "
                "only the patient or a previous image can supply it."
            ),
            "because": ("No discrete surface finding was isolated in this "
                        "image, which is not the same as nothing being wrong."),
        })

    return out[:MAX_QUESTIONS]
