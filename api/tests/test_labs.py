"""Laboratory module.

Numbers, not images. The safety questions here are different from the imaging
modules: unit confusion, ranges presented as authoritative, and interpretation
drifting into treatment.
"""

from __future__ import annotations

import pytest

from app.labs.catalog import ANALYTES, UnitError
from app.labs.interpret import interpret
from tests.conftest import API


# --- units -------------------------------------------------------------------

def test_units_are_converted_not_assumed():
    """Creatinine 2.4 mg/dL is 212 µmol/L. Reading it as µmol/L would call a
    patient in kidney failure normal."""
    out = interpret([{"code": "creat", "value": 2.4, "unit": "mg/dL"}],
                    age=68, sex="female")
    result = out.results[0]
    assert result.unit == "umol/L"
    assert result.value == pytest.approx(212.16, abs=0.1)
    assert result.flag == "high"
    assert result.submitted_unit == "mg/dL"


def test_unknown_unit_is_rejected_never_guessed():
    with pytest.raises(UnitError) as excinfo:
        interpret([{"code": "k", "value": 5.0, "unit": "g/L"}])
    assert "not a unit this analyte accepts" in str(excinfo.value)
    assert "mmol/L" in str(excinfo.value)


@pytest.mark.parametrize("code,value,unit,expected", [
    ("gluc", 110, "mg/dL", 6.105),      # mg/dL -> mmol/L
    ("hb", 9.1, "g/dL", 91.0),          # g/dL  -> g/L
    ("bili", 2.0, "mg/dL", 34.2),       # mg/dL -> µmol/L
    ("hba1c", 7.0, "%", 76.5),          # NGSP % -> IFCC mmol/mol
])
def test_conversion_factors(code, value, unit, expected):
    assert ANALYTES[code].to_canonical(value, unit) == pytest.approx(
        expected, rel=0.01)


# --- grading -----------------------------------------------------------------

def test_critical_value_routes_urgent():
    out = interpret([{"code": "k", "value": 6.9, "unit": "mmol/L"}])
    assert str(out.triage.grade) == "urgent"
    assert out.results[0].critical is True
    assert "CONTACT A CLINICIAN NOW" in out.triage.next_investigation


def test_all_normal_is_no_flag():
    out = interpret([
        {"code": "na", "value": 140, "unit": "mmol/L"},
        {"code": "k", "value": 4.2, "unit": "mmol/L"},
        {"code": "hb", "value": 145, "unit": "g/L"},
    ], sex="male")
    assert str(out.triage.grade) == "no_flag"
    # A clean panel must not be presented as reassurance.
    assert "does not exclude" in out.triage.next_investigation.lower()


def test_sex_specific_reference_ranges():
    """Haemoglobin 125 g/L is low for a man and normal for a woman."""
    male = interpret([{"code": "hb", "value": 125, "unit": "g/L"}], sex="male")
    female = interpret([{"code": "hb", "value": 125, "unit": "g/L"}],
                       sex="female")
    assert male.results[0].flag == "low"
    assert female.results[0].flag == "normal"


def test_unrecognised_analyte_is_reported_not_silently_dropped():
    out = interpret([
        {"code": "hb", "value": 140, "unit": "g/L"},
        {"code": "unobtainium", "value": 42, "unit": "mmol/L"},
    ], sex="male")
    assert len(out.results) == 1
    assert out.unrecognised[0]["code"] == "unobtainium"
    assert "not interpreted" in out.unrecognised[0]["reason"]


# --- derived indices ---------------------------------------------------------

def test_egfr_ckd_epi_2021():
    out = interpret([{"code": "creat", "value": 2.4, "unit": "mg/dL"}],
                    age=68, sex="female")
    egfr = next(d for d in out.derived if d["code"] == "egfr")
    assert egfr["value"] == pytest.approx(21.5, abs=0.5)
    assert "G4" in egfr["interpretation"]
    assert "acute kidney injury from" in egfr["caveat"]


