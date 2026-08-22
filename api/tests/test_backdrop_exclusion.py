"""The recommended blue cloth is a backdrop, not a finding on the patient.

THE FIELD FAILURE THIS PINS
---------------------------
QADAM asks the user to photograph the foot on a blue or green cloth. That
advice is right and it is in the capture guidance and in
`_widen_if_the_segmentation_split_skin`.

On a real close-up whose foot ran off the frame edges, the border-colour model
in `estimate_subject_mask` had a border made mostly of SKIN. The wideners
correctly fell back to the whole frame -- that is what they are for -- and the
recommended cloth was then measured as a finding on the patient: a "dark area"
covering a third of the imaged region, "tissue breakdown" boxes on the fabric,
and a red POSSIBLE WOUND box drawn on the backdrop.

The exclusion cannot live in the subject mask, because in this case the whole
frame IS the subject deliberately. It lives per feature region, behind two
guards.

WHY EACH GUARD EXISTS -- both are tested here, because dropping either one
turns this from a fix into a way of deleting real findings:

  1. THE REGION TOUCHES THE FRAME EDGE. A wound bed, an eschar and a bruise
     are not skin-coloured either. Without this guard the rule deletes the
     finding the module exists to report.

  2. THE REST OF THE SUBJECT READS AS SKIN. Light skin under a cool fluorescent
     tube measures a* and b* NEGATIVE -- the failure `looks_like_skin` was
     rewritten to avoid. Under that lamp a real foot's own regions could pass
     the skin test AND touch the edge. So the rule disables itself whenever
     nothing in frame reads as skin.

Synthetic images only; not a clinical claim.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.analysis import cv_utils
from app.analysis.pipeline import AnalysisJob, execute
from app.sample_data import png_bytes

W, H = 960, 720
# Deliberately runs off the left, top and bottom edges: the geometry of the
# field photograph, and the reason the border model had skin in it.
FOOT = np.array([[-40, -40], [560, -40], [660, 240], [700, 430],
                 [600, 700], [200, 760], [-40, 620]], np.int32)
SKIN = (168, 186, 208)
CLOTH = (150, 92, 48)      # the blue the capture guidance asks for


def _foot_on_blue_cloth(*, cool_light: bool = False) -> np.ndarray:
    """A close-up foot on a shaded blue cloth. `cool_light` shifts the WHOLE
    frame toward blue, as a fluorescent tube does -- skin included."""
    rng = np.random.default_rng(11)
    img = np.full((H, W, 3), CLOTH, np.uint8)
    for cx, cy, r, shade in ((880, 180, 240, 45), (860, 640, 260, -35)):
        ov = img.copy()
        cv2.circle(ov, (cx, cy), r,
                   tuple(int(np.clip(c + shade, 0, 255)) for c in CLOTH), -1)
        img = cv2.addWeighted(ov, 0.8, img, 0.2, 0)
    img = cv2.GaussianBlur(img, (0, 0), 25)
    cv2.fillPoly(img, [FOOT], SKIN)
    img = cv2.GaussianBlur(img, (0, 0), 3)
    cv2.circle(img, (300, 360), 66, (92, 96, 196), -1)      # ulcer, open bed
    cv2.circle(img, (300, 360), 42, (110, 120, 214), -1)
    if cool_light:
        img = np.clip(img.astype(np.int16) + (70, 0, -55), 0, 255).astype(np.uint8)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    return img


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _on_foot(centroid) -> bool:
    truth = np.zeros((H, W), np.uint8)
    cv2.fillPoly(truth, [FOOT], 255)
    x, y = centroid
    return bool(truth[min(y, H - 1), min(x, W - 1)])


def test_the_cloth_is_not_measured_as_a_finding():
    """The core rule. Against the unfixed code this image reported a dark area
    over 33% of the imaged region, centred on the cloth."""
    out = execute(AnalysisJob(image_bytes=_png(_foot_on_blue_cloth()),
                              module="foot", render_overlay=False))
    assert out.result is not None
    assert out.result.features["dark_area_pct"] < 1.0, (
        "the blue cloth is still being measured as a dark area on the patient")
    for lesion in out.result.lesions:
        assert _on_foot(lesion.centroid), (
            f"a {lesion.kind} finding was reported on the backdrop at "
            f"{lesion.centroid}")


def test_what_was_excluded_is_recorded_and_stated():
    """A measurement that silently shrank is worse than one that is wrong."""
    out = execute(AnalysisJob(image_bytes=_png(_foot_on_blue_cloth()),
                              module="foot", render_overlay=False))
    excluded = out.result.features.get("backdrop_excluded")
    assert excluded, "regions were dropped with no record of it"
    assert all(e["area_px"] > 0 and e["kind"] for e in excluded)
    assert any("excluded as backdrop" in line
               for line in out.result.triage.rationale), (
        "the exclusion is not stated on the page")


def test_an_interior_lesion_is_never_excluded():
    """GUARD 1. A wound bed is not skin-coloured either. Every real fixture
    keeps exactly the measurements it had -- these are the values recorded in
    SESSION_LOG for the previous commit, and this change must not move them."""
    expected = {
        "foot_clean": ("no_flag", 0.0, 0.0, 0.0),
        "foot_shadow_only": ("no_flag", 0.0, 0.0, 0.0),
        "foot_dark_area": ("review", 8.50, 0.0, 3.12),
        "foot_urgent": ("urgent", 9.44, 6.05, 0.0),
    }
    for name, (grade, ery, brk, dark) in expected.items():
        out = execute(AnalysisJob(image_bytes=png_bytes(name), module="foot",
                                  render_overlay=False))
        assert out.result is not None, f"{name} was refused"
        f = out.result.features
        assert str(out.result.triage.grade) == grade, name
        assert f["erythema_pct"] == round(ery, 2) or abs(
            f["erythema_pct"] - ery) < 0.02, f"{name} erythema moved"
        assert abs(f["breakdown_pct"] - brk) < 0.02, f"{name} breakdown moved"
        assert abs(f["dark_area_pct"] - dark) < 0.02, f"{name} dark area moved"
        assert not f.get("backdrop_excluded"), (
            f"{name} had a region excluded; nothing here is a backdrop")


def test_a_border_touching_region_on_skin_is_kept():
    """GUARD 1 again, at the unit level and in the direction that hides things:
    a region that reaches the frame edge but READS AS SKIN is not backdrop."""
    a = np.full((200, 200), 12, np.float32)      # warm throughout
    b = np.full((200, 200), 20, np.float32)
    subject = np.ones((200, 200), bool)
    feature = np.zeros((200, 200), np.uint8)
    feature[0:60, 0:60] = 255                    # touches the top-left corner
    kept, dropped = cv_utils.drop_backdrop_regions(feature, a, b, subject)
    assert not dropped
    assert kept[10, 10] == 255


def test_the_rule_disables_itself_under_a_cool_lamp():
    """GUARD 2. Under a fluorescent tube NOTHING in frame reads as skin, so
    the rule must not trim a real foot. This is the failure `looks_like_skin`
    was rewritten to avoid, and it would come straight back without it."""
    a = np.full((200, 200), -6, np.float32)      # whole frame reads cool
    b = np.full((200, 200), -18, np.float32)
    subject = np.ones((200, 200), bool)
    feature = np.zeros((200, 200), np.uint8)
    feature[0:80, 0:80] = 255
    kept, dropped = cv_utils.drop_backdrop_regions(feature, a, b, subject)
    assert not dropped, "a real foot under a cool lamp was trimmed as backdrop"
    assert (kept == feature).all()


def test_the_whole_frame_case_still_reports_the_wound():
    """The exclusion must remove the backdrop and NOTHING else. The ulcer in
    this fixture is on the foot and survives."""
    out = execute(AnalysisJob(image_bytes=_png(_foot_on_blue_cloth()),
                              module="foot", render_overlay=False))
    assert out.result.features["erythema_pct"] > 0.5, (
        "the ulcer was removed along with the backdrop")
    assert any(_on_foot(l.centroid) for l in out.result.lesions)
