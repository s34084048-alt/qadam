"""Shadow or tissue: the discrimination this module got wrong in the field.

A healthy toe was reported as "urgent — necrotic tissue" because the gap
between two toes is dark. Area and darkness cannot separate a shadow from an
eschar; both are "a dark patch". What separates them is the boundary and the
surface:

    a shadow is cast light   — soft boundary, interior as smooth as the skin
                               under it, because nothing is there but less light
    an eschar is a crust     — defined boundary, rough interior, because the
                               tissue itself changed at that line

THE RULE: a dark area that reads as cast light, in an image with NO tissue
loss, raises no urgent flag. It asks for a better photograph instead.

THE GUARD ON THE RULE: with an open wound anywhere in the frame the rule does
not apply. A shadow beside a real wound must never suppress it.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis import cv_utils
from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.types import Grade

LIGHT = (150, 175, 205)
MID = (105, 130, 165)
DARK = (70, 88, 118)


def _foot(*, shadow=False, eschar=False, wound=False, skin=LIGHT):
    W, H = 1200, 900
    rng = np.random.default_rng(3)
    img = np.full((H, W, 3), (105, 108, 112), np.uint8)
    cv2.ellipse(img, (600, 450), (280, 340), 0, 0, 360, skin, -1)

    if shadow:
        m = np.zeros((H, W), np.float32)
        cv2.ellipse(m, (600, 560), (150, 120), 0, 0, 360, 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 30)
        img = (img.astype(np.float32) * (1 - 0.60 * m[..., None])).astype(np.uint8)
    if eschar:
        reg = np.zeros((H, W), np.uint8)
        cv2.circle(reg, (600, 430), 95, 255, -1)
        crust = np.full_like(img, (36, 42, 56))
        crust = np.clip(crust + rng.normal(0, 18, crust.shape), 0, 255).astype(np.uint8)
        img[reg > 0] = crust[reg > 0]
    if wound:
        cv2.circle(img, (520, 300), 58, (120, 205, 215), -1)

    img = np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 93])
    assert ok
    out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                              render_overlay=False))
    assert out.result is not None, "the fixture failed the gates"
    return out.result


# --- the discriminator itself -------------------------------------------------

def _disc(kind: str, **kw) -> dict:
    W = H = 700
    rng = np.random.default_rng(5)
    img = np.full((H, W, 3), kw.get("skin", LIGHT), np.uint8)
    if kind == "shadow":
        m = np.zeros((H, W), np.float32)
        cv2.circle(m, (350, 350), 120, 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), kw.get("blur", 22))
        img = (img.astype(np.float32)
               * (1 - kw.get("depth", 0.55) * m[..., None])).astype(np.uint8)
        region = ((m > 0.5) * 255).astype(np.uint8)
    else:
        region = np.zeros((H, W), np.uint8)
        cv2.circle(region, (350, 350), 120, 255, -1)
        crust = np.full_like(img, (38, 44, 58))
        crust = np.clip(crust + rng.normal(0, kw.get("rough", 16), crust.shape),
                        0, 255).astype(np.uint8)
        img[region > 0] = crust[region > 0]
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    return cv_utils.dark_region_character(img, region)


@pytest.mark.parametrize("blur,depth", [(35, 0.55), (22, 0.55), (12, 0.60),
                                        (22, 0.35), (22, 0.70)])
def test_cast_light_reads_as_a_shadow(blur, depth):
    assert _disc("shadow", blur=blur, depth=depth)["verdict"] == "shadow_like"


@pytest.mark.parametrize("skin", [LIGHT, MID, DARK], ids=["light", "mid", "dark"])
def test_a_shadow_reads_the_same_on_every_skin_tone(skin):
    """The failure it replaced was harsher on dark skin. This one must not be."""
    assert _disc("shadow", skin=skin)["verdict"] == "shadow_like"


@pytest.mark.parametrize("rough", [6, 16, 28])
def test_a_crust_reads_as_tissue(rough):
    assert _disc("eschar", rough=rough)["verdict"] == "tissue_like"


def test_the_verdict_never_names_a_condition():
    """An eschar, a bruise and dark pigmentation are all "tissue_like". This
    measurement cannot separate them and does not pretend to."""
    meaning = _disc("eschar")["meaning"]
    assert "does NOT say what" in meaning
    assert "bruise" in meaning and "pigmentation" in meaning


def test_a_region_too_small_to_characterise_says_so():
    img = np.full((700, 700, 3), LIGHT, np.uint8)
    tiny = np.zeros((700, 700), np.uint8)
    cv2.circle(tiny, (350, 350), 5, 255, -1)
    assert cv_utils.dark_region_character(img, tiny)["verdict"] == "indeterminate"


# --- the rule -----------------------------------------------------------------

def test_a_broad_shadow_with_no_tissue_loss_asks_for_a_better_photograph():
    result = _foot(shadow=True)
    assert result.features["dark_area_pct"] > 5, "fixture did not produce a dark area"
    assert result.features["dark_area_character"]["verdict"] == "shadow_like"

    assert result.triage.grade is not Grade.URGENT
    prompt = result.features["re_image_required"]
    assert prompt is not None
    assert "flash" in prompt["instruction"]
    assert "toes held apart" in prompt["instruction"]
    assert result.triage.rationale[0].startswith("The dark area has a soft boundary")


def test_a_crust_is_not_suppressed():
    result = _foot(eschar=True)
    assert result.features["dark_area_character"]["verdict"] == "tissue_like"
    assert result.features["re_image_required"] is None
    assert result.triage.grade is Grade.URGENT


def test_a_shadow_beside_a_real_wound_suppresses_nothing():
    """The guard on the rule. Tissue loss in the frame disarms it entirely —
    otherwise a shadow next to an ulcer would silence the ulcer."""
    result = _foot(shadow=True, wound=True)
    assert result.features["breakdown_pct"] > 0
    assert result.features["re_image_required"] is None
    assert result.triage.grade is Grade.URGENT


def test_healthy_skin_is_still_clean():
    result = _foot()
    assert result.triage.grade is Grade.NO_FLAG
    assert result.features["re_image_required"] is None


def test_the_rule_can_only_lower_a_grade_never_raise_one():
    """It exists to stop a false alarm. It must not be able to create one."""
    shadowed = _foot(shadow=True)
    assert shadowed.triage.grade.rank <= Grade.REVIEW.rank


# --- callus or slough: the same problem one axis over -------------------------
#
# Both are yellow and both sit on the surface, so the b* threshold that finds
# one finds the other. A field capture showed thick callus on a toe measured as
# "tissue breakdown".
#
# The asymmetry with the shadow rule is the important part and is asserted
# below: a shadow is nothing, so it lowers a grade. Callus is NOT nothing — an
# ulcer very often lies underneath it — so it changes no grade at all.

def _yellow(kind: str, *, seed=4, skin=LIGHT, thickness=22) -> dict:
    rng = np.random.default_rng(seed)
    img = np.full((700, 700, 3), skin, np.uint8)
    region = np.zeros((700, 700), np.uint8)
    cv2.circle(region, (350, 350), 110, 255, -1)
    if kind == "callus":
        base = np.full_like(img, (120, 190, 215))
        base = np.clip(base + rng.normal(0, 7, base.shape), 0, 255).astype(np.uint8)
        soft = cv2.GaussianBlur((region > 0).astype(np.float32), (0, 0),
                                thickness)[..., None]
        img = (img * (1 - soft) + base * soft).astype(np.uint8)
    else:
        wet = np.full_like(img, (110, 195, 220))
        wet = np.clip(wet + rng.normal(0, 10, wet.shape), 0, 255).astype(np.uint8)
        img[region > 0] = wet[region > 0]
        for _ in range(30):
            cx, cy = rng.integers(270, 430, 2)
            cv2.circle(img, (int(cx), int(cy)), int(rng.integers(3, 7)),
                       (245, 250, 252), -1)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    return cv_utils.yellow_region_character(img, region)


@pytest.mark.parametrize("seed", [4, 11, 23])
@pytest.mark.parametrize("thickness", [14, 22, 30])
def test_dry_keratin_reads_as_callus(seed, thickness):
    assert _yellow("callus", seed=seed,
                   thickness=thickness)["verdict"] == "callus_like"


@pytest.mark.parametrize("skin", [LIGHT, MID, DARK], ids=["light", "mid", "dark"])
def test_the_verdict_holds_across_skin_tones(skin):
    assert _yellow("callus", skin=skin)["verdict"] == "callus_like"
    assert _yellow("slough", skin=skin)["verdict"] == "slough_like"


@pytest.mark.parametrize("seed", [4, 11, 23])
def test_moist_tissue_in_a_defect_reads_as_slough(seed):
    assert _yellow("slough", seed=seed)["verdict"] == "slough_like"


def test_callus_never_lowers_a_grade():
    """THE ASYMMETRY. A shadow verdict lowers the grade because a shadow is
    nothing. A callus verdict must not, because an ulcer very often lies under
    callus and is invisible until it is pared back — suppressing here would
    hide the wound this module exists to find."""
    W, H = 1200, 900
    rng = np.random.default_rng(4)
    img = np.full((H, W, 3), (150, 95, 45), np.uint8)
    cv2.ellipse(img, (600, 450), (280, 340), 0, 0, 360, LIGHT, -1)
    region = np.zeros((H, W), np.uint8)
    cv2.circle(region, (600, 430), 95, 255, -1)
    base = np.full_like(img, (120, 190, 215))
    base = np.clip(base + rng.normal(0, 7, base.shape), 0, 255).astype(np.uint8)
    soft = cv2.GaussianBlur((region > 0).astype(np.float32), (0, 0), 22)[..., None]
    img = (img * (1 - soft) + base * soft).astype(np.uint8)
    img = np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 93])
    assert ok

    out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                              render_overlay=False))
    assert out.result is not None
    assert out.result.features["yellow_area_character"]["verdict"] == "callus_like"
    # The grade is untouched, and there is no re-image suppression from it.
    assert out.result.triage.grade is Grade.URGENT
    assert out.result.features["re_image_required"] is None

    # What it DOES do is ask the question only a person can answer.
    asks = " ".join(q["ask"] for q in out.result.features["clarifying_questions"])
    assert "skin actually broken" in asks


def test_the_callus_verdict_says_it_is_not_reassurance():
    meaning = _yellow("callus")["meaning"]
    assert "does NOT mean harmless" in meaning
    assert "ulcer often lies underneath" in meaning
