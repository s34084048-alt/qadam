"""A reassuring NO_FLAG is refused when the measured region does not read as skin.

THE FIELD FAILURE THIS PINS
---------------------------
A real diabetic foot with a large dark eschar was graded NO_FLAG. The pale sole
was the same brightness as a pale clinic background, so segmentation could not
separate them and locked onto the dark regions as the "subject". Every colour
was then measured against that dark fragment, nothing read as darker than it,
and an obvious wound came back "no surface red flag" — the most dangerous output
this platform can produce.

The skin check DID fire (the measured region does not read as skin). The fix:
when that is true AND the result is the reassuring NO_FLAG, refuse rather than
report. A NO_FLAG can be read as "the foot is fine"; a refusal cannot.

NARROW BY DESIGN. "Not skin" was downgraded from a hard refusal for a real
reason (a foot under a cool fluorescent tube can read outside the skin range).
So this only overrides the REASSURING grade, and only when skin cannot be
confirmed — a detected flag is never suppressed, and every clean fixture reads
as skin and is untouched.

Synthetic images only; not a clinical claim.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.analysis.pipeline import AnalysisJob, execute
from app.sample_data import png_bytes

W, H = 960, 720


def _pale_sole_dark_eschar(background, *, clutter=True) -> bytes:
    """A pale plantar foot with a dark eschar. `background` sets whether the
    sole can be separated from it; `clutter` adds the dark off-foot objects the
    real clinic photo had (a dark chair, a monitor) that pull a border-based
    segmentation away from a pale sole."""
    rng = np.random.default_rng(7)
    img = np.full((H, W, 3), background, np.uint8)
    if clutter:
        cv2.ellipse(img, (90, 120), (150, 140), 20, 0, 360, (110, 100, 92), -1)
        cv2.rectangle(img, (760, 40), (940, 520), (150, 120, 95), -1)
        img = cv2.GaussianBlur(img, (0, 0), 9)
    foot = np.array([[300, 40], [600, 90], [680, 320], [610, 560], [470, 690],
                     [330, 700], [250, 540], [210, 300], [240, 120]], np.int32)
    cv2.fillPoly(img, [foot], (202, 207, 227))          # pale sole, high L
    img = cv2.GaussianBlur(img, (0, 0), 3)
    cv2.circle(img, (500, 250), 78, (150, 192, 212), -1)  # callus rim
    esch = np.zeros((H, W), np.uint8)
    cv2.circle(esch, (505, 244), 56, 255, -1)
    brown = np.clip(np.full_like(img, (30, 45, 70))
                    + rng.normal(0, 16, img.shape), 0, 255).astype(np.uint8)
    img[esch > 0] = brown[esch > 0]
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return buf.tobytes()


def test_no_flag_on_a_non_skin_region_is_refused_not_reported():
    """The exact field failure: eschar lost because the pale sole blended with a
    pale background. It must NOT come back as a reassuring NO_FLAG."""
    out = execute(AnalysisJob(
        image_bytes=_pale_sole_dark_eschar(background=(205, 201, 196)),
        module="foot", render_overlay=False))

    assert out.result is None, "a non-skin region was reported instead of refused"
    assert out.subject_error is not None
    assert "does not read as skin" in out.subject_error.reason
    # The guidance is actionable and names the actual fix.
    assert "contrasting background" in out.subject_error.hint.lower()


def test_the_same_foot_on_a_contrasting_background_is_read_correctly():
    """The refusal is not the module giving up — it is asking for the one thing
    that fixes it. On a dark contrasting background the SAME foot and eschar are
    measured, and the wound is found."""
    out = execute(AnalysisJob(
        image_bytes=_pale_sole_dark_eschar(background=(90, 70, 40), clutter=False),
        module="foot", render_overlay=False))

    assert out.result is not None, "a well-separated foot was refused"
    # The eschar is now measured; the grade is not the reassuring NO_FLAG.
    assert out.result.features["dark_area_pct"] > 0
    assert str(out.result.triage.grade) != "no_flag"


def test_clean_feet_still_read_no_flag():
    """The refusal must fire ONLY when the region is not skin. Well-captured
    clean feet read as skin and keep their NO_FLAG."""
    for sample in ("foot_clean", "foot_shadow_only"):
        out = execute(AnalysisJob(image_bytes=png_bytes(sample), module="foot",
                                  render_overlay=False))
        assert out.result is not None, f"{sample} was wrongly refused"
        assert str(out.result.triage.grade) == "no_flag"
        # And the skin check did not fire on them.
        assert out.result.features.get("subject_check") is None


def test_a_detected_flag_on_a_non_skin_region_is_still_surfaced():
    """The override is toward safety only. If a real flag is detected, it is
    surfaced even when the skin check is uneasy — refusing a flagged case would
    hide a finding, which is the opposite of the goal. foot_urgent carries a
    genuine finding and must never be refused by this rule."""
    out = execute(AnalysisJob(image_bytes=png_bytes("foot_urgent"), module="foot",
                              render_overlay=False))
    assert out.result is not None
    assert str(out.result.triage.grade) == "urgent"
