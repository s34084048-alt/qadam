"""The one or two questions worth asking about a given image.

A static report is read once and filed. What changes an answer is the ten-second
experiment: re-take it with the flash on, and if the dark area vanishes it was
a shadow. So every question here names what its answer would SETTLE, and none of
them asserts what that answer will be.

At most two. A list of eight questions is a form, and forms get skipped.
"""

from __future__ import annotations

import pytest

from app.analysis import clarify
from tests.test_safety_boundary import (_assert_no_forbidden_claims,
                                        assert_no_treatment_instruction)


def _features(**kw):
    base = {
        "dark_area_pct": 0.0,
        "breakdown_pct": 0.0,
        "erythema_pct": 0.0,
        "measurement": {"scale": {"available": False}},
        "lighting": {"assessable": False},
    }
    base.update(kw)
    return base


# --- the right question for the finding ---------------------------------------

@pytest.mark.parametrize("verdict", ["shadow_like", "indeterminate"])
def test_a_dark_area_asks_for_the_flash_experiment(verdict):
    out = clarify.build(_features(
        dark_area_pct=6.0, dark_area_character={"verdict": verdict}))
    first = out[0]
    assert "flash ON" in first["ask"]
    assert "30 cm" in first["ask"]
    assert "disappear" in first["ask"]
    assert "was cast shadow" in first["settles"]


def test_tissue_like_darkness_does_not_ask_whether_it_is_a_shadow():
    """The experiment has already been done by the measurement."""
    out = clarify.build(_features(
        dark_area_pct=6.0, dark_area_character={"verdict": "tissue_like"}))
    assert not any("flash ON" in q["ask"] for q in out)


def test_a_break_in_the_surface_asks_about_depth():
    out = clarify.build(_features(breakdown_pct=2.0))
    probe = next(q for q in out if "probe" in q["ask"])
    assert "reach bone" in probe["ask"]
    assert "bone infection" in probe["settles"]
    assert "depth is the one dimension a photograph has none of" in probe["because"]


def test_measured_poor_light_asks_for_more_light():
    out = clarify.build(_features(
        dark_area_pct=3.0,
        dark_area_character={"verdict": "tissue_like"},
        lighting={"assessable": True, "adequate": False, "note": "card is dark"}))
    assert any("more light" in q["ask"] for q in out)


def test_a_missing_size_reference_is_raised_when_there_is_something_to_measure():
    out = clarify.build(_features(breakdown_pct=2.0))
    card = next(q for q in out if "bank or ID card" in q["ask"])
    assert "cm²" in card["settles"]


def test_a_clean_image_asks_about_change_over_time():
    """A single photograph has no time axis, and "nothing found" is not the
    same as "nothing wrong"."""
    out = clarify.build(_features())
    assert len(out) == 1
    assert "last 48 hours" in out[0]["ask"]
    assert "not the same as nothing being wrong" in out[0]["because"]


# --- restraint -----------------------------------------------------------------

def test_never_more_than_two():
    """Everything fires at once: dark area, breakdown, poor light, no card."""
    out = clarify.build(_features(
        dark_area_pct=8.0, breakdown_pct=3.0, erythema_pct=15.0,
        dark_area_character={"verdict": "indeterminate"},
        lighting={"assessable": True, "adequate": False, "note": "dark"}))
    assert len(out) == clarify.MAX_QUESTIONS == 2


def test_the_most_decisive_question_comes_first():
    """With both a dark area and a wound, the shadow experiment leads: it is
    the one that can remove a finding entirely."""
    out = clarify.build(_features(
        dark_area_pct=8.0, breakdown_pct=3.0,
        dark_area_character={"verdict": "shadow_like"}))
    assert "flash ON" in out[0]["ask"]
    assert "probe" in out[1]["ask"]


def test_a_size_reference_already_present_is_not_asked_for():
    out = clarify.build(_features(
        breakdown_pct=2.0,
        measurement={"scale": {"available": True, "mm_per_px": 0.3}}))
    assert not any("bank or ID card" in q["ask"] for q in out)


# --- the boundary ---------------------------------------------------------------

@pytest.mark.parametrize("features", [
    _features(dark_area_pct=8.0, dark_area_character={"verdict": "shadow_like"}),
    _features(breakdown_pct=3.0),
    _features(dark_area_pct=3.0, breakdown_pct=1.0,
              lighting={"assessable": True, "adequate": False, "note": "x"}),
    _features(),
])
def test_no_question_recommends_treatment_or_asserts_a_diagnosis(features):
    for q in clarify.build(features):
        blob = " ".join([q["ask"], q["settles"], q["because"]])
        assert_no_treatment_instruction(blob, "clarifying question")
        _assert_no_forbidden_claims(blob, "clarifying question")


def test_every_question_says_what_its_answer_settles():
    """Advice without a consequence is noise. The whole design is that each
    question is an experiment with a stated result."""
    for features in (
        _features(dark_area_pct=8.0, dark_area_character={"verdict": "shadow_like"}),
        _features(breakdown_pct=3.0),
        _features(),
    ):
        for q in clarify.build(features):
            assert q["ask"].strip().endswith("?") or "Re-take" in q["ask"] \
                or "Place a" in q["ask"]
            assert len(q["settles"]) > 40
