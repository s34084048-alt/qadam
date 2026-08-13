"""Clinician follow-up answers and the re-assessment they drive.

The property under test is the ASYMMETRY. Answers may raise the routing grade
and must never lower it. Everything else here exists to make sure that property
cannot be reached around: unknown fields are rejected rather than dropped,
out-of-vocabulary values are refused, and no rule ever emits a treatment.
"""

from __future__ import annotations

import uuid as uuidlib

import pytest

from app.analysis import followup
from app.analysis.types import Grade
from app.sample_data import png_bytes
from tests.conftest import API, make_case, make_patient
from tests.test_safety_boundary import (_assert_no_forbidden_claims,
                                        assert_no_treatment_instruction)


async def _case(client, auth, ref_factory, module: str = "foot") -> str:
    ref = ref_factory("fu")
    await make_patient(client, auth, ref)
    return await make_case(client, auth, ref, module)


async def _analysed_case(client, auth, ref_factory, sample: str,
                         module: str = "foot") -> tuple[str, str]:
    case_id = await _case(client, auth, ref_factory, module)
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes(sample), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return case_id, resp.json()["triage"]["grade"]


# --- the combination rule ----------------------------------------------------

@pytest.mark.parametrize(
    "image_grade,answers,expected",
    [
        # Answers escalate.
        (Grade.NO_FLAG, {"probe_to_bone": "yes"}, Grade.URGENT),
        (Grade.NO_FLAG, {"monofilament": "absent"}, Grade.REVIEW),
        (Grade.MONITOR, {"systemic_signs": "yes"}, Grade.URGENT),
        # Answers NEVER de-escalate, however reassuring they are.
        (Grade.URGENT,
         {"pedal_pulses": "both_palpable", "monofilament": "intact",
          "probe_to_bone": "no", "systemic_signs": "no",
          "spreading_erythema": "no", "crepitus_odour_bullae": "no",
          "rest_pain": "no", "hot_swollen_no_wound": "no",
          "duration_weeks": 1},
         Grade.URGENT),
        (Grade.REVIEW, {"pedal_pulses": "both_palpable"}, Grade.REVIEW),
        # No answers at all leaves the image grade untouched.
        (Grade.MONITOR, {}, Grade.MONITOR),
    ],
)
def test_combined_grade_is_the_more_urgent_of_the_two(image_grade, answers,
                                                      expected):
    outcome = followup.evaluate("foot", image_grade, answers)
    assert outcome.combined_grade is expected


@pytest.mark.parametrize("module", sorted(followup.QUESTIONS))
def test_no_answer_set_can_lower_a_grade(module):
    """Exhaustive over every single-answer combination in every module.

    A rule added later that happens to return a grade below the image grade
    would be caught here rather than in a clinic.
    """
    for question in followup.questions_for(module):
        values = question.options or [0, 1, 5, 50, 99]
        for value in values:
            for image_grade in Grade:
                outcome = followup.evaluate(
                    module, image_grade, {question.id: value})
                assert outcome.combined_grade.rank >= image_grade.rank, (
                    f"{module}.{question.id}={value} lowered "
                    f"{image_grade} to {outcome.combined_grade}"
                )


def test_reassuring_answers_are_still_recorded():
    """De-escalation is refused, but the finding is not thrown away."""
    outcome = followup.evaluate(
        "foot", Grade.URGENT,
        {"pedal_pulses": "both_palpable", "monofilament": "intact"},
    )
    assert outcome.combined_grade is Grade.URGENT
    assert outcome.answered["pedal_pulses"] == "both_palpable"
    assert outcome.answer_grade is Grade.NO_FLAG
    assert outcome.escalated is False


def test_not_tested_is_recorded_as_such_not_as_negative():
    outcome = followup.evaluate(
        "foot", Grade.NO_FLAG,
        {"monofilament": "not_tested", "probe_to_bone": "not_tested"},
    )
    assert outcome.combined_grade is Grade.NO_FLAG
    assert set(outcome.not_tested) == {"monofilament", "probe_to_bone"}
    # An untested test produces no trigger -- it is neither positive nor
    # negative, and must not be scored as either.
    assert outcome.triggers == []


