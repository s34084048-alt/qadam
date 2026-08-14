"""The safety boundary, asserted.

These tests exist to fail loudly if anyone widens what QADAM claims.
"""

from __future__ import annotations

import json
import re

import pytest

from app.analysis.modules_config import MODULES
from app.sample_data import SAMPLES, png_bytes
from tests.conftest import API, make_case, make_patient

ANALYSABLE = [s for s in SAMPLES if s.expected_grade is not None]

# Surface findings only. Nothing in this vocabulary names an internal
# structure or a disease entity.
ALLOWED_LESION_KINDS = {
    "erythema", "tissue_breakdown", "dark_area",
    "pigmented_lesion", "inflammation",
    "scleral_yellowing", "ocular_redness",
    "bruising", "asymmetric_swelling", "visible_deformity",
    "lip_cyanosis", "lip_pallor", "facial_flushing",
}

# Affirmative claims about internal pathology. The words themselves are
# allowed -- the limitations text has to name what QADAM cannot do -- but an
# assertion built on them is not.
FORBIDDEN_CLAIMS = [
    re.compile(
        r"\b(is|are|has|have|shows?|showing|indicates?|confirms?|confirmed|"
        r"reveals?|demonstrates?|consistent with a)\s+"
        r"(an?\s+)?(fracture|dislocation|rupture|tear|internal bleeding|"
        r"osteomyelitis|melanoma|jaundice)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdiagnos(is|ed|es)\s+(of|with|as)\b", re.IGNORECASE),
    re.compile(r"\b(fractured|dislocated|ruptured)\b", re.IGNORECASE),
    re.compile(r"\b(prescribe|prescription|start\s+antibiotics|mg\s+(od|bd|tds))\b",
               re.IGNORECASE),
]

# QADAM's own text has to name the conditions it CANNOT assess, so a bare
# keyword hit is not a violation. What matters is whether the sentence asserts
# the condition or defers/denies it.
NEGATORS = (
    "cannot", "can not", "can't", "not ", "never", "whether", "if ",
    "exclude", "excluded", "unable", "does not", "do not", "no ", "suspect",
    "suspected", "possible", "rule out", "only",
)


def _assert_no_forbidden_claims(text: str, context: str) -> None:
    for pattern in FORBIDDEN_CLAIMS:
        for match in pattern.finditer(text):
            window = text[max(0, match.start() - 40): match.start()].lower()
            if any(neg in window for neg in NEGATORS):
                continue  # deferral or denial, not an assertion
            raise AssertionError(
                f"{context}: forbidden claim {match.group(0)!r} — QADAM must "
                f"not assert internal pathology or treatment"
            )


async def _analyze(client, auth, ref_factory, sample):
    ref = ref_factory("safety")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, sample.module)
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": (f"{sample.name}.png", png_bytes(sample.name), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return case_id, resp.json()


@pytest.mark.parametrize("sample", ANALYSABLE, ids=[s.name for s in ANALYSABLE])
async def test_every_result_carries_the_disclaimer(client, auth, ref_factory, sample):
    _case_id, body = await _analyze(client, auth, ref_factory, sample)
    safety = body["safety"]
    assert safety["clinical_use"] is False
    assert "not a diagnosis" in safety["disclaimer"].lower()
    assert "NOT A MEDICAL DEVICE" in safety["device_notice"]
    assert "clinician" in safety["human_in_the_loop"].lower()
    assert safety["module_limitations"]
    assert "surface" in safety["scope"].lower()
    assert "does not recommend treatment" in safety["no_treatment"].lower()


@pytest.mark.parametrize("sample", ANALYSABLE, ids=[s.name for s in ANALYSABLE])
async def test_no_result_asserts_internal_pathology(client, auth, ref_factory, sample):
    _case_id, body = await _analyze(client, auth, ref_factory, sample)

    for lesion in body["lesions"]:
        assert lesion["kind"] in ALLOWED_LESION_KINDS, (
            f"unexpected finding type {lesion['kind']!r}: findings must name "
            f"something visible on the surface"
        )

    _assert_no_forbidden_claims(body["triage"]["next_investigation"],
                                "next_investigation")
    for reason in body["triage"]["rationale"]:
        _assert_no_forbidden_claims(reason, "rationale")
    _assert_no_forbidden_claims(body["triage"]["label"], "triage label")
    _assert_no_forbidden_claims(body["summary"], "clinician summary")

    # No field in the payload is called a diagnosis, at any level.
    def _keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key.lower()
                yield from _keys(value)
        elif isinstance(node, list):
            for item in node:
                yield from _keys(item)

    assert not any("diagnos" in key for key in _keys(body))


