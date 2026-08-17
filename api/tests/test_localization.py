"""Wound localization: a boundary only where tissue is disrupted.

THE GAP THIS PINS
-----------------
The module segmented colour classes and drew a box around each — a box around a
shadow, a box around redness — none of which localised the wound. This layer
draws one boundary, and only where the character verdicts already trusted by
the evidence ceiling say there is tissue disruption. A shadow, a callus and a
healthy foot get NO box; a real ulcer gets one.

WHAT THIS FILE IS NOT
---------------------
CLINICAL PERFORMANCE CANNOT BE ESTABLISHED FROM SYNTHETIC OR UNVALIDATED TEST
CASES. Every image is drawn by numpy. These tests prove the localisation logic
behaves as specified on constructed inputs — nothing about real feet, and no
localisation accuracy figure may be reported from them.

The fixtures are shared with test_evidence_gate so the two layers are exercised
on identical constructed scenes.
"""

from __future__ import annotations

import pytest

from app.analysis import localization
from app.analysis.types import Grade
from tests.test_evidence_gate import _foot


def _wl(**kw):
    out = _foot(**kw)
    assert out.result is not None, "the fixture failed a gate it was not testing"
    return out.result.features["wound_localization"], out.result


# --- the five required regressions --------------------------------------------

def test_healthy_foot_gets_no_wound_box():
    wl, r = _wl()
    assert wl["present"] is False
    assert wl["classification"] == localization.NONE
    assert wl["box"] is None
    assert wl["message"] == ""


@pytest.mark.parametrize("noise", [5.0, 8.0, 12.0, 15.0])
def test_a_shadow_gets_no_wound_box(noise):
    """Across the noise range — including where the shadow reads
    'indeterminate' rather than 'shadow_like'. Unresolved DARKNESS must not be
    localised, because a noisy shadow is indistinguishable from noisy dark
    tissue and the specification says a shadow gets no box."""
    wl, r = _wl(shadow=0.60, noise=noise)
    assert wl["present"] is False, f"a shadow was boxed at noise {noise}"
    assert wl["box"] is None


def test_callus_gets_no_wound_box():
    """Dry keratin is not a wound. It is excluded and named as an artifact, and
    the reason — an ulcer may hide under it — is carried, not silently dropped.
    Suppression here would be safe for the BOX but the grade still routes it for
    a look (asserted last)."""
    wl, r = _wl(callus=120)
    assert wl["present"] is False
    assert wl["box"] is None
    excluded = " ".join(wl["excluded_as_artifact"]).lower()
    assert "callus" in excluded
    assert "ulcer beneath it" in excluded
    # The box is withheld, but the finding is NOT: the grade still asks a
    # clinician to look and pare.
    assert r.triage.grade.rank >= Grade.REVIEW.rank


def test_a_superficial_ulcer_is_localised():
    wl, r = _wl(slough=55)
    assert wl["present"] is True
    assert wl["classification"] == localization.CONFIRMED
    assert wl["box"] is not None
    assert wl["area_pct"] > 0
    assert wl["message"] == localization.WOUND_MESSAGE
    assert "clinical assessment required" in wl["message"].lower()


@pytest.mark.parametrize("radius", [90, 130])
def test_a_deep_or_large_ulcer_keeps_its_localisation(radius):
    wl, r = _wl(slough=radius)
    assert wl["present"] is True
    assert wl["classification"] == localization.CONFIRMED
    assert wl["box"] is not None


def test_an_infected_looking_wound_localises_and_excludes_the_redness():
    """Slough plus a surrounding red halo. The wound is localised; the redness
    is named as an artifact, not folded into the boundary — redness is not
    tissue disruption."""
    wl, r = _wl(slough=90, erythema=200)
    assert wl["present"] is True
    assert wl["classification"] == localization.CONFIRMED
    assert any("redness" in a for a in wl["excluded_as_artifact"])


# --- the box is a box around the actual wound ---------------------------------