def test_combination_rule_rest_pain_with_absent_pulses_is_more_urgent():
    """Rest pain alone routes to review; with an absent pulse it is urgent."""
    alone = followup.evaluate("foot", Grade.NO_FLAG, {"rest_pain": "yes"})
    combined = followup.evaluate(
        "foot", Grade.NO_FLAG,
        {"rest_pain": "yes", "pedal_pulses": "both_absent"})
    assert alone.combined_grade is Grade.REVIEW
    assert combined.combined_grade is Grade.URGENT


# --- validation --------------------------------------------------------------

def test_unknown_field_is_rejected_not_ignored():
    with pytest.raises(followup.UnknownFollowUpField):
        followup.evaluate("foot", Grade.NO_FLAG, {"blood_pressure": "120/80"})


def test_out_of_vocabulary_value_is_rejected():
    with pytest.raises(followup.InvalidFollowUpAnswer):
        followup.evaluate("foot", Grade.NO_FLAG, {"pedal_pulses": "maybe"})


def test_non_numeric_answer_to_a_number_question_is_rejected():
    with pytest.raises(followup.InvalidFollowUpAnswer):
        followup.evaluate("foot", Grade.NO_FLAG, {"duration_weeks": "ages"})


def test_blank_answers_are_dropped_rather_than_stored():
    outcome = followup.evaluate(
        "foot", Grade.NO_FLAG, {"pedal_pulses": "", "rest_pain": None})
    assert outcome.answered == {}
    assert "pedal_pulses" in outcome.unanswered


# --- the safety boundary, inside this new surface ----------------------------

@pytest.mark.parametrize("module", sorted(followup.QUESTIONS))
def test_no_trigger_recommends_treatment_or_medication(module):
    for question in followup.questions_for(module):
        for value in (question.options or [99]):
            outcome = followup.evaluate(module, Grade.NO_FLAG,
                                        {question.id: value})
            for trigger in outcome.triggers:
                blob = " ".join([
                    trigger.finding, trigger.because,
                    trigger.distinguished_by, *trigger.consider,
                ])
                assert_no_treatment_instruction(
                    blob, f"{module}.{question.id}={value}")


@pytest.mark.parametrize("module", sorted(followup.QUESTIONS))
def test_no_trigger_asserts_an_internal_diagnosis(module):
    for question in followup.questions_for(module):
        for value in (question.options or [99]):
            outcome = followup.evaluate(module, Grade.NO_FLAG,
                                        {question.id: value})
            for trigger in outcome.triggers:
                for text in (trigger.finding, trigger.because,
                             trigger.distinguished_by):
                    _assert_no_forbidden_claims(
                        text, f"{module}.{question.id}={value}")


@pytest.mark.parametrize("module", sorted(followup.QUESTIONS))
def test_every_trigger_offers_a_differential_and_a_discriminator(module):
    """Same rule as the clinical layer: never a single possibility asserted."""
    for question in followup.questions_for(module):
        for value in (question.options or [99]):
            outcome = followup.evaluate(module, Grade.NO_FLAG,
                                        {question.id: value})
            for trigger in outcome.triggers:
                assert len(trigger.consider) >= 2, (
                    f"{module}.{question.id} offers a single possibility: "
                    f"{trigger.consider}"
                )
                assert trigger.distinguished_by.strip()


@pytest.mark.parametrize("module", sorted(followup.QUESTIONS))
def test_every_question_explains_why_it_is_asked(module):
    for question in followup.questions_for(module):
        assert question.why.strip(), f"{module}.{question.id} has no rationale"
        if question.kind == "choice":
            assert question.options, f"{module}.{question.id} has no options"


def test_clinical_tests_always_offer_a_not_tested_option():
    """A form that forces yes/no for a test nobody did manufactures data."""
    for qid in ("probe_to_bone", "monofilament", "pedal_pulses"):
        question = next(q for q in followup.questions_for("foot") if q.id == qid)
        assert "not_tested" in question.options


# --- the API -----------------------------------------------------------------

async def test_questions_endpoint_publishes_the_rule(client, auth):
    resp = await client.get(f"{API}/follow-up/questions/foot", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["questions"]) >= 5
    assert "never lower" in body["combination_rule"]
    assert body["safety"]["clinical_use"] is False


