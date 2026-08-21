"""The role travels with the number, on every surface that shows the number.

WHAT THIS PINS
--------------
On a run whose own page said the measurements were meaningless, the annotated
image read

    tissue breakdown [artifact] 31.3%

and the findings table three cards below it read

    tissue breakdown | 31.3% | 1.00

Same region, same pipeline, same page. The word that made the number safe to
read was carried only by the burned-in label -- the surface a reader skims
PAST -- and dropped by the table, the PDF and the clinician summary, which are
the surfaces a reader skims.

The cause was structural: the rule lived in a private helper inside the
renderer, so only the renderer could apply it. It lives in
`analysis.lesion_role` now and every surface asks it. These tests assert the
agreement, not one copy of the rule.

Roles describe PIXELS. "possible_wound" is the strongest thing the vocabulary
can say and it still says possible.

Synthetic images only; not a clinical claim.
"""

from __future__ import annotations

import numpy as np

from app.analysis import lesion_role, overlay
from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.types import Grade, Lesion, QualityReport, Triage
from app.sample_data import png_bytes
from app.summary import build_summary

CONFIRMED = {"wound_localization": {"classification": "confirmed_possible_wound"}}


def test_a_shadow_is_an_artifact_and_a_slough_bed_is_not():
    """The two verdicts that carry a positive reading, in both directions."""
    shadow = {"dark_area_character": {"verdict": "shadow_like"}, **CONFIRMED}
    tissue = {"dark_area_character": {"verdict": "tissue_like"}, **CONFIRMED}
    assert lesion_role.role_for("dark_area", shadow) == lesion_role.ARTIFACT
    assert lesion_role.role_for("dark_area", tissue) == lesion_role.POSSIBLE_WOUND

    callus = {"yellow_area_character": {"verdict": "callus_like"}, **CONFIRMED}
    slough = {"yellow_area_character": {"verdict": "slough_like"}, **CONFIRMED}
    assert lesion_role.role_for("tissue_breakdown", callus) == lesion_role.ARTIFACT
    assert (lesion_role.role_for("tissue_breakdown", slough)
            == lesion_role.POSSIBLE_WOUND)


def test_no_verdict_reads_uncertain_never_artifact():
    """Absence of evidence is not a verdict either way. Defaulting to ARTIFACT
    would dismiss a finding on no evidence; POSSIBLE_WOUND would assert one."""
    for features in ({}, {"dark_area_character": {"verdict": "indeterminate"}},
                     {"dark_area_character": None}):
        assert lesion_role.role_for("dark_area", features) == lesion_role.UNCERTAIN
    # A kind this pipeline does not characterise gets no claim either.
    assert lesion_role.role_for("pigmented_lesion", CONFIRMED) == lesion_role.UNCERTAIN
    # Erythema is never a wound claim on its own.
    assert lesion_role.role_for("erythema", CONFIRMED) == lesion_role.UNCERTAIN


def test_a_role_never_over_claims_past_localisation():
    """Where localisation drew no confirmed boundary, "possible wound" is
    exactly the claim its plausibility guard exists to withhold."""
    tissue_unconfirmed = {"dark_area_character": {"verdict": "tissue_like"},
                          "wound_localization": {"classification": "uncertain"}}
    assert (lesion_role.role_for("dark_area", tissue_unconfirmed)
            == lesion_role.UNCERTAIN)
    # ARTIFACT is never upgraded away by the same guard.
    shadow_unconfirmed = {"dark_area_character": {"verdict": "shadow_like"},
                          "wound_localization": {}}
    assert (lesion_role.role_for("dark_area", shadow_unconfirmed)
            == lesion_role.ARTIFACT)


def test_the_overlay_colour_and_the_role_cannot_disagree():
    """The picture's colour is DERIVED from the role now. This is the coupling
    that keeps the burned-in label and the table in step."""
    for features, expected in (
        ({"dark_area_character": {"verdict": "shadow_like"}}, overlay.ARTIFACT_BLUE),
        ({"dark_area_character": {"verdict": "tissue_like"}, **CONFIRMED},
         overlay.WOUND_RED),
        ({}, overlay.UNCERTAIN_YELLOW),
    ):
        role = lesion_role.role_for("dark_area", features)
        assert overlay.ROLE_COLOR[role] == expected


def _foot_analysis(sample: str):
    out = execute(AnalysisJob(image_bytes=png_bytes(sample), module="foot",
                              render_overlay=False))
    assert out.result is not None
    return out


def test_every_reported_lesion_carries_a_role():
    """Across the real fixtures: no lesion reaches a reader without one."""
    seen = set()
    for sample in ("foot_urgent", "foot_dark_area", "foot_shadow_only"):
        out = _foot_analysis(sample)
        for lesion in out.result.lesions:
            role = lesion_role.role_for(lesion.kind, out.result.features)
            assert role in lesion_role.ROLE_LABEL, f"{sample}: {role!r}"
            seen.add(role)
    assert seen, "no lesions were produced; this test asserts nothing"


def test_the_clinician_summary_states_the_role():
    """FAILS against the unfixed summary, which printed the area and severity
    of an artifact with nothing to say it was one."""
    out = _foot_analysis("foot_urgent")
    text = build_summary(
        result=out.result, quality=out.quality, module="foot",
        patient_ref="TEST-1", captured_at="2026-01-01T00:00:00", body_site=None,
    )
    for lesion in out.result.lesions:
        role = lesion_role.role_for(lesion.kind, out.result.features)
        assert f"[{lesion_role.ROLE_LABEL[role]}]" in text, (
            f"{lesion.kind} appears in the summary without its role")


def test_the_overlay_label_states_the_role():
    """The burned-in label keeps saying it -- this is the behaviour that was
    already right, and the refactor must not lose it."""
    img = np.full((260, 340, 3), 180, np.uint8)
    lesions = [Lesion(kind="dark_area", area_pct=31.3, severity=1.0,
                      bbox=(40, 40, 90, 70), centroid=(85, 75))]
    triage = Triage(grade=Grade.REVIEW, label="Clinician review", confidence=0.2)
    quality = QualityReport(passed=True, checks=[], width=340, height=260,
                            subject_fraction=0.5, focus_var=100.0,
                            exposure_mean=128.0, confidence_factor=1.0)
    rendered = overlay.render_overlay(
        img, lesions, triage, quality, "foot",
        features={"dark_area_character": {"verdict": "shadow_like"}})
    # The label is drawn, so assert on the colour it is drawn in: BLUE is the
    # palette's "explicitly NOT a wound".
    blue = np.all(rendered == np.array(overlay.ARTIFACT_BLUE, np.uint8), axis=-1)
    assert blue.any(), "the artifact box lost its BLUE role colour"
