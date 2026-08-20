"""Evidence strength must move when its own preconditions fail.

The defect: `_conf` returned 0.85 on a run where the segmentation had
explicitly failed, and 0.53 on a healthy foot whose "dark area" was background
pixels. The score was computed from how far the measurement sat from its
decision boundary, and never from whether that measurement was possible.

Each test below drives ONE prerequisite failure and asserts two things: that
the score moved, and that the reason appears in the itemisation. The second
half matters as much as the first -- a number that drops for reasons the
reader cannot see is not an improvement on a number that never drops.
"""

from __future__ import annotations

import numpy as np

from app.analysis import localization, prerequisites
from app.analysis.calibration import Calibration
from app.analysis.scale import Scale

USABLE_CARD = Calibration(
    detected=True, applied=True,
    scale=Scale(available=True, mm_per_px=0.4, card_long_px=214.0),
)
NO_CARD = Calibration(detected=False)
TILTED_CARD = Calibration(
    detected=True, applied=True,
    scale=Scale(available=False, reason="The reference card is not square to "
                                        "the camera (its shape in the image "
                                        "is off by 22%)."),
)


def _evaluate(**overrides) -> prerequisites.Prerequisites:
    kwargs = {
        "background_warning": None,
        "subject_mask_was_degenerate": False,
        "wound_classification": localization.CONFIRMED,
        "no_wound_region_marker": localization.NONE,
        "calibration": USABLE_CARD,
    }
    kwargs.update(overrides)
    return prerequisites.evaluate(**kwargs)


def _reasons(adjustments) -> set[str]:
    return {a["reason"] for a in adjustments}


# --- 1. segmentation failure -> hard cap -------------------------------------

def test_background_same_colour_as_skin_caps_the_score():
    prereqs = _evaluate(background_warning={"issue": "background_same_colour_as_skin"})
    score, adjustments = prerequisites.apply(0.85, prereqs)

    assert score <= prerequisites.SEGMENTATION_FAILED_CAP
    cap = next(a for a in adjustments if a["kind"] == "cap")
    assert cap["from"] == 0.85
    assert cap["to"] == prerequisites.SEGMENTATION_FAILED_CAP
    assert prerequisites.SEG_BACKGROUND_SAME_COLOUR in cap["triggered_by"]
    assert "whole frame" in cap["detail"]


def test_a_degenerate_subject_mask_caps_the_score():
    """Previously silent: the segmentation found nothing, the whole frame was
    substituted, and no signal left the backend."""
    prereqs = _evaluate(subject_mask_was_degenerate=True)
    score, adjustments = prerequisites.apply(0.85, prereqs)

    assert score <= prerequisites.SEGMENTATION_FAILED_CAP
    cap = next(a for a in adjustments if a["kind"] == "cap")
    assert prerequisites.SEG_DEGENERATE_MASK in cap["triggered_by"]


def test_no_wound_region_isolated_caps_the_score():
    prereqs = _evaluate(wound_classification=localization.NONE)
    score, adjustments = prerequisites.apply(0.85, prereqs)

    assert score <= prerequisites.SEGMENTATION_FAILED_CAP
    cap = next(a for a in adjustments if a["kind"] == "cap")
    assert prerequisites.SEG_NO_WOUND_REGION in cap["triggered_by"]


def test_all_three_segmentation_failures_are_named_not_just_the_first():
    prereqs = _evaluate(
        background_warning={"issue": "background_same_colour_as_skin"},
        subject_mask_was_degenerate=True,
        wound_classification=localization.NONE,
    )
    _score, adjustments = prerequisites.apply(0.85, prereqs)
    cap = next(a for a in adjustments if a["kind"] == "cap")
    assert set(cap["triggered_by"]) == {
        prerequisites.SEG_BACKGROUND_SAME_COLOUR,
        prerequisites.SEG_DEGENERATE_MASK,
        prerequisites.SEG_NO_WOUND_REGION,
    }


def test_a_failed_prerequisite_is_itemised_even_when_the_score_was_already_low():
    """The check must be visible as a check. Otherwise a reader has to infer
    from a low number that a prerequisite was tested at all."""
    prereqs = _evaluate(subject_mask_was_degenerate=True)
    score, adjustments = prerequisites.apply(0.20, prereqs)

    assert score == 0.20
    cap = next(a for a in adjustments if a["kind"] == "cap")
    assert cap["from"] == cap["to"] == 0.20
    assert "already at or below the cap" in cap["detail"]


# --- 2. reference card seen but unusable -------------------------------------

def test_a_card_seen_but_unusable_costs_the_documented_penalty():
    prereqs = _evaluate(calibration=TILTED_CARD)
    score, adjustments = prerequisites.apply(0.80, prereqs)

    assert score == 0.80 - prerequisites.CARD_UNUSABLE_PENALTY
    penalty = next(a for a in adjustments
                   if a["reason"] == prerequisites.CARD_UNUSABLE)
    assert penalty["penalty"] == prerequisites.CARD_UNUSABLE_PENALTY
    # The user is told WHICH problem, not just that there was one.
    assert "not square to the camera" in penalty["detail"]


