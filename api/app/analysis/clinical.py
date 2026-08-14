"""Clinical depth layer.

Turns a set of measured surface features into the kind of structured note a
specialist would write from the same photograph: what the visible pattern
overlaps with, what test separates those possibilities, what to do right now to
protect the patient, and what to ask or examine because the camera cannot.

THE BOUNDARY IS UNCHANGED. Nothing here asserts a diagnosis. Every entry is a
DIFFERENTIAL -- a list of possibilities a clinician should evaluate -- and each
one names the investigation that actually distinguishes them. A single-item
differential is never emitted: if the surface cannot narrow it, it says so.

`immediate_actions` are protective, non-pharmacological steps taken WHILE the
referral is being arranged. No medication, no dose, no procedure, no wound
manipulation. See test_safety_boundary.py, which enforces all of this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import Grade, Lesion


@dataclass(slots=True)
class Consideration:
    """One differential prompt. `overlaps_with` always holds 2+ entries."""

    pattern: str
    overlaps_with: list[str]
    distinguished_by: str

    def to_json(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "overlaps_with": list(self.overlaps_with),
            "distinguished_by": self.distinguished_by,
        }


@dataclass(slots=True)
class ClinicalContext:
    severity_index: dict[str, Any] | None = None
    considerations: list[Consideration] = field(default_factory=list)
    immediate_actions: list[str] = field(default_factory=list)
    ask_and_check: list[str] = field(default_factory=list)
    not_assessable: list[str] = field(default_factory=list)
    scales: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "severity_index": self.severity_index,
            "considerations": [c.to_json() for c in self.considerations],
            "immediate_actions": list(self.immediate_actions),
            "ask_and_check": list(self.ask_and_check),
            "not_assessable": list(self.not_assessable),
            "scales": dict(self.scales),
            "status": (
                "Differential prompts for a clinician, not findings. The list is "
                "what the visible surface is compatible with; the named test is "
                "what settles it."
            ),
        }


# --- foot --------------------------------------------------------------------

def _foot(grade: Grade, f: dict[str, Any]) -> ClinicalContext:
    ery = float(f.get("erythema_pct", 0.0))
    brk = float(f.get("breakdown_pct", 0.0))
    nec = float(f.get("dark_area_pct", 0.0))

    # Weighted surface burden. Necrotic-appearing tissue and an open bed carry
    # far more weight than redness alone. Bounded 0-100; it summarises the
    # IMAGE, not the limb.
    burden = min(100.0, nec * 12.0 + brk * 6.0 + ery * 1.2)
    band = ("minimal" if burden < 5 else
            "mild" if burden < 20 else
            "moderate" if burden < 50 else "extensive")

    ctx = ClinicalContext(
        severity_index={
            "name": "Surface burden index",
            "value": round(burden, 1),
            "unit": "% (weighted surface score, 0-100)",
            "band": band,
            "components": {
                "dark_area_pct": round(nec, 2),
                "tissue_breakdown_pct": round(brk, 2),
                "erythema_pct": round(ery, 2),
            },
            "caveat": "A composite of visible area only. It is not a wound "
                      "grade and does not correlate with depth or infection.",
        },
        scales={
            "SINBAD": {
                "assessable_from_this_image": ["Area (surface extent only)"],
                "requires_clinical_examination": [
                    "Site (confirm anatomically)",
                    "Ischaemia (pulses, ABPI or toe pressures)",
                    "Neuropathy (10 g monofilament, vibration)",
                    "Bacterial infection (clinical signs, swab)",
                    "Depth (probe-to-bone)",
                ],
                "note": "5 of 6 SINBAD components cannot be obtained from a "
                        "photograph. No SINBAD score is produced.",
            },
            "Wagner": {
                "assessable_from_this_image": [],
                "note": "Wagner grading is depth-based and starts at the "
                        "question of whether the ulcer penetrates to tendon, "
                        "capsule or bone. A photograph cannot answer that, so "
                        "no Wagner grade is produced.",
            },
        },
        ask_and_check=[
            "Pulses (dorsalis pedis, posterior tibial) and capillary refill.",
            "Protective sensation with a 10 g monofilament at standard sites.",
            "Probe-to-bone if there is an open wound.",
            "Fever, rigors, malaise, or rapidly spreading redness.",
            "Glycaemic control, and how long the lesion has been present.",
            "Previous ulcer or amputation, smoking, renal disease.",
            "Always inspect the OTHER foot and between all toes.",
        ],
        not_assessable=[
            "Whether tissue is viable. A photograph cannot separate eschar "
            "from shadow, bruising or pigmentation — only inspection can.",
            "Wound depth and whether bone is involved.",
            "Infection, osteomyelitis, or abscess.",
            "Arterial perfusion and tissue viability.",
            "Neuropathy.",
        ],
    )

    if nec >= 1.5:
        ctx.considerations.append(Consideration(
            pattern="Area markedly darker than the surrounding skin",
            overlaps_with=[
                "SHADOW — the commonest explanation by far, especially between "
                "toes, under an arch, or in raking light",
                "normal pigmentation, a callus, or a healing bruise",
                "dressing residue, iodine, henna or another topical dye",
                "haematoma under a callus",
                "eschar or dry gangrene",
                "deep tissue pressure injury",
            ],
            distinguished_by="RE-IMAGE IN EVEN, INDIRECT LIGHT FIRST — a dark "
                             "area that moves or disappears was shadow. If it "
                             "persists, direct inspection with debridement of "
                             "overlying callus by a trained clinician, "
                             "perfusion assessment (pulses, ABPI, toe "
                             "pressures), and imaging where osteomyelitis is "
                             "suspected.",
        ))
    if brk >= 0.4:
        ctx.considerations.append(Consideration(
            pattern="Open wound bed with slough on the surface",
            overlaps_with=[
                "neuropathic (plantar, punched-out) ulcer",
                "ischaemic ulcer",
                "neuroischaemic ulcer",
                "pressure or footwear-related ulceration",
                "traumatic wound or burn",
            ],
            distinguished_by="Site and margin pattern on examination, "
                             "monofilament testing, pulses and ABPI. These "
                             "differ in management, and only examination "
                             "separates them.",
        ))
    if ery >= 4.0:
        ctx.considerations.append(Consideration(
            pattern="Area of surface erythema",
            overlaps_with=[
                "cellulitis",
                "acute Charcot neuroarthropathy",
                "dependent rubor of critical ischaemia",
                "gout or inflammatory arthropathy",
                "pressure erythema or a reaction to footwear",
            ],
            distinguished_by="Skin temperature difference between feet, "
                             "whether the redness settles on elevation, "
                             "systemic signs, inflammatory markers, and "
                             "imaging. Charcot and cellulitis look alike in a "
                             "photograph and are managed very differently.",
        ))
    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No discrete surface abnormality isolated",
            overlaps_with=[
                "intact skin",
                "an early lesion below the resolution or contrast of this image",
                "a lesion outside the photographed field",
            ],
            distinguished_by="Structured foot examination, which also covers "
                             "perfusion and sensation that no photograph shows.",
        ))

    if grade in (Grade.REVIEW, Grade.URGENT):
        ctx.immediate_actions = [
            "Stop weight-bearing on the affected foot and offload it while the "
            "referral is arranged.",
            "Remove tight or rubbing footwear and any constricting sock.",
            "Keep the area clean and dry. Cover with a simple dry dressing.",
            "Do NOT debride, cut, or use corn removers, and do NOT apply heat "
            "or a hot-water bottle.",
            "Do not soak the foot.",
            "Escalate the same day if there is fever, spreading redness, foul "
            "odour, or the foot becomes cold, pale or acutely painful.",
        ]
    elif grade is Grade.MONITOR:
        ctx.immediate_actions = [
            "Offload and change footwear; recheck the area daily.",
            "Do not apply heat or attempt to trim callus.",
            "Seek review sooner if the area opens, spreads, or discharges.",
        ]
    else:
        ctx.immediate_actions = [
            "Continue daily foot inspection, including between the toes and "
            "the other foot.",
            "Well-fitting footwear; never walk barefoot.",
        ]
    return ctx




def build(module: str, grade: Grade, features: dict[str, Any],
          lesions: list[Lesion] | None = None) -> ClinicalContext | None:
    """Entry point. Returns None for modules without a clinical layer yet."""
    builders = {"foot": _foot}
    builder = builders.get(module)
    return builder(grade, features) if builder else None
