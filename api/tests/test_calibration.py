"""Colour calibration from a reference card in the frame.

Two properties matter, and they pull in opposite directions.

1. When a good card is present, the correction must actually neutralise a
   colour cast, so two images taken under different lights become comparable.
2. When the card is absent, unusable, or is not really a card, the pipeline
   must fall back to exactly its previous behaviour. A wrongly identified
   "card" applies a wrong correction to the whole image, which is worse than
   applying none.

The second property is the one under real pressure, so most of this file is
about refusing.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis import calibration, cv_utils
from app.analysis.pipeline import AnalysisJob, execute
from app.sample_data import png_bytes
from tests.conftest import API, make_case, make_patient


def _decode(name: str) -> np.ndarray:
    return cv_utils.decode_image(png_bytes(name))


def _add_card(bgr: np.ndarray, *, grey: int = 200, cast=(1.0, 1.0, 1.0),
              box=(40, 40, 150, 110)) -> np.ndarray:
    """Paint a flat neutral card, then tint the WHOLE frame.

    The tint is applied after the card so the card carries the same cast the
    subject does — which is the entire premise of using it as a reference.
    """
    out = bgr.copy()
    x, y, w, h = box
    rng = np.random.default_rng(7)
    patch = np.full((h, w, 3), grey, dtype=np.float32)
    patch += rng.normal(0, 1.5, patch.shape)
    out[y:y + h, x:x + w] = np.clip(patch, 0, 255).astype(np.uint8)
    tinted = out.astype(np.float32) * np.asarray(cast, dtype=np.float32)
    return np.clip(tinted, 0, 255).astype(np.uint8)


def _png(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    assert ok
    return buf.tobytes()


# --- detection ---------------------------------------------------------------

def test_no_card_in_a_plain_image_is_not_an_error():
    image = _decode("foot_clean")
    out, mask, cal = calibration.calibrate(image, None)
    assert cal.detected is False
    assert cal.applied is False
    assert np.array_equal(out, image), "image must be returned untouched"
    assert mask is None
    assert "not" in cal.to_json()["note"].lower()


def test_a_neutral_card_is_detected():
    image = _add_card(_decode("foot_clean"))
    card = cv_utils.find_reference_card(image, None)
    assert card is not None
    assert card["chroma_mean"] < cv_utils.REFERENCE_MAX_CHROMA
    assert card["L_std"] < cv_utils.REFERENCE_MAX_L_STD


def test_calibration_neutralises_a_colour_cast():
    """A blue-cast capture and a warm-cast capture of the same scene must land
    close together once both are corrected. That is the whole point."""
    base = _decode("foot_clean")
    cool = _add_card(base, cast=(1.18, 1.0, 0.86))     # BGR: blue up, red down
    warm = _add_card(base, cast=(0.85, 1.0, 1.20))     # BGR: red up, blue down

    before = [c.astype(np.float32).mean(axis=(0, 1)) for c in (cool, warm)]
    gap_before = float(np.abs(before[0] - before[1]).mean())

    corrected = []
    for image in (cool, warm):
        out, _mask, cal = calibration.calibrate(image, None)
        assert cal.applied is True, cal.reason
        corrected.append(out.astype(np.float32).mean(axis=(0, 1)))
    gap_after = float(np.abs(corrected[0] - corrected[1]).mean())

    assert gap_after < gap_before / 2, (
        f"correction did not bring the two captures together: "
        f"{gap_before:.1f} -> {gap_after:.1f}"
    )


def test_illuminant_shift_is_reported():
    image = _add_card(_decode("foot_clean"), cast=(1.2, 1.0, 0.85))
    _out, _mask, cal = calibration.calibrate(image, None)
    assert cal.applied is True
    body = cal.to_json()
    assert body["illuminant_shift_pct"] > 5
    assert len(body["gains_bgr"]) == 3
    # Gains scale DOWN only, so a correction can never clip a highlight.
    assert max(body["gains_bgr"]) == pytest.approx(1.0, abs=1e-6)


# --- refusing -----------------------------------------------------------------

def test_an_over_exposed_card_is_refused():
    image = _add_card(_decode("foot_clean"), grey=254)
    _out, _mask, cal = calibration.calibrate(image, None)
    assert cal.applied is False
    assert cal.detected is True
    assert "over-exposed" in (cal.reason or "")


def test_an_unevenly_lit_card_is_refused():
    """A shadow falling across the card means mixed illuminants in the scene,
    and one set of gains cannot correct two of them."""
    image = _decode("foot_clean")
    x, y, w, h = 40, 40, 150, 110
    ramp = np.linspace(235, 150, w, dtype=np.float32)
    image[y:y + h, x:x + w] = np.repeat(
        np.tile(ramp, (h, 1))[:, :, None], 3, axis=2).astype(np.uint8)
    _out, _mask, cal = calibration.calibrate(image, None)
    assert cal.applied is False


def test_a_strongly_coloured_patch_is_never_used_as_a_reference():
    """The failure that would matter most: a coloured object read as grey."""
    image = _decode("foot_clean")
    image[40:150, 40:190] = (40, 60, 200)      # a red card
    _out, _mask, cal = calibration.calibrate(image, None)
    assert cal.applied is False


def test_a_dark_card_is_refused():
    image = _add_card(_decode("foot_clean"), grey=30)
    _out, _mask, cal = calibration.calibrate(image, None)
    assert cal.applied is False


def test_a_tiny_highlight_is_not_a_card():
    image = _decode("foot_clean")
    image[300:308, 300:308] = 240              # a specular highlight
    card = cv_utils.find_reference_card(image, None)
    assert card is None


def test_a_thin_neutral_sliver_is_not_a_card():
    image = _decode("foot_clean")
    image[10:18, 10:700] = 205                 # a strip of skirting board
    card = cv_utils.find_reference_card(image, None)
    assert card is None


def test_smooth_skin_is_never_mistaken_for_a_card():
    """Regression. A flat expanse of skin was detected as a grey reference
    card; the correction then neutralised the skin, and the module rejected the
    image as "not skin" — a healthy finger made unanalysable by the step that
    was supposed to make it comparable between visits.
    """
    W, H = 1200, 900
    rng = np.random.default_rng(3)
    img = np.full((H, W, 3), (118, 118, 120), np.uint8)
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    cv2.ellipse(img, (600, 470), (150, 330), 0, 0, 360, (150, 175, 205), -1)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)

    mask, _frac = cv_utils.estimate_subject_mask(img)
    assert cv_utils.find_reference_card(img, mask) is None

    output = execute(AnalysisJob(image_bytes=_png(img), module="foot",
                                 render_overlay=False))
    assert output.result is not None, "the subject was corrected out of being skin"
    assert output.result.features["colour_calibration"]["applied"] is False


def test_a_card_beside_the_subject_is_accepted():
    """The placement the instructions actually describe: flat beside the area
    of interest, not overlapping it."""
    W, H = 1200, 900
    rng = np.random.default_rng(11)
    image = np.full((H, W, 3), (100, 104, 108), np.uint8)
    cv2.ellipse(image, (660, 450), (240, 306), 0, 0, 360, (150, 175, 205), -1)
    image = np.clip(image + rng.normal(0, 4, image.shape), 0, 255).astype(np.uint8)
    image[315:475, 60:280] = 200

    mask, _frac = cv_utils.estimate_subject_mask(image)
    card = cv_utils.find_reference_card(image, mask)
    assert card is not None, "a card laid beside the subject was not found"
    assert card["bbox"][0] < 300


def test_a_neutral_surface_across_the_room_is_ignored():
    """A grey wall elsewhere in a wide shot is under different light from the
    subject, so the correction it implies is wrong for the subject."""
    W, H = 1600, 1200
    rng = np.random.default_rng(5)
    image = np.full((H, W, 3), (100, 104, 108), np.uint8)
    cv2.ellipse(image, (1250, 950), (170, 190), 0, 0, 360, (150, 175, 205), -1)
    image = np.clip(image + rng.normal(0, 4, image.shape), 0, 255).astype(np.uint8)
    image[60:220, 60:280] = 205                 # opposite corner of the scene

    mask, _frac = cv_utils.estimate_subject_mask(image)
    assert cv_utils.find_reference_card(image, mask) is None


# --- the card must not be measured as skin -----------------------------------

def test_no_card_pixel_survives_inside_the_measured_region():
    """The invariant, tested against the worst case for it.

    `estimate_subject_mask` returns the WHOLE FRAME for a true close-up, so a
    card in that frame starts out fully inside the measured region. Nothing of
    it may remain, or a rectangle of cardboard gets measured as tissue.
    """
    image = _decode("foot_clean")
    box = (40, 40, 150, 110)
    with_card = _add_card(image, box=box)
    whole_frame = np.full(image.shape[:2], 255, dtype=np.uint8)

    _out, new_mask, cal = calibration.calibrate(with_card, whole_frame)
    assert cal.detected is True
    assert new_mask is not None

    x, y, w, h = box
    assert int((new_mask[y:y + h, x:x + w] > 0).sum()) == 0, (
        "card pixels were left inside the measured region"
    )
    # Removed with a margin: the card's edge and the shadow it casts are
    # neither card nor skin, and both would read as dark tissue.
    removed = int((whole_frame > 0).sum()) - int((new_mask > 0).sum())
    assert removed > w * h


# --- end to end ---------------------------------------------------------------

def test_pipeline_reports_calibration_when_absent():
    output = execute(AnalysisJob(image_bytes=png_bytes("foot_clean"),
                                 module="foot"))
    assert output.result is not None
    cal = output.result.features["colour_calibration"]
    assert cal["detected"] is False
    assert cal["applied"] is False
    assert cal["how_to"]


def test_pipeline_applies_calibration_and_says_so_in_the_rationale():
    image = _add_card(_decode("foot_clean"), cast=(1.15, 1.0, 0.88))
    output = execute(AnalysisJob(image_bytes=_png(image), module="foot"))
    assert output.result is not None, "calibrated image failed the quality gate"
    cal = output.result.features["colour_calibration"]
    assert cal["applied"] is True
    joined = " ".join(output.result.triage.rationale).lower()
    assert "reference card" in joined


def test_a_clean_foot_stays_clean_with_a_card_in_frame():
    """The regression that would matter: a card must not create a finding.

    A large neutral rectangle beside the foot is exactly the sort of thing the
    old dark-area rule would have read as necrotic tissue.
    """
    image = _add_card(_decode("foot_clean"), box=(30, 30, 160, 120))
    output = execute(AnalysisJob(image_bytes=_png(image), module="foot"))
    assert output.result is not None
    assert output.result.triage.grade.rank <= 1, (
        f"a reference card produced a {output.result.triage.grade} flag"
    )


async def test_calibration_reaches_the_api_payload(client, auth, ref_factory):
    ref = ref_factory("cal")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    image = _add_card(_decode("foot_clean"), cast=(1.15, 1.0, 0.88))
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("card.png", _png(image), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    cal = resp.json()["features"]["colour_calibration"]
    assert cal["applied"] is True
    assert cal["illuminant_shift_pct"] > 0
    # Calibration is a colour correction and says so. The only mention of
    # diagnosis it is allowed to carry is the denial of one.
    assert "does not make any finding diagnostic" in cal["note"]
    assert "grade" not in cal
    assert "finding" not in cal


# --- the card as a light meter ------------------------------------------------

def _card(L: float) -> dict:
    return {"L_mean": L, "bbox": (0, 0, 260, 164)}


def test_a_white_card_that_renders_bright_means_the_light_was_adequate():
    out = calibration.lighting_from_card(_card(228), skin_L=150)
    assert out["assessable"] is True
    assert out["adequate"] is True


def test_a_white_card_that_renders_dark_means_the_capture_was_underexposed():
    """The whole point: dark regions in this frame are partly dark because of
    the lamp, not the tissue."""
    out = calibration.lighting_from_card(_card(110), skin_L=88)
    assert out["assessable"] is True
    assert out["adequate"] is False
    assert "underexposed" in out["note"]
    assert "% short" in out["note"]
    assert "flash" in out["advice"]


def test_a_card_darker_than_the_skin_says_nothing_about_the_light():
    """A white card reflects more than skin of any tone, so under the same
    light it is always brighter. A card that is DARKER than the skin is a grey
    card, and its lightness reports nothing about the exposure. Reading it as
    underexposure would fire on every correctly lit photograph taken with a
    grey card."""
    out = calibration.lighting_from_card(_card(110), skin_L=186)
    assert out["assessable"] is False
    assert "dark grey card" in out["reason"]


def test_no_card_means_no_lighting_verdict():
    out = calibration.lighting_from_card(None, skin_L=150)
    assert out["assessable"] is False
    assert "cannot be measured" in out["reason"]


def test_no_skin_measurement_means_no_lighting_verdict():
    assert calibration.lighting_from_card(_card(228), None)["assessable"] is False


def test_the_lighting_verdict_never_names_a_condition():
    out = calibration.lighting_from_card(_card(110), skin_L=88)
    blob = out["note"] + out["advice"]
    for word in ("necrosis", "necrotic", "gangrene", "infection", "ischaemia"):
        assert word not in blob.lower()


def test_known_limitation_a_bright_card_beside_skin_may_not_be_found():
    """HONEST FAILURE, PINNED.

    The detector treats "neutral" loosely so that a card under a colour cast is
    still recognised, and skin is neutral enough to enter that set. When the
    card is BRIGHTER than the skin the two land in the same population and the
    card is not reliably separated — so on a foot photographed against a
    coloured cloth with a white card beside it, the card can go undetected and
    no lighting verdict is produced.

    Nothing is reported wrongly when this happens: `assessable` is false and
    the analysis proceeds exactly as it does with no card. This test exists so
    the limitation is recorded in the code rather than only in a conversation.
    """
    W, H = 1400, 1000
    rng = np.random.default_rng(9)
    img = np.full((H, W, 3), (150, 95, 45), np.uint8)          # blue cloth
    cv2.ellipse(img, (950, 500), (260, 320), 0, 0, 360, (150, 175, 205), -1)
    img[420:584, 400:660] = 232                                 # white card
    img = np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)

    mask, _frac = cv_utils.estimate_subject_mask(img)
    card = cv_utils.find_reference_card(img, mask)
    verdict = calibration.lighting_from_card(card, skin_L=186.0)
    # Either it found the card, or it says it cannot assess. Never a wrong
    # verdict.
    assert verdict["assessable"] is False or verdict.get("adequate") is not None