# --- 3. no size reference in frame -------------------------------------------

def test_no_size_reference_costs_the_documented_penalty():
    prereqs = _evaluate(calibration=NO_CARD)
    score, adjustments = prerequisites.apply(0.80, prereqs)

    assert score == 0.80 - prerequisites.NO_SIZE_REFERENCE_PENALTY
    penalty = next(a for a in adjustments
                   if a["reason"] == prerequisites.NO_SIZE_REFERENCE)
    assert penalty["penalty"] == prerequisites.NO_SIZE_REFERENCE_PENALTY
    assert "compared with another visit" in penalty["detail"]


def test_the_two_card_penalties_are_mutually_exclusive():
    """A card is either absent or present-and-rejected. Charging both would
    double-count one fact."""
    assert _reasons(prerequisites.apply(0.8, _evaluate(calibration=NO_CARD))[1]) \
        == {prerequisites.NO_SIZE_REFERENCE}
    assert _reasons(prerequisites.apply(0.8, _evaluate(calibration=TILTED_CARD))[1]) \
        == {prerequisites.CARD_UNUSABLE}


def test_a_usable_card_and_a_good_segmentation_adjust_nothing():
    score, adjustments = prerequisites.apply(0.80, _evaluate())
    assert score == 0.80
    assert adjustments == []


# --- ordering and floor ------------------------------------------------------

def test_the_cap_binds_before_the_penalties():
    """A cap says the measurement is untrustworthy; a penalty says it cannot be
    compared with another visit. The stronger statement has to bind first, or
    the penalty is subtracted from a number the cap is about to discard."""
    prereqs = _evaluate(subject_mask_was_degenerate=True, calibration=NO_CARD)
    score, adjustments = prerequisites.apply(0.85, prereqs)

    assert [a["kind"] for a in adjustments] == ["cap", "penalty"]
    assert score == (prerequisites.SEGMENTATION_FAILED_CAP
                     - prerequisites.NO_SIZE_REFERENCE_PENALTY)


def test_adjustments_never_drive_the_score_below_the_floor():
    prereqs = _evaluate(subject_mask_was_degenerate=True, calibration=TILTED_CARD)
    score, _adjustments = prerequisites.apply(prerequisites.FLOOR, prereqs)
    assert score == prerequisites.FLOOR


def test_the_cap_sits_well_below_an_even_odds_reading():
    """Guards the documented intent of the constant rather than its value: a
    capped score must not be readable as 'about even'."""
    assert prerequisites.FLOOR < prerequisites.SEGMENTATION_FAILED_CAP < 0.40


# --- end to end through the real backend -------------------------------------

def _jittered(img: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(img.astype(int) + rng.integers(-6, 7, img.shape),
                   0, 255).astype(np.uint8)


def test_a_real_analysis_carries_its_adjustments_on_the_triage():
    """The whole point is that the payload explains the number, so this asserts
    on what a caller actually receives rather than on the helper."""
    from app.analysis.backends import classical_backend
    from app.analysis.quality import run_quality_gate

    # Skin filling the frame: subject and background cannot be separated.
    image = _jittered(np.full((400, 400, 3), (140, 170, 205), dtype=np.uint8), 0)
    quality = run_quality_gate(image)
    fragment = np.zeros((400, 400), np.uint8)
    fragment[150:250, 150:250] = 255
    quality.mask = fragment

    result = classical_backend().analyze(image, "foot", quality, NO_CARD)
    payload = result.triage.to_json()

    assert payload["confidence"] <= prerequisites.SEGMENTATION_FAILED_CAP
    reasons = {a["reason"] for a in payload["confidence_adjustments"]}
    assert "segmentation_failed" in reasons
    assert prerequisites.NO_SIZE_REFERENCE in reasons
    assert all(a["detail"] for a in payload["confidence_adjustments"])


def test_a_clean_detection_keeps_its_evidence_strength():
    """The cap must not flatten every result. A capture whose segmentation
    succeeded and which found a wound region keeps the score the evidence
    earned, less only the size-reference penalty."""
    from app.sample_data import png_bytes
    from app.analysis.pipeline import AnalysisJob, execute

    job = AnalysisJob(image_bytes=png_bytes("foot_urgent"), module="foot",
                      backend_id="classical_cv", artifact_uri=None,
                      model_version="0.1.0", render_overlay=False)
    out = execute(job)

    triage = out.result.triage
    assert triage.confidence > prerequisites.SEGMENTATION_FAILED_CAP
    assert {a["reason"] for a in triage.confidence_adjustments} == {
        prerequisites.NO_SIZE_REFERENCE
    }
