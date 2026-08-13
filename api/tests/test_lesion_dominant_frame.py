"""What happens when the lesion is most of the picture.

Reported from the field as "it analyses one time in two and cannot diagnose".
The cause was not intermittency. It was framing:

`estimate_subject_mask` keeps whatever stands out from the border. On a wide
shot that is the foot against the backdrop. On a TIGHT CROP -- the framing the
crop tool explicitly asks for -- the border is skin and the thing standing out
is the WOUND, so the wound became "the subject". Every threshold is relative to
the subject's own median, the wound is uniform to itself, and the answer came
back `no_flag` over a wound filling the frame. The more carefully the user
framed the lesion, the more certainly the result was wrong.

Two changes, and one thing deliberately NOT changed:

  * the mask is widened when the segmented region is much darker than a
    surround that looks like skin -- the surround is the patient, the region is
    what is wrong with them;
  * when the lesion still dominates and nothing was measured, the module
    REFUSES instead of returning no_flag;
  * the reference stays the median. A high percentile fixes the residual case
    and brings back the false "necrotic tissue on a healthy toe" that this
    project already shipped once -- see
    test_analysis.py::test_shadow_is_not_reported_as_dead_tissue.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.types import Grade

LIGHT = (150, 175, 205)
MID = (105, 130, 165)
DARK = (75, 92, 120)
WOUND = (40, 45, 60)


def _png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _scene(skin, lesion_share=0.0, *, tight=False, wound=WOUND):
    """`lesion_share` is a fraction of the FOOT region, not of the frame."""
    W, H = (900, 900) if tight else (1200, 900)
    rng = np.random.default_rng(4)
    img = np.full((H, W, 3), (105, 108, 112), np.uint8)
    if tight:
        img[:, :] = skin
        area = float(W * H)
    else:
        rx, ry = int(W * 0.22), int(H * 0.34)
        cv2.ellipse(img, (W // 2, H // 2), (rx, ry), 0, 0, 360, skin, -1)
        area = np.pi * rx * ry
    if lesion_share > 0:
        r = int(((area * lesion_share) / np.pi) ** 0.5)
        cv2.circle(img, (W // 2, H // 2), r, wound, -1)
    img = np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)
    return execute(AnalysisJob(image_bytes=_png(img), module="foot",
                               render_overlay=False))


# --- no false positives ------------------------------------------------------

@pytest.mark.parametrize("skin", [LIGHT, MID, DARK],
                         ids=["light", "mid", "dark"])
@pytest.mark.parametrize("tight", [False, True], ids=["wide", "tight"])
def test_healthy_skin_stays_clean(skin, tight):
    out = _scene(skin, tight=tight)
    assert out.subject_error is None, "healthy skin was refused"
    assert out.result is not None
    assert out.result.triage.grade is Grade.NO_FLAG
    assert out.result.features["dark_area_pct"] == 0.0


# --- the bug: a tightly cropped lesion was invisible --------------------------

@pytest.mark.parametrize("share", [0.15, 0.25, 0.40])
def test_a_tightly_cropped_lesion_is_seen(share):
    """Every one of these returned no_flag before the mask was widened."""
    out = _scene(LIGHT, share, tight=True)
    assert out.subject_error is None
    assert out.result is not None
    assert out.result.triage.grade is Grade.URGENT, (
        f"lesion covering {share:.0%} of a tight crop graded "
        f"{out.result.triage.grade}"
    )
    assert out.result.features["dark_area_pct"] > share * 80


@pytest.mark.parametrize("share", [0.10, 0.25, 0.50])
def test_a_lesion_in_a_wide_shot_is_seen(share):
    out = _scene(LIGHT, share)
    assert out.result is not None
    assert out.result.triage.grade is Grade.URGENT


# --- the residual case must never be silent ----------------------------------

@pytest.mark.parametrize("share,tight", [(0.60, True), (0.75, True),
                                         (0.80, False)])
def test_a_dominant_lesion_asks_for_a_better_photograph(share, tight):
    """The reference is the lesion itself, so nothing can be measured against
    it. Refusing is the only honest answer; `no_flag` reads as reassurance and
    is the most dangerous output this module can produce."""
    out = _scene(LIGHT, share, tight=tight)
    assert out.subject_error is not None, (
        f"lesion covering {share:.0%} returned a grade instead of refusing"
    )
    assert "normal skin" in out.subject_error.reason
    assert "further back" in out.subject_error.hint


def test_the_refusal_can_never_raise_a_grade():
    """It only ever converts a negative into a request for a better image, so
    it cannot manufacture an alarm."""
    from app.analysis.backends.classical import ClassicalCVBackend
    from app.analysis.types import SubjectMismatch

    # With spread, as any real capture has. A perfectly flat two-value array
    # is degenerate: Otsu puts the threshold on the lower value itself and one
    # class comes out empty.
    rng = np.random.default_rng(1)
    L = np.concatenate([rng.normal(30, 4, 4000), rng.normal(200, 4, 4000)])
    L = np.clip(L, 0, 255).reshape(80, 100)
    subject = np.ones_like(L, dtype=bool)

    # Something was measured -> never refuses, whatever the histogram shows.
    for dark, brk, ery in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 5.0)]:
        ClassicalCVBackend._refuse_if_the_reference_is_the_lesion(
            L, subject, dark, brk, ery)

    # Nothing measured and the histogram is split -> refuses.
    with pytest.raises(SubjectMismatch):
        ClassicalCVBackend._refuse_if_the_reference_is_the_lesion(
            L, subject, 0.0, 0.0, 0.0)


def test_a_uniform_subject_is_not_refused():
    """A plain region with no second population must pass straight through."""
    from app.analysis.backends.classical import ClassicalCVBackend

    L = np.full((80, 100), 180.0)
    ClassicalCVBackend._refuse_if_the_reference_is_the_lesion(
        L, np.ones_like(L, dtype=bool), 0.0, 0.0, 0.0)