async def test_answers_escalate_a_stored_case(client, auth, ref_factory):
    case_id, image_grade = await _analysed_case(
        client, auth, ref_factory, "foot_clean")
    assert image_grade == "no_flag"

    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"probe_to_bone": "yes", "systemic_signs": "yes"},
              "note": "Wound over the 1st MTP, present since Ramadan."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["image_grade"] == "no_flag"
    assert body["combined_grade"] == "urgent"
    assert body["escalated"] is True
    assert body["note"].startswith("Wound over")
    assert body["safety"]["clinical_use"] is False
    assert len(body["outcome"]["triggers"]) == 2


async def test_answers_do_not_de_escalate_a_stored_case(client, auth,
                                                        ref_factory):
    case_id, image_grade = await _analysed_case(
        client, auth, ref_factory, "foot_urgent")
    assert image_grade == "urgent"

    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"pedal_pulses": "both_palpable",
                          "monofilament": "intact",
                          "systemic_signs": "no"}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["answer_grade"] == "no_flag"
    assert body["combined_grade"] == "urgent"
    assert body["escalated"] is False


async def test_note_alone_is_accepted(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"note": "Patient declined the monofilament test today."},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["combined_grade"] == "no_flag"


async def test_unknown_field_returns_an_actionable_error(client, auth,
                                                         ref_factory):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"blood_sugar": "high"}},
    )
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "unknown_follow_up_field"
    assert "pedal_pulses" in error["details"]["allowed"]


async def test_answers_attach_to_a_named_analysis(client, auth, ref_factory):
    case_id, _ = await _analysed_case(client, auth, ref_factory, "foot_clean")
    detail = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    analysis_id = detail["latest_analysis"]["id"]

    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"rest_pain": "yes"}, "analysis_id": analysis_id},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["analysis_id"] == analysis_id


async def test_analysis_from_another_case_is_refused(client, auth, ref_factory):
    first, _ = await _analysed_case(client, auth, ref_factory, "foot_clean")
    second = await _case(client, auth, ref_factory)
    detail = (await client.get(f"{API}/cases/{first}", headers=auth)).json()

    resp = await client.post(
        f"{API}/cases/{second}/follow-up", headers=auth,
        json={"answers": {"rest_pain": "yes"},
              "analysis_id": detail["latest_analysis"]["id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "analysis_not_found"


async def test_lab_module_has_no_follow_up_set(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory, "lab")
    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {}, "note": "x"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_follow_up_questions"


async def test_entries_are_listed_newest_first(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    for weeks in (2, 8):
        resp = await client.post(
            f"{API}/cases/{case_id}/follow-up", headers=auth,
            json={"answers": {"duration_weeks": weeks}},
        )
        assert resp.status_code == 201, resp.text

    listing = await client.get(f"{API}/cases/{case_id}/follow-up", headers=auth)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    assert body["entries"][0]["answers"]["duration_weeks"] == 8
    assert body["questions"]


async def test_follow_up_reaches_the_pdf(client, auth, ref_factory):
    case_id, _ = await _analysed_case(client, auth, ref_factory, "foot_clean")
    await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"probe_to_bone": "yes"},
              "note": "Probe reached bone at the heel."},
    )
    resp = await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    # A summary that silently drops what the clinician examined is not the
    # record of the visit.
    assert len(resp.content) > 4000


async def test_audit_records_the_grade_but_not_the_note(client, auth,
                                                        ref_factory):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuditLog

    case_id = await _case(client, auth, ref_factory)
    secret = "Patient works at the airport and is scared of amputation."
    await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"systemic_signs": "yes"}, "note": secret},
    )

    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.action == "follow_up.create")
        )).scalars().all()

    assert rows, "no audit entry recorded"
    blob = str([row.meta_json for row in rows])
    assert "urgent" in blob                      # the decision is auditable
    assert "airport" not in blob                 # the clinical prose is not
    assert "systemic_signs" not in blob          # nor are the answer values


async def test_follow_up_for_an_unknown_case_is_404(client, auth):
    resp = await client.post(
        f"{API}/cases/{uuidlib.uuid4()}/follow-up", headers=auth,
        json={"answers": {"rest_pain": "yes"}},
    )
    assert resp.status_code == 404