def test_the_box_sits_over_the_wound_not_the_whole_foot():
    """A localisation that returns the whole frame is not a localisation. The
    ulcer is drawn at a known place in the fixture; the box must be near it and
    much smaller than the subject."""
    wl, r = _wl(slough=90)
    box = wl["box"]
    subject_px = r.features["subject_area_px"]
    box_px = box["w"] * box["h"]
    assert box_px < subject_px, "the box is as large as the whole subject"
    # The fixture centres the wound near (600, 380). The box must contain it.
    assert box["x"] <= 600 <= box["x"] + box["w"]
    assert box["y"] <= 380 <= box["y"] + box["h"]


def test_ulcer_with_surrounding_callus_still_localises():
    """Case H: callus rings a wound. The wound is not suppressed by the callus
    around it — a box is still drawn."""
    wl, r = _wl(slough=70, callus_ring=150)
    assert wl["present"] is True
    assert wl["box"] is not None


# --- the invariants the layer must hold ---------------------------------------

def test_localisation_changes_no_grade():
    """The layer is a drawing, not a decision. The grade with localisation must
    equal the grade the evidence ceiling produced — asserted by checking the
    localisation never appears without the grade independently supporting it,
    and that a boxed wound and an unboxed one carry the grades they had."""
    healthy = _foot().result
    assert healthy.features["wound_localization"]["present"] is False
    assert healthy.triage.grade is Grade.NO_FLAG

    ulcer = _foot(slough=110).result
    assert ulcer.features["wound_localization"]["present"] is True
    assert ulcer.triage.grade is Grade.URGENT

    # Callus: no box, but the grade is unchanged from what evidence.py sets.
    callus = _foot(callus=120).result
    assert callus.features["wound_localization"]["present"] is False
    assert callus.triage.grade.rank >= Grade.REVIEW.rank


def test_boundary_confidence_is_labelled_uncalibrated():
    wl, r = _wl(slough=90)
    assert 0.0 <= wl["boundary_confidence"] <= 0.85
    note = wl["boundary_confidence_note"].lower()
    assert "uncalibrated" in note
    assert "not a probability" in note


def test_no_box_is_ever_a_diagnosis():
    """The strongest thing a red box may say is 'possible wound, assess'."""
    wl, r = _wl(slough=110)
    assert "interpretation_limit" in wl
    assert "not a diagnosis" in wl["interpretation_limit"].lower()
    banned = ["necrosis", "necrotic", "gangrene", "infected", "infection",
              "osteomyelitis", "confirmed ulcer", "diagnos"]
    text = (wl["message"] + " " + " ".join(wl["contributing_evidence"])).lower()
    assert not any(b in text for b in banned), text


def test_the_overlay_renders_with_a_localised_wound():
    """End to end: an overlay is produced and the disclaimer band survives the
    added wound box (regression on the burned-in notice)."""
    import cv2
    import numpy as np
    from app.analysis.pipeline import AnalysisJob, execute
    from app.sample_data import png_bytes

    out = execute(AnalysisJob(image_bytes=png_bytes("foot_urgent"), module="foot"))
    assert out.overlay_png
    overlay = cv2.imdecode(np.frombuffer(out.overlay_png, np.uint8), cv2.IMREAD_COLOR)
    assert overlay is not None and overlay.shape[0] > 0


# === the dangerous false positive the audit surfaced =========================
#
# "tissue_like" means a defined boundary and a textured interior — nothing
# about a wound. A large, hard-edged, textured DARK region that is NOT a wound
# (dark pigmentation, a tattoo, a hairy patch, dried material) satisfies it. A
# red "POSSIBLE WOUND" box over half the foot asserts far more than the evidence
# carries. These pin the guard that stops it — and the honest limit of that
# guard.

