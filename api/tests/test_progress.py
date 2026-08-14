"""Wound area across visits.

This is the one thing a camera contributes that a general model cannot: the
same patient, the same site, measured against a card of known size, over time.
It is also the only image-derived number here that corresponds to an
established clinical indicator — percentage area reduction of roughly half by
about four weeks.

The failures it must not have:

  * subtracting two percentages, which measures the camera's position rather
    than the wound;
  * reading a trend out of two photographs taken minutes apart;
  * turning a measurement into a diagnosis, or into a routing change.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuidlib

import pytest

from app import progress as progress_mod


def _analysis(days_ago: float, area_cm2: float | None, *,
              scale_reason: str | None = None) -> dict:
    at = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=days_ago)
    if area_cm2 is None:
        measurement = {
            "comparable_between_visits": False,
            "scale": {"available": False,
                      "reason": scale_reason or "No size reference in the frame."},
            "areas": {"breakdown_pct": {"percent_of_region": 4.0}},
        }
    else:
        measurement = {
            "comparable_between_visits": True,
            "scale": {"available": True, "mm_per_px": 0.3},
            "areas": {"breakdown_pct": {"percent_of_region": 4.0,
                                        "cm2": area_cm2}},
        }
    return {"id": uuidlib.uuid4(), "created_at": at,
            "features": {"measurement": measurement}}


# --- refusing to compare what cannot be compared ------------------------------

def test_percentages_without_a_size_reference_are_excluded():
    """Two percentages cannot be subtracted: moving the camera changes them."""
    built = progress_mod.build([_analysis(0, None), _analysis(30, None)])
    assert built.comparable is False
    assert len(built.points) == 0
    assert len(built.excluded) == 2
    assert all("size reference" in e["reason"] for e in built.excluded)


def test_one_calibrated_visit_is_not_a_trend():
    built = progress_mod.build([_analysis(0, 6.0), _analysis(30, None)])
    assert built.comparable is False
    assert "at least two" in built.reason.lower()
    assert "1 of 2 qualify" in built.reason


def test_uncalibrated_visits_are_named_not_silently_dropped():
    built = progress_mod.build([
        _analysis(0, 6.0), _analysis(14, None, scale_reason="The card is tilted."),
        _analysis(30, 3.0),
    ])
    assert built.comparable is True
    assert len(built.points) == 2
    assert built.excluded[0]["reason"] == "The card is tilted."


def test_two_photographs_minutes_apart_are_not_a_trend():
    built = progress_mod.build([_analysis(0, 6.0), _analysis(0.02, 5.4)])
    assert built.comparable is False
    assert "measurement noise" in built.reason


# --- the measurement ----------------------------------------------------------

def test_area_reduction_is_computed_from_cm2():
    built = progress_mod.build([_analysis(0, 8.0), _analysis(28, 3.2)])
    assert built.comparable is True
    change = built.change
    assert change["percent_area_reduction"] == pytest.approx(60.0)
    assert change["absolute_cm2"] == pytest.approx(-4.8)
    assert change["direction"] == "smaller"
    assert change["days_between"] == pytest.approx(28.0)


def test_a_growing_wound_reads_as_larger():
    built = progress_mod.build([_analysis(0, 4.0), _analysis(30, 6.0)])
    assert built.change["direction"] == "larger"
    assert built.change["percent_area_reduction"] == pytest.approx(-50.0)


def test_the_baseline_is_the_earliest_regardless_of_input_order():
    late, early = _analysis(30, 3.0), _analysis(0, 8.0)
    built = progress_mod.build([late, early])
    assert built.change["baseline"]["area_cm2"] == 8.0
    assert built.change["latest"]["area_cm2"] == 3.0


# --- the four-week prompt -----------------------------------------------------

def test_before_four_weeks_no_conclusion_is_drawn():
    built = progress_mod.build([_analysis(0, 8.0), _analysis(10, 7.6)])
    assert built.prompt["action"] == "too_early"
    assert "has not been reached" in built.prompt["detail"]


def test_meeting_the_expected_trajectory_says_continue():
    built = progress_mod.build([_analysis(0, 8.0), _analysis(30, 3.0)])
    assert built.prompt["action"] == "on_track"


def test_falling_short_prompts_reassessment_not_a_finding():
    built = progress_mod.build([_analysis(0, 8.0), _analysis(30, 7.0)])
    prompt = built.prompt
    assert prompt["action"] == "reassess"
    # It names what to look FOR, and disclaims having found any of it.
    assert "offloading" in prompt["detail"]
    assert "not a finding about any of them" in prompt["detail"]
    assert "not a change to this case's routing" in prompt["detail"]


def test_a_zero_baseline_does_not_divide_by_zero():
    built = progress_mod.build([_analysis(0, 0.0), _analysis(30, 2.0)])
    assert built.change["percent_area_reduction"] is None
    assert built.prompt["action"] == "none"


# --- the boundary -------------------------------------------------------------

def test_the_trend_declares_that_it_routes_nothing():
    body = progress_mod.build([_analysis(0, 8.0), _analysis(30, 7.0)]).to_json()
    assert body["routes_nothing"] is True
    assert body["derived_from_image"] is True
    assert "not a diagnosis" in body["not_a_diagnosis"].lower()
    assert "depth, infection or perfusion" in body["not_a_diagnosis"]


def test_no_prompt_asserts_a_cause():
    """"Not healing" has many causes and this measures none of them."""
    from tests.test_safety_boundary import _assert_no_forbidden_claims

    for latest in (7.0, 3.0, 9.0):
        built = progress_mod.build([_analysis(0, 8.0), _analysis(30, latest)])
        _assert_no_forbidden_claims(built.prompt["detail"], "progress prompt")
        _assert_no_forbidden_claims(built.prompt["basis"], "progress basis")


# --- through the API ----------------------------------------------------------

async def test_progress_endpoint_reports_nothing_to_compare(
    client, auth, ref_factory
):
    from tests.conftest import API, make_case, make_patient

    ref = ref_factory("prog")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.get(f"{API}/cases/{case_id}/progress", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["comparable"] is False
    assert body["routes_nothing"] is True
    assert body["safety"]["clinical_use"] is False


async def test_progress_is_scoped_to_the_organisation(
    client, auth, other_auth, ref_factory
):
    from tests.conftest import API, make_case, make_patient

    ref = ref_factory("prog")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.get(f"{API}/cases/{case_id}/progress", headers=other_auth)
    assert resp.status_code == 404


# --- what the unit tests missed and the API found -----------------------------

def test_naive_and_aware_timestamps_can_be_mixed():
    """SQLite returns NAIVE datetimes while the application writes aware ones,
    so a real series mixes the two. Every test above builds aware datetimes and
    none of them caught this; the first live request did, with a 500."""
    naive = _analysis(0, 8.0)
    naive["created_at"] = naive["created_at"].replace(tzinfo=None)
    aware = _analysis(30, 3.0)

    built = progress_mod.build([naive, aware])
    assert built.comparable is True
    assert built.change["percent_area_reduction"] == pytest.approx(62.5)
    assert built.change["days_between"] == pytest.approx(30.0)


def test_a_fully_naive_series_works_too():
    rows = []
    for days, area in ((0, 8.0), (30, 3.0)):
        row = _analysis(days, area)
        row["created_at"] = row["created_at"].replace(tzinfo=None)
        rows.append(row)
    assert progress_mod.build(rows).comparable is True


def test_an_unknown_measure_is_refused():
    with pytest.raises(progress_mod.UnknownMeasure):
        progress_mod.build([], measure="not_a_measure")
