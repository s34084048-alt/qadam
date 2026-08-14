"""Real-world size from a reference card in the frame.

WHY THIS IS THE FOUNDATION OF EVERYTHING ELSE.

Every area this platform measured until now was a PERCENTAGE OF THE SEGMENTED
SUBJECT. That number is meaningless between visits: stand half a metre closer
next week and it changes without the wound changing at all. Serial comparison
built on it would be comparing camera positions, not tissue -- and would do it
with a confident-looking percentage.

Absolute area in cm² is what wound care actually measures, and it needs a
known length in the frame. The reference card already used for colour is that
length. An ISO/IEC 7810 ID-1 card -- any bank or ID card, 85.60 × 53.98 mm to a
tolerance far tighter than this measurement needs -- is the practical choice
because everyone already carries one.

WHAT THIS IS NOT. It is not planimetry and it is not a substitute for a ruler.
It assumes the card lies in the same plane as the wound and roughly square to
the lens. Tilt shortens the card in the image and inflates every derived area,
so the tilt estimate below is reported with the result and a poor one refuses
outright rather than returning a confident wrong number in cm².
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ISO/IEC 7810 ID-1. Bank cards, most national ID cards, most driving licences.
ID1_LONG_MM = 85.60
ID1_SHORT_MM = 53.98
ID1_ASPECT = ID1_LONG_MM / ID1_SHORT_MM          # 1.586

# A card seen at an angle is foreshortened, and every area scales with the
# SQUARE of the length error: a 20% shortening inflates area by ~56%. This is
# tight for that reason.
MAX_ASPECT_ERROR = 0.14
MIN_CARD_LONG_PX = 60                            # below this, one pixel is ~1.4 mm


@dataclass(slots=True)
class Scale:
    """Millimetres per pixel, or an explicit refusal to guess."""

    available: bool = False
    mm_per_px: float = 0.0
    reason: str | None = None
    card_long_px: float = 0.0
    aspect_error: float = 0.0
    reference: str = "ISO/IEC 7810 ID-1 card (85.6 × 54.0 mm)"
    notes: list[str] = field(default_factory=list)

    def area_cm2(self, pixels: float) -> float | None:
        if not self.available:
            return None
        return pixels * (self.mm_per_px ** 2) / 100.0

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "available": self.available,
            "reference": self.reference,
            "how_to": (
                "Lay a bank or ID card flat NEXT TO the wound, in the same "
                "plane and the same light, square to the camera. It sets both "
                "the colour reference and the size reference, so areas can be "
                "reported in cm² and compared with the last visit."
            ),
        }
        if self.available:
            out["mm_per_px"] = round(self.mm_per_px, 4)
            out["card_long_px"] = round(self.card_long_px, 1)
            out["tilt_estimate_pct"] = round(self.aspect_error * 100, 1)
        else:
            out["reason"] = self.reason or (
                "No size reference in the frame. Areas are reported as a "
                "percentage of the imaged region only, and CANNOT be compared "
                "with another visit — moving the camera changes them."
            )
        if self.notes:
            out["notes"] = list(self.notes)
        return out


def from_card(card: dict | None) -> Scale:
    """Derive mm-per-pixel from a detected reference card.

    `card` is the descriptor produced by cv_utils.find_reference_card.
    """
    if not card:
        return Scale(available=False)

    bbox = card.get("bbox")
    if not bbox:
        return Scale(available=False)
    w, h = float(bbox[2]), float(bbox[3])
    if w <= 0 or h <= 0:
        return Scale(available=False)

    long_px, short_px = (w, h) if w >= h else (h, w)
    if long_px < MIN_CARD_LONG_PX:
        return Scale(
            available=False,
            reason=(
                f"The reference card is only {long_px:.0f} px across, too "
                "small to measure from. Move closer, or bring the card nearer "
                "to the wound."
            ),
        )

    seen_aspect = long_px / short_px
    aspect_error = abs(seen_aspect - ID1_ASPECT) / ID1_ASPECT
    if aspect_error > MAX_ASPECT_ERROR:
        return Scale(
            available=False,
            card_long_px=long_px,
            aspect_error=aspect_error,
            reason=(
                "The reference card is not square to the camera (its shape in "
                f"the image is off by {aspect_error * 100:.0f}%). A tilted card "
                "makes every area come out too large, so no size is reported. "
                "Re-take the photograph looking straight down at the card and "
                "the wound together."
            ),
        )

    scale = Scale(
        available=True,
        mm_per_px=ID1_LONG_MM / long_px,
        card_long_px=long_px,
        aspect_error=aspect_error,
    )
    if aspect_error > MAX_ASPECT_ERROR / 2:
        scale.notes.append(
            "The card is slightly tilted; areas may be overstated by roughly "
            f"{((1 / (1 - aspect_error)) ** 2 - 1) * 100:.0f}%."
        )
    return scale