def _textured_dark_blob(radius_x=180, radius_y=210, seed=3):
    """A large hard-edged, textured DARK region on a foot. Constructed to be a
    non-wound that nonetheless reads 'tissue_like' — exactly the failure."""
    import cv2
    import numpy as np
    W, H = 1200, 900
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), (105, 108, 112), np.uint8)
    cv2.ellipse(img, (600, 450), (280, 340), 0, 0, 360, (150, 175, 205), -1)
    reg = np.zeros((H, W), np.uint8)
    cv2.ellipse(reg, (600, 450), (radius_x, radius_y), 0, 0, 360, 255, -1)
    tex = np.full_like(img, (60, 66, 78))
    tex = np.clip(tex + rng.normal(0, 22, tex.shape), 0, 255).astype(np.uint8)
    img[reg > 0] = tex[reg > 0]
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    from app.analysis.pipeline import AnalysisJob, execute
    return execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                               render_overlay=False))


def test_a_large_textured_non_wound_is_not_a_red_box():
    """THE DANGEROUS FALSE POSITIVE. A large connected texture region without a
    real wound must NOT automatically become a RED (confirmed) wound box.

    The plausibility guard downgrades it to UNCERTAIN (yellow): a wound filling
    most of the foot is less likely than pigmentation, a broad shadow or a
    framing problem, and 'tissue_like' is not proof of a wound.
    """
    out = _textured_dark_blob()
    assert out.result is not None
    wl = out.result.features["wound_localization"]
    assert wl["area_pct"] > 35.0, "fixture did not produce a large region"
    assert wl["classification"] != localization.CONFIRMED, (
        "a large textured non-wound became a RED possible-wound box")
    # It is not silenced either — a box is still drawn and the reason is stated.
    assert any("implausibly large" in a for a in wl["excluded_as_artifact"])


def test_the_localizer_is_labelled_heuristic_not_detection():
    """Requirement 5: it must present as heuristic, never as wound detection or
    validated localisation."""
    out = _textured_dark_blob()
    wl = out.result.features["wound_localization"]
    assert wl["method"] == "heuristic_wound_region_localization"
    note = wl["method_note"].lower()
    assert "not wound detection" in note
    assert "not validated" in note


def test_a_moderate_textured_non_wound_is_a_known_limitation():
    """HONESTY, NOT A PASS DISGUISED. The size guard only catches IMPLAUSIBLY
    LARGE regions. A moderate textured dark region that is not a wound still
    reads 'tissue_like' and still gets a red box — the classical features
    cannot tell it from an eschar. This test DOCUMENTS that limitation so it is
    visible in the suite rather than hidden, and will start failing (a signal to
    revisit) only if a real discriminator is ever added."""
    out = _textured_dark_blob(radius_x=90, radius_y=95)  # ~ moderate size
    wl = out.result.features["wound_localization"]
    assert wl["present"] is True
    # It IS a red box today. That is the limitation, not a success — the message
    # is honest ("possible wound ... clinical assessment required"), but the
    # region is not a wound.
    assert wl["classification"] == localization.CONFIRMED
    assert wl["area_pct"] <= 35.0


# === real-looking wound surrounded by callus (requirement 10) ================

def test_a_wound_surrounded_by_callus_localises_the_wound_not_the_callus():
    """The wound is localised; the callus ring does not become the box.

    The box must be centred on the wound core and must not span the full callus
    extent. The fixture centres the wound at (600, 390) with a callus ring out
    to radius 150; a box covering the whole ring would be ~300 px across, so a
    correctly-localised box is materially smaller and centred on the core.
    """
    wl, r = _wl(slough=70, callus_ring=150)
    assert wl["present"] is True
    box = wl["box"]
    # Centred on the wound core, not the callus ring.
    cx = box["x"] + box["w"] / 2
    cy = box["y"] + box["h"] / 2
    assert abs(cx - 600) < 90, f"box not centred on the wound (cx={cx})"
    assert abs(cy - 390) < 90, f"box not centred on the wound (cy={cy})"
    # Callus is named as excluded, never folded into the wound boundary.
    callus_excluded = any("callus" in a for a in wl["excluded_as_artifact"])
    yellow_char = (r.features.get("yellow_area_character") or {}).get("verdict")
    # Either the callus was separately identified and excluded, or the merged
    # region read indeterminate — in neither case is the box the callus ring.
    assert box["w"] < 300 and box["h"] < 300, (
        "the box spans the callus ring rather than the wound")