@pytest.mark.parametrize("sample", ANALYSABLE, ids=[s.name for s in ANALYSABLE])
async def test_summary_states_limits_and_requires_confirmation(
    client, auth, ref_factory, sample
):
    _case_id, body = await _analyze(client, auth, ref_factory, sample)
    summary = body["summary"]
    assert "NOT A MEDICAL DEVICE" in summary
    assert "not a diagnosis" in summary.lower()
    assert "NOT ASSESSED / LIMITATIONS" in summary
    assert "RECOMMENDED NEXT INVESTIGATION" in summary
    assert "Clinician confirmation:" in summary


# Anything that would make an "immediate action" a treatment instruction.
TREATMENT_TERMS = [
    "antibiotic", "antifungal", "steroid", "cream", "ointment", "tablet",
    "capsule", "insulin", "analgesi", "paracetamol", "ibuprofen", "mg ",
    "dose", "prescri", "inject", "suture", "incise", "debride the",
    "drain the", "excise", "apply iodine", "apply honey",
]

# Matched on a word boundary, not as a bare substring: "ointment" otherwise
# fires inside "appointment", which flagged perfectly safe scheduling advice.
_TREATMENT_PATTERNS = [
    (term, re.compile(r"\b" + re.escape(term), re.IGNORECASE))
    for term in TREATMENT_TERMS
]
_TREATMENT_NEGATORS = ("do not", "don't", "never", "avoid", "without")


def assert_no_treatment_instruction(text: str, context: str) -> None:
    """A prohibition ("do NOT debride") is protective; an instruction is not."""
    if any(neg in text.lower() for neg in _TREATMENT_NEGATORS):
        return
    for term, pattern in _TREATMENT_PATTERNS:
        if pattern.search(text):
            raise AssertionError(
                f"{context}: reads as a treatment instruction ({term!r}): "
                f"{text!r}"
            )


@pytest.mark.parametrize("sample", [s for s in ANALYSABLE
                                    if s.module == "foot"],
                         ids=[s.name for s in ANALYSABLE
                              if s.module == "foot"])
async def test_clinical_layer_gives_differentials_not_diagnoses(
    client, auth, ref_factory, sample
):
    _case_id, body = await _analyze(client, auth, ref_factory, sample)
    clinical = body["clinical"]
    assert clinical, "clinical layer missing for a module that has one"

    assert clinical["considerations"], "a considerations list must always exist"
    for item in clinical["considerations"]:
        # A one-item differential reads as a diagnosis. It is never emitted.
        assert len(item["overlaps_with"]) >= 2, (
            f"single-possibility differential {item['overlaps_with']!r} reads "
            f"as a diagnosis"
        )
        # Every differential must name the test that actually settles it.
        assert item["distinguished_by"].strip()
        _assert_no_forbidden_claims(item["pattern"], "consideration pattern")

    assert "not findings" in clinical["status"].lower()
    assert clinical["not_assessable"], "must state what the image cannot show"
    assert clinical["ask_and_check"], "must prompt what the camera cannot see"


@pytest.mark.parametrize("sample", [s for s in ANALYSABLE
                                    if s.module == "foot"],
                         ids=[s.name for s in ANALYSABLE
                              if s.module == "foot"])
async def test_immediate_actions_are_protective_never_treatment(
    client, auth, ref_factory, sample
):
    """Offloading and 'do not apply heat' are safe. Anything resembling a
    prescription or a procedure is not, whatever the grade."""
    _case_id, body = await _analyze(client, auth, ref_factory, sample)
    actions = body["clinical"]["immediate_actions"]
    assert actions

    for action in actions:
        assert_no_treatment_instruction(action, "immediate action")
        _assert_no_forbidden_claims(action, "immediate action")