def test_derived_indices_require_their_inputs():
    """No age means no eGFR — the equation needs it, so it is not produced."""
    out = interpret([{"code": "creat", "value": 200, "unit": "umol/L"}])
    assert not any(d["code"] == "egfr" for d in out.derived)


def test_anion_gap_and_adjusted_calcium():
    out = interpret([
        {"code": "na", "value": 140, "unit": "mmol/L"},
        {"code": "cl", "value": 100, "unit": "mmol/L"},
        {"code": "hco3", "value": 18, "unit": "mmol/L"},
        {"code": "ca", "value": 2.15, "unit": "mmol/L"},
        {"code": "alb", "value": 30, "unit": "g/L"},
    ])
    gap = next(d for d in out.derived if d["code"] == "anion_gap")
    assert gap["value"] == pytest.approx(22.0)
    assert gap["interpretation"] == "raised"

    # 2.15 + 0.02 * (40 - 30) = 2.35 -> a "low" calcium that is not low.
    adjusted = next(d for d in out.derived if d["code"] == "ca_adjusted")
    assert adjusted["value"] == pytest.approx(2.35, abs=0.01)
    assert adjusted["interpretation"] == "within the usual range"


# --- differentials -----------------------------------------------------------

@pytest.mark.parametrize("mcv,expected", [
    (72, "microcytic"), (105, "macrocytic"), (88, "normocytic"),
])
def test_anaemia_differential_branches_on_mcv(mcv, expected):
    out = interpret([
        {"code": "hb", "value": 95, "unit": "g/L"},
        {"code": "mcv", "value": mcv, "unit": "fL"},
    ], sex="female")
    patterns = " ".join(c.pattern for c in out.clinical.considerations)
    assert expected in patterns


def test_liver_pattern_separates_hepatocellular_from_cholestatic():
    hepatocellular = interpret([
        {"code": "alt", "value": 300, "unit": "U/L"},
        {"code": "alp", "value": 90, "unit": "U/L"},
    ], sex="male")
    assert any("Hepatocellular" in c.pattern
               for c in hepatocellular.clinical.considerations)

    cholestatic = interpret([
        {"code": "alt", "value": 30, "unit": "U/L"},
        {"code": "alp", "value": 400, "unit": "U/L"},
    ], sex="male")
    consideration = next(c for c in cholestatic.clinical.considerations
                         if "Cholestatic" in c.pattern)
    # A raised ALP is not always the liver, and the module must say so.
    assert any("BONE source" in option for option in consideration.overlaps_with)
    assert "GGT" in consideration.distinguished_by


def test_every_lab_differential_has_at_least_two_possibilities():
    out = interpret([
        {"code": "k", "value": 6.9, "unit": "mmol/L"},
        {"code": "na", "value": 128, "unit": "mmol/L"},
        {"code": "hb", "value": 95, "unit": "g/L"},
        {"code": "mcv", "value": 72, "unit": "fL"},
        {"code": "crp", "value": 120, "unit": "mg/L"},
    ], age=70, sex="female")
    assert out.clinical.considerations
    for consideration in out.clinical.considerations:
        assert len(consideration.overlaps_with) >= 2
        assert consideration.distinguished_by.strip()


def test_sample_validity_is_the_first_thing_questioned():
    """The commonest cause of a shock potassium is the sample, not the patient."""
    out = interpret([{"code": "k", "value": 6.9, "unit": "mmol/L"}])
    potassium = next(c for c in out.clinical.considerations
                     if "Potassium" in c.pattern)
    assert "haemolysed" in potassium.overlaps_with[0]
    assert any("haemolys" in a.lower() for a in out.clinical.immediate_actions)


def test_actions_never_stray_into_treatment():
    from tests.test_safety_boundary import assert_no_treatment_instruction

    out = interpret([
        {"code": "k", "value": 6.9, "unit": "mmol/L"},
        {"code": "gluc", "value": 28, "unit": "mmol/L"},
    ], age=60, sex="male")
    for action in out.clinical.immediate_actions:
        assert_no_treatment_instruction(action, "lab action")
    assert any("belongs to the clinician" in a
               for a in out.clinical.immediate_actions)


