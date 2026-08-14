"""Recorded disagreement — the validation dataset, one row at a time.

Every real defect this platform has had was found by a person looking at a real
photograph: a healthy toe called necrotic, a shadow read as tissue, callus
counted as a wound. None was found by the test suite. This is where those
reports are meant to land instead of scattering across messages.

The property that matters most is a NEGATIVE one: leaving feedback changes
nothing. No grade moves and no threshold adapts.
"""

from __future__ import annotations

import pytest

from app.sample_data import png_bytes
from tests.conftest import API, make_case, make_patient


async def _analysed(client, auth, ref_factory) -> tuple[str, str, str]:
    ref = ref_factory("fb")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return case_id, body["id"], body["triage"]["grade"]


# --- recording ----------------------------------------------------------------

async def test_a_disagreement_is_recorded_with_what_was_reported(
    client, auth, ref_factory
):
    case_id, analysis_id, grade = await _analysed(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/feedback", headers=auth,
        json={"analysis_id": analysis_id, "verdict": "too_high",
              "ground_truth": "callus",
              "note": "Thick callus over the 1st MTP, skin intact."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # The reported grade and model are COPIED, so the row still means something
    # after a re-analysis or a threshold change.
    assert body["reported_grade"] == grade
    assert body["model_version"].startswith("classical-cv")
    assert body["verdict_label"] == "It was more alarming than what I saw."
    assert body["ground_truth_label"].startswith("Callus")


@pytest.mark.parametrize("verdict", ["agree", "too_high", "too_low",
                                     "unusable_image"])
async def test_every_verdict_is_accepted(client, auth, ref_factory, verdict):
    case_id, analysis_id, _ = await _analysed(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/feedback", headers=auth,
        json={"analysis_id": analysis_id, "verdict": verdict},
    )
    assert resp.status_code == 201, resp.text


async def test_an_unknown_verdict_is_refused(client, auth, ref_factory):
    case_id, analysis_id, _ = await _analysed(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/feedback", headers=auth,
        json={"analysis_id": analysis_id, "verdict": "sort_of"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_verdict"


async def test_feedback_must_name_an_analysis_on_this_case(
    client, auth, ref_factory
):
    """It is left against a specific result, so the image and its measurements
    can be looked at later alongside it."""
    _first_case, first_analysis, _ = await _analysed(client, auth, ref_factory)
    second_case, _second_analysis, _ = await _analysed(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{second_case}/feedback", headers=auth,
        json={"analysis_id": first_analysis, "verdict": "agree"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "analysis_not_found"


# --- it changes nothing --------------------------------------------------------

async def test_feedback_does_not_move_the_grade(client, auth, ref_factory):
    """THE PROPERTY THAT MATTERS. A system that retunes itself on unvalidated
    corrections is a system whose behaviour nobody can state."""
    case_id, analysis_id, grade = await _analysed(client, auth, ref_factory)
    for _ in range(3):
        await client.post(
            f"{API}/cases/{case_id}/feedback", headers=auth,
            json={"analysis_id": analysis_id, "verdict": "too_high",
                  "ground_truth": "intact_skin"},
        )

    detail = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert detail["latest_analysis"]["triage"]["grade"] == grade
    # And the case routing is still what the examination says, which is nothing.
    assert detail["routing"]["grade"] == "not_assessed"


async def test_feedback_does_not_change_a_later_analysis(
    client, auth, ref_factory
):
    case_id, analysis_id, grade = await _analysed(client, auth, ref_factory)
    await client.post(
        f"{API}/cases/{case_id}/feedback", headers=auth,
        json={"analysis_id": analysis_id, "verdict": "too_high",
              "ground_truth": "intact_skin"},
    )
    again = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert again.json()["triage"]["grade"] == grade


async def test_the_listing_says_it_changes_nothing(client, auth, ref_factory):
    case_id, _analysis_id, _ = await _analysed(client, auth, ref_factory)
    body = (await client.get(f"{API}/cases/{case_id}/feedback",
                             headers=auth)).json()
    assert "changes a grade" in body["note"]
    assert set(body["verdicts"]) == {"agree", "too_high", "too_low",
                                     "unusable_image"}


# --- isolation and deletion ----------------------------------------------------

async def test_another_organisation_cannot_leave_or_read_feedback(
    client, auth, other_auth, ref_factory
):
    case_id, analysis_id, _ = await _analysed(client, auth, ref_factory)
    post = await client.post(
        f"{API}/cases/{case_id}/feedback", headers=other_auth,
        json={"analysis_id": analysis_id, "verdict": "agree"},
    )
    assert post.status_code == 404
    get = await client.get(f"{API}/cases/{case_id}/feedback", headers=other_auth)
    assert get.status_code == 404


async def test_deleting_a_case_removes_its_feedback(client, auth, ref_factory):
    case_id, analysis_id, _ = await _analysed(client, auth, ref_factory)
    await client.post(
        f"{API}/cases/{case_id}/feedback", headers=auth,
        json={"analysis_id": analysis_id, "verdict": "agree"},
    )
    resp = await client.delete(f"{API}/cases/{case_id}?confirm=true",
                               headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["feedback"] == 1


# --- the summary ----------------------------------------------------------------

async def test_the_summary_refuses_to_call_itself_a_validation_study(
    client, auth, admin_auth, ref_factory
):
    case_id, analysis_id, _ = await _analysed(client, auth, ref_factory)
    await client.post(
        f"{API}/cases/{case_id}/feedback", headers=auth,
        json={"analysis_id": analysis_id, "verdict": "too_high",
              "ground_truth": "callus"},
    )
    body = (await client.get(f"{API}/admin/feedback", headers=admin_auth)).json()
    assert body["total"] >= 1
    assert body["by_verdict"].get("too_high", 0) >= 1
    assert "urgent" in body["reported_grade_vs_ground_truth"]

    # It states what it is NOT, in the same payload.
    assert "Not a validation study" in body["what_this_is_not"]
    assert "no protocol" in body["what_this_is_not"]
    assert "cannot state how often it is right" in body["what_this_is_not"]
    assert "sample size fixed in advance" in body["what_would_make_it_one"]
    assert body["safety"]["clinical_use"] is False


async def test_a_clinician_cannot_read_the_summary(client, auth):
    assert (await client.get(f"{API}/admin/feedback",
                             headers=auth)).status_code == 403
