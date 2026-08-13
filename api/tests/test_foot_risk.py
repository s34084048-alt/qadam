"""Diabetic foot risk stratification.

The lead indication. The rule itself is published and easy to get right; the
thing worth testing hardest is the refusal path, because the failure mode of
photo-led foot screening is a neuropathic foot recorded as low risk because
nobody put a monofilament on it.
"""

from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.foot_risk import stratify
from app.models import FootRiskAssessment
from tests.conftest import API, make_case, make_patient

ABSENT = {
    "lops": "absent", "pad": "absent", "deformity": "absent",
    "previous_ulcer": "absent", "previous_amputation": "absent",
    "end_stage_renal_disease": "absent",
}


def _s(**overrides):
    return stratify(**{**ABSENT, **overrides})


# --- the published rule ------------------------------------------------------

@pytest.mark.parametrize("overrides,category", [
    ({}, 0),
    ({"lops": "present"}, 1),
    ({"pad": "present"}, 1),
    ({"lops": "present", "pad": "present"}, 2),
    ({"lops": "present", "deformity": "present"}, 2),
    ({"pad": "present", "deformity": "present"}, 2),
    ({"lops": "present", "previous_ulcer": "present"}, 3),
    ({"pad": "present", "previous_amputation": "present"}, 3),
    ({"lops": "present", "end_stage_renal_disease": "present"}, 3),
])
def test_iwgdf_categories(overrides, category):
    assert _s(**overrides).category == category


def test_deformity_alone_is_not_enough_for_category_2():
    """Deformity only raises the category in combination with LOPS or PAD."""
    assert _s(deformity="present").category == 0


@pytest.mark.parametrize("category,expected", [
    (0, "once a year"), (1, "6–12 months"), (2, "3–6 months"), (3, "1–3 months"),
])
def test_each_category_sets_a_screening_interval(category, expected):
    overrides = {
        0: {},
        1: {"lops": "present"},
        2: {"lops": "present", "pad": "present"},
        3: {"lops": "present", "previous_ulcer": "present"},
    }[category]
    result = _s(**overrides)
    assert result.category == category
    assert expected in result.screening_interval


# --- the refusal path --------------------------------------------------------

@pytest.mark.parametrize("field,test_name", [
    ("lops", "monofilament"),
    ("pad", "pulses"),
])
def test_untested_sensation_or_perfusion_refuses_to_stratify(field, test_name):
    result = _s(**{field: "not_tested"})
    assert result.category is None
    assert result.complete is False
    assert result.missing_tests
    assert test_name in " ".join(result.missing_tests).lower()
    # Never silently filed as low risk.
    assert str(result.grade) == "review"
    assert "NOT produced" in result.rationale[0]
    assert any("ABSENT TEST IS NOT A NEGATIVE TEST" in r.upper()
               for r in result.rationale)


def test_an_untested_foot_is_not_reported_as_low_risk():
    """The exact failure mode this module exists to prevent."""
    untested = _s(lops="not_tested")
    tested = _s()
    assert tested.category == 0 and str(tested.grade) == "no_flag"
    assert untested.category is None
    assert "Not determined" in untested.screening_interval
    assert "low risk" not in untested.label.lower()


def test_incomplete_assessment_names_the_indistinguishable_possibilities():
    result = _s(pad="not_tested")
    assert result.clinical is not None
    consideration = result.clinical.considerations[0]
    assert len(consideration.overlaps_with) >= 3
    assert any("not been tested" in o for o in consideration.overlaps_with)


def test_history_without_neuropathy_or_ischaemia_is_escalated_for_review():
    """The rule puts this at category 0, but the combination is odd enough to
    warrant a clinician rather than quiet filing."""
    result = _s(previous_ulcer="present")
    assert result.category == 0
    assert str(result.grade) == "review"
    assert any("unusual" in r for r in result.rationale)


# --- clinical layer ----------------------------------------------------------

def test_never_claims_to_see_neuropathy_or_perfusion_in_an_image():
    result = _s(lops="present", pad="present")
    not_assessable = " ".join(result.clinical.not_assessable).lower()
    assert "monofilament is required" in not_assessable
    assert "pulses and ankle or toe pressures are required" in not_assessable
    assert result.to_json()["derived_from_image"] is False


def test_charcot_is_offered_against_deformity():
    """A warm swollen neuropathic foot mistaken for infection costs the foot."""
    result = _s(lops="present", deformity="present")
    deformity = next(c for c in result.clinical.considerations
                     if "deformity" in c.pattern.lower())
    assert any("Charcot" in o for o in deformity.overlaps_with)
    assert "temperature" in deformity.distinguished_by.lower()


def test_falsely_high_ankle_index_is_named_against_pad():
    result = _s(pad="present")
    pad = next(c for c in result.clinical.considerations
               if "artery" in c.pattern.lower())
    assert any("calcification" in o for o in pad.overlaps_with)
    assert "toe" in pad.distinguished_by.lower()


def test_category_zero_does_not_read_as_reassurance():
    result = _s()
    assert "does not describe the foot today" in \
        result.clinical.severity_index["caveat"]
    assert "still an emergency" in result.clinical.severity_index["caveat"]


def test_every_differential_has_two_or_more_possibilities():
    for overrides in ({}, {"lops": "present"}, {"pad": "present"},
                      {"lops": "present", "deformity": "present"},
                      {"lops": "not_tested"}):
        result = _s(**overrides)
        assert result.clinical.considerations
        for consideration in result.clinical.considerations:
            assert len(consideration.overlaps_with) >= 2
            assert consideration.distinguished_by.strip()