# --- API ---------------------------------------------------------------------

async def test_catalogue_endpoint_lists_accepted_units(client, auth):
    body = (await client.get(f"{API}/labs/catalogue", headers=auth)).json()
    codes = {a["code"] for a in body["analytes"]}
    assert {"hb", "k", "creat", "alt", "gluc"} <= codes

    creat = next(a for a in body["analytes"] if a["code"] == "creat")
    assert "mg/dL" in creat["accepted_units"]
    assert creat["reference_female"]["high"] == 90

    # Troponin is deliberately shipped without a range.
    trop = next(a for a in body["analytes"] if a["code"] == "trop")
    assert trop["reference"] == {"low": None, "high": None}
    assert "specific to the assay" in trop["note"]

    assert "NOT universal" in body["reference_range_caveat"]


async def test_interpret_endpoint(client, auth):
    resp = await client.post(f"{API}/labs/interpret", headers=auth, json={
        "age": 68, "sex": "female",
        "results": [
            {"code": "k", "value": 6.9, "unit": "mmol/L"},
            {"code": "creat", "value": 2.4, "unit": "mg/dL"},
        ],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["triage"]["grade"] == "urgent"
    assert body["interpreted_from_image"] is False
    assert body["input_kind"] == "typed_numeric_values"
    assert body["safety"]["clinical_use"] is False
    assert any(d["code"] == "egfr" for d in body["derived"])
    assert "NOT universal" in body["reference_range_caveat"]


async def test_interpret_rejects_a_bad_unit_with_a_usable_hint(client, auth):
    resp = await client.post(f"{API}/labs/interpret", headers=auth, json={
        "results": [{"code": "k", "value": 5.0, "unit": "g/L"}],
    })
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "unit_not_accepted"
    assert "labs/catalogue" in error["hint"]


async def test_labs_require_authentication(client):
    assert (await client.get(f"{API}/labs/catalogue")).status_code == 401
    assert (await client.post(f"{API}/labs/interpret", json={
        "results": [{"code": "k", "value": 4.0, "unit": "mmol/L"}]})
    ).status_code == 401


# --- persistence -------------------------------------------------------------

async def test_panel_is_stored_against_a_case_and_read_back(
    client, auth, ref_factory
):
    from tests.conftest import make_case, make_patient

    ref = ref_factory("lab")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "lab")

    created = await client.post(f"{API}/cases/{case_id}/labs", headers=auth, json={
        "panel_name": "U&E + FBC",
        "collected_at": "2026-08-12T09:30:00+00:00",
        "age": 68, "sex": "female",
        "results": [
            {"code": "k", "value": 6.9, "unit": "mmol/L"},
            {"code": "creat", "value": 2.4, "unit": "mg/dL"},
            {"code": "hb", "value": 9.1, "unit": "g/dL"},
        ],
    })
    assert created.status_code == 201, created.text
    assert created.json()["triage"]["grade"] == "urgent"

    listed = (await client.get(f"{API}/cases/{case_id}/labs", headers=auth)).json()
    assert listed["total"] == 1
    panel = listed["panels"][0]
    assert panel["panel_name"] == "U&E + FBC"
    assert panel["triage"]["grade"] == "urgent"
    assert panel["clinical"]["considerations"]
    assert any(d["code"] == "egfr" for d in panel["derived"])

    # Critical results sort first, and the submitted value survives the round
    # trip so a later reader can see what was actually typed.
    assert panel["results"][0]["critical"] is True
    creat = next(r for r in panel["results"] if r["code"] == "creat")
    assert creat["unit"] == "umol/L"
    assert creat["submitted"] == {"value": 2.4, "unit": "mg/dL"}
    assert creat["converted"] is True


async def test_panel_attaches_to_a_non_lab_case(client, auth, ref_factory):
    """The loop only closes if bloods can hang off the imaging case that
    asked for them."""
    from app.sample_data import png_bytes
    from tests.conftest import make_case, make_patient

    ref = ref_factory("loop")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )
    created = await client.post(f"{API}/cases/{case_id}/labs", headers=auth, json={
        "results": [{"code": "crp", "value": 180, "unit": "mg/L"}],
    })
    assert created.status_code == 201

    listed = (await client.get(f"{API}/cases/{case_id}/labs", headers=auth)).json()
    assert listed["total"] == 1
    case = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert case["latest_analysis"]["triage"]["grade"] == "urgent"


