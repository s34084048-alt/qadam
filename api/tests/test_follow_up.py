"""Clinician follow-up answers and the re-assessment they drive.

These answers are graded on their own. The photograph used to be combined with
them — the outcome was max(image grade, answer grade) — and that made a
hand-tuned colour threshold a term in a clinical decision. It is gone; routing
now combines these answers with the IWGDF category in app/routing.py, and
test_routing.py holds that property.

What is left here is that the answers themselves are graded correctly, that
unknown fields are rejected rather than dropped, that out-of-vocabulary values
are refused, and that no rule ever emits a treatment.
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


# --- grading the answers ------------------------------------------------------

@pytest.mark.parametrize("answers,expected", [
    ({"probe_to_bone": "yes"}, Grade.URGENT),
    ({"systemic_signs": "yes"}, Grade.URGENT),
    ({"crepitus_odour_bullae": "yes"}, Grade.URGENT),
    ({"monofilament": "absent"}, Grade.REVIEW),
    ({"duration_weeks": 8}, Grade.REVIEW),
    # Reassuring answers grade as no flag. They do not "lower" anything,
    # because there is nothing here for them to lower any more.
    ({"pedal_pulses": "both_palpable", "monofilament": "intact",
      "probe_to_bone": "no", "systemic_signs": "no"}, Grade.NO_FLAG),
    ({}, Grade.NO_FLAG),
])
def test_answers_are_graded_on_their_own(answers, expected):
    assert followup.evaluate("foot", answers).answer_grade is expected


def test_the_image_is_not_a_parameter():
    """Structural, not behavioural: there is no argument through which a
    colour threshold could be reintroduced into this grade."""
    import inspect

    assert set(inspect.signature(followup.evaluate).parameters) == {
        "module", "answers"}


def test_reassuring_answers_are_still_recorded():
    """Graded as no flag, but the finding itself is not thrown away."""
    outcome = followup.evaluate(
        "foot", {"pedal_pulses": "both_palpable", "monofilament": "intact"})
    assert outcome.answer_grade is Grade.NO_FLAG
    assert outcome.answered["pedal_pulses"] == "both_palpable"
    assert outcome.triggers == []


def test_not_tested_is_recorded_as_such_not_as_negative():
    outcome = followup.evaluate(
        "foot", {"monofilament": "not_tested", "probe_to_bone": "not_tested"})
    assert outcome.answer_grade is Grade.NO_FLAG
    assert set(outcome.not_tested) == {"monofilament", "probe_to_bone"}
    # An untested test produces no trigger -- it is neither positive nor
    # negative, and must not be scored as either.
    assert outcome.triggers == []


def test_rest_pain_with_absent_pulses_is_more_urgent_than_either():
    """A combination rule inside the answers themselves."""
    alone = followup.evaluate("foot", {"rest_pain": "yes"})
    with_pulses = followup.evaluate(
        "foot", {"rest_pain": "yes", "pedal_pulses": "both_absent"})
    assert alone.answer_grade is Grade.REVIEW
    assert with_pulses.answer_grade is Grade.URGENT


# --- validation --------------------------------------------------------------

def test_unknown_field_is_rejected_not_ignored():
    with pytest.raises(followup.UnknownFollowUpField):
        followup.evaluate("foot", {"blood_pressure": "120/80"})


def test_out_of_vocabulary_value_is_rejected():
    with pytest.raises(followup.InvalidFollowUpAnswer):
        followup.evaluate("foot", {"pedal_pulses": "maybe"})


def test_non_numeric_answer_to_a_number_question_is_rejected():
    with pytest.raises(followup.InvalidFollowUpAnswer):
        followup.evaluate("foot", {"duration_weeks": "ages"})


def test_blank_answers_are_dropped_rather_than_stored():
    outcome = followup.evaluate("foot", {"pedal_pulses": "", "rest_pain": None})
    assert outcome.answered == {}
    assert "pedal_pulses" in outcome.unanswered


# --- the safety boundary, inside this new surface ----------------------------

@pytest.mark.parametrize("module", sorted(followup.QUESTIONS))
def test_no_trigger_recommends_treatment_or_medication(module):
    for question in followup.questions_for(module):
        for value in (question.options or [99]):
            outcome = followup.evaluate(module, {question.id: value})
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
            outcome = followup.evaluate(module, {question.id: value})
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
            outcome = followup.evaluate(module, {question.id: value})
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
    assert "answers alone" in body["combination_rule"]
    assert "not an input" in body["combination_rule"]
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
    # The image's observation is RECORDED beside the answers, never combined.
    assert body["image_grade"] == "no_flag"
    assert body["answer_grade"] == "urgent"
    assert body["triggered"] is True
    assert body["note"].startswith("Wound over")
    assert body["safety"]["clinical_use"] is False
    assert len(body["outcome"]["triggers"]) == 2


async def test_an_urgent_photograph_does_not_grade_the_answers(client, auth,
                                                               ref_factory):
    """The image is recorded and ignored. Its grade appears beside the answers
    so a reader can see what was photographed, and takes no part in routing."""
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
    assert body["image_grade"] == "urgent"      # recorded
    assert body["answer_grade"] == "no_flag"    # and not combined
    assert body["triggered"] is False


async def test_note_alone_is_accepted(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"note": "Patient declined the monofilament test today."},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["answer_grade"] == "no_flag"


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


# --- combination rules from the clinical specification ------------------------

def test_ulcer_with_absent_pulse_and_rest_pain_is_the_ischaemia_pattern():
    outcome = followup.evaluate("foot", {
        "open_ulcer": "yes", "pedal_pulses": "both_absent", "rest_pain": "yes"})
    assert outcome.answer_grade is Grade.URGENT
    pattern = next(t for t in outcome.triggers
                   if "absent pulse and rest pain" in t.finding)
    assert "threatened limb" in pattern.because
    assert "BEFORE any local wound procedure" in pattern.distinguished_by


def test_ulcer_with_pus_and_fever_is_the_infection_pattern():
    outcome = followup.evaluate("foot", {
        "open_ulcer": "yes", "systemic_signs": "yes",
        "purulent_discharge": "yes"})
    assert outcome.answer_grade is Grade.URGENT
    pattern = next(t for t in outcome.triggers
                   if t.finding.startswith("Open ulcer with pus"))
    assert "probe-to-bone" in pattern.distinguished_by


def test_pus_without_a_recorded_ulcer_asks_where_it_is_coming_from():
    outcome = followup.evaluate("foot", {"purulent_discharge": "yes"})
    trigger = next(t for t in outcome.triggers if "coming from" in t.because)
    assert "beneath callus" in " ".join(trigger.consider)


@pytest.mark.parametrize("hba1c,expected", [(6.5, Grade.NO_FLAG),
                                            (9.0, Grade.REVIEW),
                                            (11.2, Grade.REVIEW)])
def test_glycaemic_control_is_an_input_the_foot_cannot_provide(hba1c, expected):
    assert followup.evaluate(
        "foot", {"glycaemic_control": hba1c}).answer_grade is expected


# --- the contraindication -----------------------------------------------------

def test_debridement_is_prohibited_when_the_foot_is_not_perfused():
    """A CONTRAINDICATION, not a recommendation. This platform never says what
    to do TO a wound; it can say what must not be done, because sharp
    debridement of an unperfused foot creates a defect the circulation cannot
    close."""
    for pulses in ("both_absent", "one_absent"):
        outcome = followup.evaluate(
            "foot", {"open_ulcer": "yes", "pedal_pulses": pulses})
        prohibition = next(t for t in outcome.triggers
                           if t.finding.startswith("DO NOT debride"))
        assert "not perfused" in prohibition.because
        assert "belongs to the clinician" in prohibition.distinguished_by


def test_nothing_ever_recommends_debridement():
    """The prohibition has no positive counterpart. With good pulses the
    platform says nothing about procedures at all — choosing to debride is a
    clinical decision made by someone holding the foot."""
    outcome = followup.evaluate(
        "foot", {"open_ulcer": "yes", "pedal_pulses": "both_palpable",
                 "systemic_signs": "no"})
    for trigger in outcome.triggers:
        blob = " ".join([trigger.finding, trigger.because,
                         trigger.distinguished_by, *trigger.consider]).lower()
        assert "debride" not in blob or "do not debride" in blob


def test_no_rule_recommends_a_dressing_or_a_drug():
    """Asked for in the specification, deliberately not implemented. A
    photograph cannot support a dressing choice, and the whole regulatory
    position of this platform rests on never making one."""
    banned = ("hydrogel", "silver", "foam dressing", "antibiotic",
              "iv antibiotics", "prescribe")
    for question in followup.questions_for("foot"):
        for value in (question.options or [1, 12, 99]):
            outcome = followup.evaluate("foot", {question.id: value})
            for trigger in outcome.triggers:
                blob = " ".join([trigger.finding, trigger.because,
                                 trigger.distinguished_by,
                                 *trigger.consider]).lower()
                for word in banned:
                    assert word not in blob, f"{question.id}={value}: {word!r}"
