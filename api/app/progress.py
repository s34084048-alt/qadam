"""Whether the wound is closing: area measured across visits.

THE ONE THING A CAMERA IS ACTUALLY GOOD FOR HERE.

"Is this necrotic?" is a judgement, and this project measured the ceiling on
getting it from colour thresholds: every fix bought one error with the other.
"Is it smaller than it was three weeks ago?" is a MEASUREMENT of the same
patient, the same site, against a card of known size — a difference rather than
a classification, and difference is the tractable problem.

It is also the established one. Percentage area reduction over roughly four
weeks is a published prognostic indicator in wound care: a wound that has not
reduced by about half in that time is unlikely to heal on its current
management and warrants reassessment. That is a prompt to look again, not a
diagnosis, and it is what this module produces.

WHAT IT REFUSES TO DO
---------------------
Compare percentages. An area given as "% of the imaged region" changes when the
camera moves and the wound does not, so two such numbers cannot be subtracted.
Only measurements in cm², taken with a size reference in the frame, are
compared here; everything else is listed as excluded, with the reason.

It also does not route. The wound outline comes from the same segmentation that
proved unreliable at classification, so an area inherits that unreliability
even when the ruler is exact. The trend is shown to a clinician and prompts a
reassessment; it does not change a grade by itself. See app/routing.py.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# The wound bed itself -- the open surface -- is what "wound area" means, so it
# is the default. The others are selectable because a dry eschar is measured as
# a dark area rather than as a bed, and a clinician tracking one should be able
# to keep tracking it.
PRIMARY_MEASURE = "breakdown_pct"
MEASURES = ("breakdown_pct", "dark_area_pct", "erythema_pct")


class UnknownMeasure(ValueError):
    pass

# Published prognostic threshold: about half, by about four weeks.
PAR_WINDOW_DAYS = 28
PAR_TARGET_PCT = 50.0
# Below this the two visits are too close together for the trend to mean much.
MIN_DAYS_BETWEEN = 3

NOT_A_DIAGNOSIS = (
    "A change in measured surface area. It is not a diagnosis, it says nothing "
    "about depth, infection or perfusion, and it does not by itself change how "
    "this case is routed."
)


@dataclass(slots=True)
class Point:
    at: dt.datetime
    area_cm2: float
    analysis_id: str

    def to_json(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(timespec="minutes"),
            "area_cm2": round(self.area_cm2, 3),
            "analysis_id": self.analysis_id,
        }


@dataclass(slots=True)
class Progress:
    measure: str = PRIMARY_MEASURE
    comparable: bool = False
    points: list[Point] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    change: dict[str, Any] | None = None
    prompt: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "measure": self.measure,
            "comparable": self.comparable,
            "points": [p.to_json() for p in self.points],
            "excluded": list(self.excluded),
            "not_a_diagnosis": NOT_A_DIAGNOSIS,
            "derived_from_image": True,
            "routes_nothing": True,
        }
        if self.reason:
            out["reason"] = self.reason
        if self.change:
            out["change"] = self.change
        if self.prompt:
            out["prompt"] = self.prompt
        return out


def _area_cm2(features: dict[str, Any], measure: str) -> float | None:
    measurement = (features or {}).get("measurement") or {}
    if not measurement.get("comparable_between_visits"):
        return None
    entry = (measurement.get("areas") or {}).get(measure)
    if not entry or "cm2" not in entry:
        return None
    return float(entry["cm2"])


def _utc(value: dt.datetime) -> dt.datetime:
    """Normalise to an aware UTC datetime.

    SQLite hands back NAIVE datetimes while the application writes aware ones,
    so a series can mix the two and comparing them raises. Every unit test here
    built aware datetimes and none of them caught it; the API did, immediately.
    """
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def _why_excluded(features: dict[str, Any]) -> str:
    measurement = (features or {}).get("measurement") or {}
    scale = measurement.get("scale") or {}
    return scale.get("reason") or (
        "No size reference in this image, so its area is a percentage of the "
        "imaged region and cannot be compared with another visit."
    )


def build(analyses: list[dict[str, Any]], measure: str = PRIMARY_MEASURE) -> Progress:
    """`analyses` is [{id, created_at, features}], any order.

    ONE measure for the whole series, never whichever happens to be non-zero.
    Silently switching between slough at one visit and eschar at the next would
    produce a trend line out of two different things.
    """
    if measure not in MEASURES:
        raise UnknownMeasure(measure)
    progress = Progress(measure=measure)

    for row in sorted(analyses, key=lambda r: _utc(r["created_at"])):
        area = _area_cm2(row.get("features") or {}, measure)
        if area is None:
            progress.excluded.append({
                "analysis_id": str(row["id"]),
                "at": _utc(row["created_at"]).isoformat(timespec="minutes"),
                "reason": _why_excluded(row.get("features") or {}),
            })
            continue
        progress.points.append(
            Point(at=_utc(row["created_at"]), area_cm2=area,
                  analysis_id=str(row["id"]))
        )

    if len(progress.points) < 2:
        progress.reason = (
            "At least two photographs with a size reference in the frame are "
            "needed before areas can be compared. "
            f"{len(progress.points)} of {len(analyses)} qualify."
        )
        return progress

    first, last = progress.points[0], progress.points[-1]
    days = (last.at - first.at).total_seconds() / 86400.0
    if days < MIN_DAYS_BETWEEN:
        progress.reason = (
            f"The two measurements are {days:.1f} days apart. A wound does not "
            "change measurably that quickly, and the difference would be "
            "measurement noise rather than healing."
        )
        return progress

    progress.comparable = True
    absolute = last.area_cm2 - first.area_cm2
    par = (
        ((first.area_cm2 - last.area_cm2) / first.area_cm2) * 100.0
        if first.area_cm2 > 0 else None
    )

    progress.change = {
        "baseline": first.to_json(),
        "latest": last.to_json(),
        "days_between": round(days, 1),
        "absolute_cm2": round(absolute, 3),
        "percent_area_reduction": round(par, 1) if par is not None else None,
        "direction": (
            "smaller" if absolute < 0 else "larger" if absolute > 0 else "unchanged"
        ),
    }
    progress.prompt = _prompt(days, par)
    return progress


def _prompt(days: float, par: float | None) -> dict[str, Any]:
    """The four-week rule, stated as what it is: a reason to look again."""
    basis = (
        "Percentage area reduction of roughly 50% by about four weeks is a "
        "published prognostic indicator: wounds that fall short of it are "
        "unlikely to heal on their current management."
    )
    if par is None:
        return {"action": "none", "basis": basis,
                "detail": "No measurable area at the first visit to compare against."}

    if days < PAR_WINDOW_DAYS:
        return {
            "action": "too_early",
            "basis": basis,
            "detail": (
                f"{days:.0f} days since the first measurement. The four-week "
                "point has not been reached, so no conclusion is drawn from "
                "the trend yet."
            ),
        }

    if par >= PAR_TARGET_PCT:
        return {
            "action": "on_track",
            "basis": basis,
            "detail": (
                f"Area is {par:.0f}% smaller after {days:.0f} days, which meets "
                "the expected trajectory. Continue current management and "
                "surveillance."
            ),
        }

    return {
        "action": "reassess",
        "basis": basis,
        "detail": (
            f"Area is {par:.0f}% smaller after {days:.0f} days, short of the "
            "expected reduction. This is a prompt to reassess what is "
            "preventing healing — offloading, perfusion, infection — not a "
            "finding about any of them, and not a change to this case's "
            "routing."
        ),
    }
