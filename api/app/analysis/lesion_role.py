"""What a per-feature box MEANS — in one place, so the picture and the table
cannot disagree about it.

THE DEFECT THIS CLOSES
----------------------
The overlay has tagged every box with its role since the localisation layer
landed: `[artifact]` for a shadow or a callus, `[uncertain]` for a surface
change whose nature is unresolved, `[possible wound]` only where localisation
confirmed tissue disruption. The JSON carried none of it. So on an image whose
own result page said "the photographed area does not read as skin — every
measurement below is meaningless", the annotated picture read

    tissue breakdown [artifact] 31.3%

and the findings table, three cards below it, read

    tissue breakdown | 31.3% | 1.00

The word that made the number safe to read was dropped by the surface that is
easier to read. A table is skimmed; a burned-in label on a photograph is not.

The rule was a private helper inside the renderer, which is why only the
renderer could apply it. It lives here now, and `overlay.render_overlay` and
the API serializer both ask this module. Adding a role or changing a verdict
mapping changes both, or neither.

Roles are about the PIXELS, never about a patient. `POSSIBLE_WOUND` is the
strongest thing this vocabulary can say, and it still says "possible".
"""

from __future__ import annotations

from typing import Any

# A region localisation confirmed as tissue disruption.
POSSIBLE_WOUND = "possible_wound"
# A surface change the character tests could not resolve either way.
UNCERTAIN = "uncertain"
# Explicitly NOT a wound: cast light, or thickened keratin.
ARTIFACT = "artifact"

# The kinds whose character the foot pipeline actually measures. A kind outside
# this set has no verdict to read, so it gets no role claim -- see `role_for`.
CLASSIFIED_KINDS = frozenset({"dark_area", "tissue_breakdown", "erythema"})

# Human-readable, for a burned-in label or a table cell.
ROLE_LABEL = {
    POSSIBLE_WOUND: "possible wound",
    UNCERTAIN: "uncertain",
    ARTIFACT: "artifact",
}


def _wound_confirmed(features: dict[str, Any]) -> bool:
    return (features.get("wound_localization") or {}).get(
        "classification") == "confirmed_possible_wound"


def role_for(kind: str, features: dict[str, Any] | None) -> str:
    """The role of a `kind` box, given the run's features.

    UNCERTAIN is the answer whenever the evidence does not positively support
    another one -- including for a kind this pipeline does not characterise.
    Defaulting to ARTIFACT would dismiss a finding on no evidence; defaulting
    to POSSIBLE_WOUND would assert one. Neither is a reading of the image.
    """
    features = features or {}
    dark = (features.get("dark_area_character") or {}).get("verdict")
    yellow = (features.get("yellow_area_character") or {}).get("verdict")

    if kind == "dark_area":
        role = {"tissue_like": POSSIBLE_WOUND,
                "shadow_like": ARTIFACT}.get(dark, UNCERTAIN)
    elif kind == "tissue_breakdown":
        role = {"slough_like": POSSIBLE_WOUND,
                "callus_like": ARTIFACT}.get(yellow, UNCERTAIN)
    else:
        # Erythema is never a wound claim on its own -- redness is a colour,
        # and colour is set as much by the lamp as by the skin.
        role = UNCERTAIN

    # A box may never claim MORE than the wound-localisation decision. Where
    # localisation drew no confirmed boundary -- the plausibility guard fired,
    # or quality was too poor -- "possible wound" is exactly the claim that
    # guard exists to withhold.
    if role == POSSIBLE_WOUND and not _wound_confirmed(features):
        role = UNCERTAIN
    return role