async def test_severity_index_is_labelled_as_surface_only(
    client, auth, ref_factory
):
    sample = next(s for s in SAMPLES if s.name == "foot_urgent")
    _case_id, body = await _analyze(client, auth, ref_factory, sample)
    index = body["clinical"]["severity_index"]
    assert 0.0 <= index["value"] <= 100.0
    assert "not a wound grade" in index["caveat"].lower()

    # Published depth-based grades must not be fabricated from a photograph.
    scales = body["clinical"]["scales"]
    assert scales["Wagner"]["assessable_from_this_image"] == []
    assert "no wagner grade is produced" in scales["Wagner"]["note"].lower()
    assert "no sinbad score is produced" in scales["SINBAD"]["note"].lower()
    assert len(scales["SINBAD"]["requires_clinical_examination"]) >= 4




async def test_emergency_reference_is_static_and_image_independent(client, auth):
    """The emergency reference must never become image-driven. Assessing a
    casualty from a photograph is exactly the thing that would make it
    dangerous, so this asserts the wiring, not just the wording."""
    import inspect

    from app import reference

    first = (await client.get(f"{API}/reference/emergency", headers=auth)).json()
    assert first["image_independent"] is True
    assert first["generated_from_image"] is False
    assert first["kind"] == "static_reference"

    # Identical on every call, and unaffected by any case in the database.
    second = (await client.get(f"{API}/reference/emergency", headers=auth)).json()
    assert first == second

    # The module must not import the analysis pipeline at all.
    source = inspect.getsource(reference)
    for forbidden in ("analysis", "pipeline", "cv2", "Analysis", "case"):
        assert f"import {forbidden}" not in source, (
            f"reference.py imports {forbidden!r} — it must stay independent of "
            f"image analysis"
        )
    assert reference.emergency_reference.__code__.co_argcount == 0

    topics = {t["id"]: t for t in first["topics"]}
    assert {"priorities", "do_not_move", "in_line_stabilisation",
            "recovery_position", "log_roll", "handover"} <= set(topics)

    do_not_move = " ".join(
        topics["do_not_move"]["steps"] + topics["do_not_move"]["warnings"]
    ).lower()
    assert "mechanism" in do_not_move
    assert "no photograph" in do_not_move
    assert "do not exclude a spinal fracture" in do_not_move
    assert topics["do_not_move"]["move_only_if"]

    stabilisation = " ".join(topics["in_line_stabilisation"]["warnings"]).lower()
    assert "never apply traction" in stabilisation

    # Positioning and recognition only: no treatment, no medication.
    for topic in first["topics"]:
        for line in topic["steps"] + topic.get("warnings", []):
            _assert_no_forbidden_claims(line, f"reference/{topic['id']}")
            assert_no_treatment_instruction(line, f"reference/{topic['id']}")

    # Every diagram referenced by a topic exists and is inline SVG.
    for topic in first["topics"]:
        name = topic.get("diagram")
        if name:
            assert name in first["diagrams"]
            svg = first["diagrams"][name]
            assert svg.startswith("<svg")
            # Self-contained: the xmlns URI is a namespace identifier, but
            # anything that actually LOADS something must not be there.
            for loader in ("href=", "src=", "url(", "<image", "<script"):
                assert loader not in svg, f"diagram {name} pulls in {loader!r}"










async def test_confidence_is_never_overstated(client, auth, ref_factory):
    """An unvalidated placeholder must not report near-certainty."""
    for sample in ANALYSABLE:
        _case_id, body = await _analyze(client, auth, ref_factory, sample)
        assert body["triage"]["confidence"] <= 0.85


async def test_degraded_quality_discounts_confidence():
    """Confidence falls when the image is worse, for the same finding."""
    import cv2
    import numpy as np

    from app.analysis.pipeline import AnalysisJob, execute
    from app.sample_data import foot_urgent

    sharp = foot_urgent()
    # Soft enough to bite into the focus margin, sharp enough to still pass.
    softened = cv2.GaussianBlur(sharp, (0, 0), 1.0)

    sharp_ok, sharp_png = cv2.imencode(".png", sharp)
    soft_ok, soft_png = cv2.imencode(".png", softened)
    assert sharp_ok and soft_ok

    a = execute(AnalysisJob(image_bytes=sharp_png.tobytes(), module="foot",
                            render_overlay=False))
    b = execute(AnalysisJob(image_bytes=soft_png.tobytes(), module="foot",
                            render_overlay=False))
    assert a.result and b.result
    assert b.quality.confidence_factor <= a.quality.confidence_factor
    assert b.result.triage.confidence <= a.result.triage.confidence
    assert np.isfinite(b.result.triage.confidence)
