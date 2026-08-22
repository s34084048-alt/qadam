"""Is the redness a BOUNDED AREA, or colour spread across the skin?

WHY THIS EXISTS
---------------
This module measures three things: red, yellow, dark. A granulating ulcer bed
is RED -- not yellow, not dark -- so by construction it lands in `erythema`,
the same bucket as a flush or the pink of a warm foot. On a real photograph of
an open plantar ulcer the wound was reported as "erythema, uncertain, 10.7%"
and nothing on the page separated it from scattered colour variation.

`tissue_breakdown` could not have caught it: that threshold measures YELLOWNESS
(b* above the skin median), which is slough, not a red bed.

WHAT THIS DOES, AND WHAT IT REFUSES TO DO
-----------------------------------------
It measures a MARGIN and MOISTURE -- the same two quantities that separate
slough from callus, one colour axis over -- and says whether the redness is
bounded. That is a better description and nothing else.

It does NOT raise the grade and cannot: erythema stays capped at REVIEW in
`evidence._erythema`, because a bounded red area is still a colour and none of
these measurements establishes warmth, infection or depth. That ceiling has its
own test below, and it is the test that must never be deleted.

Synthetic images only; not a clinical claim.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.analysis import cv_utils, evidence, lesion_role
from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.types import Grade
from app.sample_data import png_bytes

W, H = 900, 700
SKIN = (168, 186, 208)
CONFIRMED = {"wound_localization": {"classification": "confirmed_possible_wound"}}


def _base():
    rng = np.random.default_rng(5)
    img = np.full((H, W, 3), (70, 55, 40), np.uint8)
    cv2.ellipse(img, (450, 350), (300, 260), 0, 0, 360, SKIN, -1)
    return cv2.GaussianBlur(img, (0, 0), 3), rng


def _bounded_bed() -> tuple[np.ndarray, np.ndarray]:
    """An open bed: a hard margin, granular texture, wet highlights."""
    img, rng = _base()
    region = np.zeros((H, W), np.uint8)
    cv2.circle(region, (430, 330), 70, 255, -1)
    img[region > 0] = (92, 96, 200)
    ys, xs = np.nonzero(region)
    for _ in range(700):                       # granulation
        i = rng.integers(0, ys.size)
        cv2.circle(img, (int(xs[i]), int(ys[i])), int(rng.integers(2, 5)),
                   tuple(int(c) for c in np.clip(
                       np.array((92, 96, 200)) + rng.normal(0, 34, 3), 0, 255)), -1)
    for _ in range(90):                        # specular, i.e. moist
        i = rng.integers(0, ys.size)
        cv2.circle(img, (int(xs[i]), int(ys[i])), int(rng.integers(2, 4)),
                   (238, 240, 248), -1)
    return np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8), region


def _diffuse_flush() -> tuple[np.ndarray, np.ndarray]:
    """A flush: no margin at skin level, dry, fading gradually."""
    img, rng = _base()
    region = np.zeros((H, W), np.uint8)
    cv2.circle(region, (430, 330), 130, 255, -1)
    red = img.copy()
    red[region > 0] = (120, 128, 200)
    red = cv2.GaussianBlur(red, (0, 0), 55)
    img = np.where(cv2.GaussianBlur(region, (0, 0), 55)[..., None] > 8, red, img)
    return np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8), region


def test_a_bounded_wet_bed_and_a_dry_flush_are_told_apart():
    """The measurement itself, on the two cases it exists to separate."""
    bed_img, bed = _bounded_bed()
    flush_img, flush = _diffuse_flush()

    bed_v = cv_utils.red_region_character(bed_img, bed)
    flush_v = cv_utils.red_region_character(flush_img, flush)

    assert bed_v["verdict"] == "bed_like", bed_v
    assert flush_v["verdict"] == "diffuse_like", flush_v
    # And on the axes, not just the label.
    assert bed_v["edge_gradient"] > flush_v["edge_gradient"] * 3
    assert bed_v["specular_fraction"] > flush_v["specular_fraction"]


def test_erythema_can_never_reach_urgent_whatever_the_character_says():
    """THE TEST THAT MUST NOT BE DELETED.

    The whole point of this feature is a better description, not a new route to
    a same-day alarm. Redness is a colour; a bounded red area is still a
    colour. Every verdict, including the strongest, keeps the REVIEW ceiling.
    """
    for verdict in ("bed_like", "diffuse_like", "indeterminate", None):
        report = evidence.assess({
            "erythema_pct": 40.0,
            "erythema_character": {"verdict": verdict} if verdict else None,
            **CONFIRMED,
        })
        found = [f for f in report.findings if f.kind == "erythema"]
        assert found, verdict
        assert found[0].ceiling is Grade.REVIEW, verdict
        assert found[0].sufficient_for_urgent is False, verdict
        assert report.ceiling is not Grade.URGENT, (
            f"erythema alone reached URGENT with character {verdict!r}")


def test_a_bed_is_described_as_bounded_and_a_flush_is_not_called_safe():
    """Both directions of the wording. `diffuse_like` is the one that could be
    misread as the all-clear, so it carries its own limit."""
    bed = evidence.assess({"erythema_pct": 9.0,
                           "erythema_character": {"verdict": "bed_like"}})
    bed_f = [f for f in bed.findings if f.kind == "erythema"][0]
    assert "BOUNDED AREA" in bed_f.observed
    assert "has not been determined" in bed_f.observed

    flush = evidence.assess({"erythema_pct": 9.0,
                             "erythema_character": {"verdict": "diffuse_like"}})
    flush_f = [f for f in flush.findings if f.kind == "erythema"][0]
    assert "spread across the skin" in flush_f.observed
    assert any("NOT reassurance" in limit for limit in flush_f.limits), (
        "a flush was described without saying that spreading erythema is a "
        "red flag a photograph cannot rule out")


def test_the_word_wound_needs_two_mechanisms_to_agree():
    """`bed_like` alone does not put "possible wound" on a red region: the
    localisation guard must have drawn a confirmed boundary independently."""
    bed = {"erythema_character": {"verdict": "bed_like"}}
    assert lesion_role.role_for("erythema", bed) == lesion_role.UNCERTAIN, (
        "character alone claimed a wound with no confirmed localisation")
    assert (lesion_role.role_for("erythema", {**bed, **CONFIRMED})
            == lesion_role.POSSIBLE_WOUND), (
        "the path is dead: both mechanisms agreed and nothing changed")
    for verdict in ("diffuse_like", "indeterminate"):
        assert lesion_role.role_for(
            "erythema", {"erythema_character": {"verdict": verdict},
                         **CONFIRMED}) == lesion_role.UNCERTAIN, verdict


def test_the_pipeline_carries_the_character_end_to_end():
    """It reaches `features` from a real run, and the fixtures are unmoved."""
    out = execute(AnalysisJob(image_bytes=png_bytes("foot_urgent"),
                              module="foot", render_overlay=False))
    f = out.result.features
    assert (f.get("erythema_character") or {}).get("verdict") == "bed_like"
    # Unchanged: this feature describes, it does not measure or grade.
    assert str(out.result.triage.grade) == "urgent"
    assert abs(f["erythema_pct"] - 9.44) < 0.02
    assert abs(f["breakdown_pct"] - 6.05) < 0.02

    clean = execute(AnalysisJob(image_bytes=png_bytes("foot_clean"),
                                module="foot", render_overlay=False))
    assert clean.result.features.get("erythema_character") is None, (
        "characterised a region that was never isolated"
    )