def test_no_action_is_a_treatment_instruction():
    from tests.test_safety_boundary import assert_no_treatment_instruction

    for overrides in ({}, {"lops": "present", "previous_ulcer": "present"},
                      {"pad": "not_tested"}):
        result = _s(**overrides)
        for action in result.clinical.immediate_actions:
            assert_no_treatment_instruction(action, "foot action")


# --- API ---------------------------------------------------------------------

async def test_risk_model_is_published(client, auth):
    body = (await client.get(f"{API}/foot/risk-model", headers=auth)).json()
    assert set(body["categories"]) == {"0", "1", "2", "3"} or \
        set(body["categories"]) == {0, 1, 2, 3}
    assert "monofilament" in body["required_tests"]["lops"]
    assert "calcification" in body["required_tests"]["pad"]
    assert "absent test is not a negative test" in \
        body["refuses_to_stratify_when"].lower()
    assert body["derived_from_image"] is False


async def test_assessment_is_stored_and_read_back(client, auth, ref_factory):
    ref = ref_factory("foot")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    created = await client.post(
        f"{API}/cases/{case_id}/foot-risk", headers=auth,
        json={"foot": "both", "lops": "present", "pad": "absent",
              "deformity": "present", "previous_ulcer": "absent",
              "previous_amputation": "absent",
              "end_stage_renal_disease": "absent"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["category"] == 2
    assert body["complete"] is True
    assert "3–6 months" in body["screening_interval"]

    listed = (await client.get(f"{API}/cases/{case_id}/foot-risk",
                               headers=auth)).json()
    assert listed["total"] == 1
    assert listed["assessments"][0]["findings"]["lops"] == "present"

    async with SessionLocal() as session:
        row = (await session.execute(
            select(FootRiskAssessment)
            .where(FootRiskAssessment.case_id == uuidlib.UUID(case_id))
        )).scalar_one()
    assert row.category == 2 and row.complete is True


async def test_incomplete_assessment_is_stored_with_a_null_category(
    client, auth, ref_factory
):
    ref = ref_factory("foot-incomplete")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    created = await client.post(
        f"{API}/cases/{case_id}/foot-risk", headers=auth,
        json={"lops": "not_tested", "pad": "absent"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["category"] is None
    assert body["complete"] is False
    assert body["grade"] == "review"

    async with SessionLocal() as session:
        row = (await session.execute(
            select(FootRiskAssessment)
            .where(FootRiskAssessment.case_id == uuidlib.UUID(case_id))
        )).scalar_one()
    assert row.category is None


async def test_erasure_removes_foot_assessments(client, auth, ref_factory):
    ref = ref_factory("foot-erase")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    await client.post(f"{API}/cases/{case_id}/foot-risk", headers=auth,
                      json={"lops": "present", "pad": "present"})

    export = (await client.get(f"{API}/patients/{ref}/export",
                               headers=auth)).json()
    assert export["cases"][0]["foot_risk_assessments"][0]["category"] == 2

    assert (await client.delete(f"{API}/patients/{ref}",
                                headers=auth)).status_code == 200
    async with SessionLocal() as session:
        assert (await session.execute(
            select(FootRiskAssessment)
            .where(FootRiskAssessment.case_id == uuidlib.UUID(case_id))
        )).scalars().all() == []


async def test_foot_risk_requires_authentication(client, auth, ref_factory):
    ref = ref_factory("foot-auth")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    assert (await client.get(f"{API}/foot/risk-model")).status_code == 401
    assert (await client.post(f"{API}/cases/{case_id}/foot-risk",
                              json={"lops": "absent", "pad": "absent"})
            ).status_code == 401


# --- the exported record -----------------------------------------------------

async def test_pdf_exports_an_examination_with_no_photograph(
    client, auth, ref_factory
):
    """A foot visit where the monofilament test was done but the photo failed
    the quality gate is a real visit. The examination sets the screening
    interval, so the record must still export."""
    ref = ref_factory("foot-pdf")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    empty = await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "nothing_to_summarise"

    await client.post(f"{API}/cases/{case_id}/foot-risk", headers=auth,
                      json={"lops": "present", "pad": "absent",
                            "deformity": "present"})

    pdf = await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:5] == b"%PDF-"
    assert len(pdf.content) > 2000


async def test_pdf_carries_the_whole_screening_record(client, auth, ref_factory):
    """Image analysis, foot examination, bloods and a filed report in one
    exported document — the referral loop end to end."""
    from app.sample_data import png_bytes

    ref = ref_factory("foot-full")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    await client.post(f"{API}/cases/{case_id}/analyze", headers=auth,
                      files={"file": ("f.png", png_bytes("foot_urgent"),
                                      "image/png")})
    await client.post(f"{API}/cases/{case_id}/foot-risk", headers=auth,
                      json={"lops": "not_tested", "pad": "absent"})
    await client.post(f"{API}/cases/{case_id}/labs", headers=auth, json={
        "age": 66, "sex": "male",
        "results": [{"code": "crp", "value": 180, "unit": "mg/L"},
                    {"code": "hba1c", "value": 9.4, "unit": "%"}],
    })
    await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "modality": "x-ray",
              "identifiers_removed": "true",
              "report_text": "No periosteal reaction. Correlate clinically."},
    )

    pdf = await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:5] == b"%PDF-"
    # Four sections plus the safety pages make a substantially larger document
    # than the image-only summary.
    assert len(pdf.content) > 20000
