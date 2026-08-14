"""Where a case is routed, and what that decision may rest on.

The property under test is a NEGATIVE one: the photograph is not an input.

It used to be. The follow-up outcome was max(image grade, answer grade), which
made a hand-tuned colour threshold a term in a clinical decision. This project
then measured the ceiling on those thresholds directly — raising the skin
reference to catch a wound filling the frame brought back the false "necrotic
tissue on a healthy toe"; lowering it again brought back the silent miss. Each
fix bought one error with the other.

So routing now combines two things a clinician obtained with their hands:
the IWGDF risk category, and the follow-up answers.
"""

from __future__ import annotations

import pytest

from app import routing
from app.analysis import followup
from app.analysis.types import Grade
from app.sample_data import png_bytes
from tests.conftest import API, make_case, make_patient


def _foot(grade: str, category=1):
    return {"grade": grade, "category": category,
            "screening_interval": "Every 6-12 months"}


def _answers(grade: str, triggers=()):
    return {"answer_grade": grade,
            "triggers": [{"finding": t} for t in triggers]}


# --- the image is not an input ------------------------------------------------

def test_the_follow_up_grade_does_not_take_the_image(monkeypatch):
    """evaluate() no longer accepts an image grade at all, so there is no
    parameter through which one could be reintroduced by accident."""
    import inspect

    params = inspect.signature(followup.evaluate).parameters
    assert "image_grade" not in params
    assert set(params) == {"module", "answers"}


def test_routing_declares_that_it_excludes_the_image():
    body = routing.decide(_foot("review"), _answers("no_flag")).to_json()
    assert body["derived_from_image"] is False
    assert "does not contribute" in body["image_note"]
    for entry in body["basis"]:
        assert entry["source"] in ("iwgdf_risk_category", "follow_up_answers")


def test_an_urgent_photograph_cannot_route_the_case():
    """Nothing about the image reaches decide(); this pins that structurally."""
    import inspect

    params = inspect.signature(routing.decide).parameters
    assert set(params) == {"foot_risk", "follow_up"}


# --- the combination ---------------------------------------------------------

@pytest.mark.parametrize("foot_grade,answer_grade,expected", [
    ("no_flag", "no_flag", Grade.NO_FLAG),
    ("review", "no_flag", Grade.REVIEW),
    ("no_flag", "urgent", Grade.URGENT),
    ("review", "urgent", Grade.URGENT),
    ("urgent", "review", Grade.URGENT),
    ("monitor", "review", Grade.REVIEW),
])
def test_the_more_urgent_of_the_two_wins(foot_grade, answer_grade, expected):
    decision = routing.decide(_foot(foot_grade), _answers(answer_grade))
    assert decision.assessed is True
    assert decision.grade is expected


def test_either_source_alone_still_routes():
    assert routing.decide(_foot("review"), None).grade is Grade.REVIEW
    assert routing.decide(None, _answers("urgent")).grade is Grade.URGENT


def test_a_single_source_says_what_is_missing():
    decision = routing.decide(_foot("review"), None)
    assert decision.assessed is True
    assert any("follow-up" in m.lower() for m in decision.missing)

    decision = routing.decide(None, _answers("review"))
    assert any("examination" in m.lower() for m in decision.missing)


# --- nothing assessed is not no flag -----------------------------------------

def test_an_unassessed_case_is_not_reported_as_low_risk():
    """The most dangerous output this layer could produce. `no_flag` on a case
    nobody has examined reads as reassurance."""
    decision = routing.decide(None, None)
    assert decision.assessed is False
    assert decision.grade is None

    body = decision.to_json()
    assert body["grade"] == "not_assessed"
    assert body["grade"] != "no_flag"
    assert "NOT a low-risk result" in body["note"]
    assert len(body["missing"]) == 2


def test_an_unassessed_case_carries_no_colour():
    """No grade colour, so no interface can paint it green."""
    assert "color" not in routing.decide(None, None).to_json()


# --- every routed grade points somewhere real --------------------------------

@pytest.mark.parametrize("grade", ["no_flag", "monitor", "review", "urgent"])
def test_every_grade_routes_to_a_real_destination(grade):
    body = routing.decide(_foot(grade), None).to_json()
    assert body["routing_target"].strip()
    assert body["next_investigation"].strip()
    assert body["urgency"].strip()
    assert body["color"].startswith("#")


# --- through the API ----------------------------------------------------------

async def test_a_new_case_is_not_assessed(client, auth, ref_factory):
    ref = ref_factory("route")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    body = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert body["routing"]["grade"] == "not_assessed"
    assert body["routing"]["assessed"] is False


async def test_analysing_a_photograph_does_not_route_the_case(
    client, auth, ref_factory
):
    """The whole point, end to end: an image that the CV layer calls urgent
    leaves the case unassessed, because nobody has examined the patient."""
    ref = ref_factory("route")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    analysis = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["triage"]["grade"] == "urgent"

    body = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert body["routing"]["grade"] == "not_assessed", (
        "the photograph routed the case"
    )
    assert body["routing"]["derived_from_image"] is False


async def test_the_examination_routes_the_case(client, auth, ref_factory):
    ref = ref_factory("route")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.post(
        f"{API}/cases/{case_id}/foot-risk", headers=auth,
        json={"lops": "present", "pad": "absent"},
    )
    assert resp.status_code == 201, resp.text

    body = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert body["routing"]["assessed"] is True
    assert body["routing"]["grade"] != "not_assessed"
    assert any(b["source"] == "iwgdf_risk_category"
               for b in body["routing"]["basis"])


async def test_answers_route_the_case(client, auth, ref_factory):
    ref = ref_factory("route")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"probe_to_bone": "yes"}},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["answer_grade"] == "urgent"

    body = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert body["routing"]["grade"] == "urgent"
    assert any(b["source"] == "follow_up_answers"
               for b in body["routing"]["basis"])