async def test_age_and_sex_fall_back_to_the_patient_record(
    client, auth, ref_factory
):
    from tests.conftest import make_case

    ref = ref_factory("fallback")
    await client.post(f"{API}/patients", headers=auth, json={
        "external_ref": ref, "dob_year": 1958, "sex": "female",
        "consent_flag": True,
    })
    case_id = await make_case(client, auth, ref, "lab")

    created = await client.post(f"{API}/cases/{case_id}/labs", headers=auth, json={
        "results": [{"code": "creat", "value": 2.4, "unit": "mg/dL"}],
    })
    assert created.status_code == 201
    body = created.json()
    # eGFR needs an age; it came from dob_year without the caller restating it.
    assert any(d["code"] == "egfr" for d in body["derived"])
    # Female range applied: 212 µmol/L against a female upper limit of 90.
    assert body["results"][0]["reference"]["high"] == 90


async def test_nothing_is_stored_when_a_unit_is_rejected(
    client, auth, ref_factory
):
    from tests.conftest import make_case, make_patient

    ref = ref_factory("atomic")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "lab")

    resp = await client.post(f"{API}/cases/{case_id}/labs", headers=auth, json={
        "results": [
            {"code": "hb", "value": 140, "unit": "g/L"},
            {"code": "k", "value": 5.0, "unit": "g/L"},
        ],
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unit_not_accepted"

    listed = (await client.get(f"{API}/cases/{case_id}/labs", headers=auth)).json()
    assert listed["total"] == 0, "a rejected panel must not be half-stored"


async def test_erasure_removes_lab_results_too(client, auth, ref_factory):
    """A right-to-erasure that leaves lab results behind is not an erasure."""
    import uuid as uuidlib

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import LabPanel, LabResult
    from tests.conftest import make_case, make_patient

    ref = ref_factory("erase-lab")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "lab")
    await client.post(f"{API}/cases/{case_id}/labs", headers=auth, json={
        "age": 60, "sex": "male",
        "results": [{"code": "k", "value": 6.9, "unit": "mmol/L"}],
    })

    cid = uuidlib.UUID(case_id)
    async with SessionLocal() as session:
        panel = (await session.execute(
            select(LabPanel).where(LabPanel.case_id == cid)
        )).scalar_one()
        panel_id = panel.id
        assert (await session.execute(
            select(LabResult).where(LabResult.panel_id == panel_id)
        )).scalars().all()

    # It is in the export before erasure...
    export = (await client.get(f"{API}/patients/{ref}/export", headers=auth)).json()
    assert export["cases"][0]["lab_panels"][0]["results"][0]["code"] == "k"

    assert (await client.delete(f"{API}/patients/{ref}",
                                headers=auth)).status_code == 200

    async with SessionLocal() as session:
        assert (await session.execute(
            select(LabPanel).where(LabPanel.id == panel_id)
        )).scalar_one_or_none() is None
        assert (await session.execute(
            select(LabResult).where(LabResult.panel_id == panel_id)
        )).scalars().all() == []


async def test_audit_records_the_panel_but_never_the_values(client, auth):
    import json as jsonlib

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuditLog

    await client.post(f"{API}/labs/interpret", headers=auth, json={
        "age": 55, "sex": "male",
        "results": [{"code": "k", "value": 6.9, "unit": "mmol/L"}],
    })
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.action == "lab.interpret")
        )).scalars().all()
    assert rows
    blob = jsonlib.dumps(rows[-1].meta_json)
    assert "6.9" not in blob, "audit trail must not carry result values"
    assert rows[-1].meta_json["grade"] == "urgent"
    assert rows[-1].meta_json["critical"] == 1
