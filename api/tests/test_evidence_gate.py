"""The evidence gate: what the pixels are allowed to claim.

THE FAILURE THESE TESTS PIN
---------------------------
A visually healthy foot was graded URGENT by two independent routes, both
reproduced before the fix and both asserted here:

  * a shadow whose character came back "indeterminate" — the module's own
    statement that it could not tell — fell through to the urgent branch,
    because the shadow rule tested for "shadow_like" exactly;
  * dry callus, correctly identified as "callus_like", crossed the urgent
    breakdown threshold because nothing consumed that verdict.

WHAT THESE TESTS ARE NOT
------------------------
CLINICAL PERFORMANCE CANNOT BE ESTABLISHED FROM SYNTHETIC OR UNVALIDATED TEST
CASES. Every image below is drawn by numpy. Passing this file says the decision
logic behaves as specified on constructed inputs; it says NOTHING about
sensitivity, specificity or accuracy on real feet, and no figure derived from
it may be reported as clinical performance. This project has no labelled
clinical images.

What the file does buy is determinism: the two failure routes above cannot
return silently, and the true positives cannot be traded away to close them.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis import cv_utils, evidence
from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.types import Grade

LIGHT = (150, 175, 205)
MID = (105, 130, 165)
W, H = 1200, 900


def _foot(*, shadow=0.0, blur=28, eschar=0, slough=0, callus=0, scatter=0,
          erythema=0, skin=LIGHT, noise=6.0, seed=3, backdrop=(105, 108, 112),
          jpeg=92, blurred=False, callus_ring=0, return_core=False):
    """One constructed foot. Nothing here is a photograph of a patient.

    `callus_ring` draws a keratin annulus AROUND the central slough wound, so
    the two coexist the way callus commonly rings a real ulcer. `return_core`
    also hands back the mask of the slough bed alone, so a test can prove the
    wound is characterised INDEPENDENTLY of the surrounding callus.
    """
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), backdrop, np.uint8)
    cv2.ellipse(img, (600, 450), (280, 340), 0, 0, 360, skin, -1)

    if callus_ring > 0:
        ring = np.zeros((H, W), np.float32)
        cv2.circle(ring, (600, 390), callus_ring, 1.0, -1)
        cv2.circle(ring, (600, 390), callus_ring - 30, 0.0, -1)
        ring = cv2.GaussianBlur(ring, (0, 0), 12)[..., None]
        keratin = np.full_like(img, (120, 190, 215), np.uint8)
        img = (img * (1 - ring) + keratin * ring).astype(np.uint8)

    if shadow > 0:
        m = np.zeros((H, W), np.float32)
        cv2.ellipse(m, (600, 600), (150, 120), 0, 0, 360, 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), blur)
        img = (img.astype(np.float32) * (1 - shadow * m[..., None])).astype(np.uint8)

    if erythema > 0:
        reg = np.zeros((H, W), np.float32)
        cv2.circle(reg, (600, 400), erythema, 1.0, -1)
        reg = cv2.GaussianBlur(reg, (0, 0), 25)[..., None]
        red = np.full_like(img, (120, 120, 215), np.uint8)
        img = (img * (1 - reg) + red * reg).astype(np.uint8)

    if callus > 0:
        reg = np.zeros((H, W), np.float32)
        cv2.circle(reg, (600, 380), callus, 1.0, -1)
        reg = cv2.GaussianBlur(reg, (0, 0), 22)[..., None]
        keratin = np.full_like(img, (120, 190, 215), np.uint8)
        img = (img * (1 - reg) + keratin * reg).astype(np.uint8)

    if eschar > 0:
        reg = np.zeros((H, W), np.uint8)
        cv2.circle(reg, (600, 380), eschar, 255, -1)
        crust = np.full_like(img, (36, 42, 56))
        crust = np.clip(crust + rng.normal(0, 18, crust.shape), 0, 255).astype(np.uint8)
        img[reg > 0] = crust[reg > 0]

    core_mask = None
    if slough > 0:
        reg = np.zeros((H, W), np.uint8)
        cv2.circle(reg, (600, 390 if callus_ring else 380), slough, 255, -1)
        bed = np.full_like(img, (120, 205, 215))
        bed = np.clip(bed + rng.normal(0, 12, bed.shape), 0, 255).astype(np.uint8)
        img[reg > 0] = bed[reg > 0]
        cy0 = 390 if callus_ring else 380
        for _ in range(28):
            cx = int(rng.integers(600 - slough // 2, 600 + slough // 2))
            cy = int(rng.integers(cy0 - slough // 2, cy0 + slough // 2))
            cv2.circle(img, (cx, cy), int(rng.integers(3, 8)), (245, 250, 252), -1)
        core_mask = reg

    for _ in range(scatter):
        cx = int(rng.integers(430, 770)); cy = int(rng.integers(230, 670))
        cv2.circle(img, (cx, cy), int(rng.integers(9, 15)), (120, 195, 218), -1)

    img = np.clip(img + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    if blurred:
        img = cv2.GaussianBlur(img, (0, 0), 9)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    assert ok
    if return_core:
        # The characterisation of the slough bed ALONE, on the same encoded
        # image, so a test can show the wound is seen independently of callus.
        decoded = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        core_char = cv_utils.yellow_region_character(decoded, core_mask)
        out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                                  render_overlay=False))
        return out, core_char
    return execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                               render_overlay=False))


def _result(**kw):
    out = _foot(**kw)
    assert out.result is not None, "the fixture failed a gate it was not testing"
    return out.result


# --- 1-3. the healthy foot, which is what started this ------------------------

def test_1_visually_healthy_foot_raises_nothing():
    r = _result()
    assert r.triage.grade is Grade.NO_FLAG
    ev = r.features["evidence"]
    assert ev["appearance"] == evidence.NORMAL
    # And "normal" is never allowed to read as "healthy".
    assert "not a statement that the foot is healthy" in " ".join(ev["notes"]).lower()


@pytest.mark.parametrize("skin", [LIGHT, MID], ids=["light", "mid"])
def test_2_normal_pigmentation_is_not_a_finding(skin):
    r = _result(skin=skin)
    assert r.triage.grade is Grade.NO_FLAG


@pytest.mark.parametrize("noise", [2.0, 5.0, 8.0, 12.0, 15.0])
def test_3_a_shadow_on_a_healthy_foot_is_never_urgent(noise):
    """THE ORIGINAL FALSE POSITIVE, across the noise range that produced it.

    At noise >= 12 the interior-texture measurement exceeds its shadow bound
    while the edge measurement does not, so the character comes back
    "indeterminate". That verdict used to fall straight through to urgent.
    """
    r = _result(shadow=0.60, noise=noise)
    assert r.features["breakdown_pct"] == 0.0, "fixture grew a wound"
    assert r.triage.grade is not Grade.URGENT
    assert r.triage.confidence <= 0.6


def test_3b_indeterminate_darkness_cannot_reach_urgent():
    """The fail-open, stated directly against the evidence layer rather than
    through an image, so it cannot be lost to fixture drift."""
    report = evidence.assess(
        {"dark_area_pct": 40.0, "dark_area_character": {"verdict": "indeterminate"},
         "dark_coherence": {"dominant_fraction": 1.0, "components": 1}},
        quality_factor=1.0,
    )
    assert report.ceiling is Grade.REVIEW
    dark = next(f for f in report.findings if f.kind == "dark_area")
    assert dark.sufficient_for_urgent is False
    assert "disagreement is not evidence" in " ".join(dark.limits).lower()


# --- 4. mild redness ----------------------------------------------------------

def test_4_mild_redness_never_reaches_urgent():
    r = _result(erythema=110)
    assert r.triage.grade.rank <= Grade.REVIEW.rank
    ery = next(f for f in r.features["evidence"]["findings"]
               if f["kind"] == "erythema")
    assert ery["sufficient_for_urgent"] is False
    assert "temperature is not inferable" in " ".join(ery["limits"]).lower()


# --- 5-7. genuine findings, which must survive the fix ------------------------

def test_5_a_visible_superficial_wound_is_reported():
    r = _result(slough=55)
    assert r.features["breakdown_pct"] > 0
    assert r.triage.grade.rank >= Grade.REVIEW.rank


@pytest.mark.parametrize("radius", [80, 110])
def test_6_a_clear_ulcer_still_reaches_urgent(radius):
    r = _result(slough=radius)
    assert r.features["yellow_area_character"]["verdict"] == "slough_like"
    assert r.triage.grade is Grade.URGENT
    assert r.features["grade_capped_by_evidence"] is False


@pytest.mark.parametrize("noise", [6.0, 12.0])
def test_7_a_crust_still_reaches_urgent(noise):
    """The discrimination that matters: a real crust reads tissue_like and is
    NOT capped, on the same noisy capture that caps a shadow."""
    r = _result(eschar=95, noise=noise)
    assert r.features["dark_area_character"]["verdict"] == "tissue_like"
    assert r.triage.grade is Grade.URGENT


def test_7b_a_shadow_beside_a_real_wound_suppresses_nothing():
    r = _result(slough=80, shadow=0.55)
    assert r.features["breakdown_pct"] > 0
    assert r.triage.grade is Grade.URGENT
    assert r.features["re_image_required"] is None


# --- 8-10. images that cannot carry a claim -----------------------------------

def test_8_a_poor_quality_image_is_not_interpreted():
    out = _foot(blurred=True, eschar=95)
    if out.result is None:
        assert not out.quality.passed          # rejected outright: correct
        assert out.quality.failures
        return
    # Analysable but unreliable: no urgent claim, and it says why.
    assert out.result.triage.grade is not Grade.URGENT
    assert out.result.features["evidence"]["appearance"] == evidence.UNREADABLE


def test_8b_poor_quality_cannot_be_compensated_by_confidence():
    """Confidence must fall with evidence quality, never rise to cover it."""
    report = evidence.assess(
        {"dark_area_pct": 30.0, "dark_area_character": {"verdict": "tissue_like"},
         "dark_coherence": {"dominant_fraction": 1.0, "components": 1}},
        quality_factor=0.3,
    )
    assert report.appearance == evidence.UNREADABLE
    assert report.ceiling.rank <= Grade.REVIEW.rank


def test_9_an_ambiguous_image_says_so_rather_than_guessing():
    r = _result(shadow=0.60, noise=14.0)
    ev = r.features["evidence"]
    assert r.triage.grade is not Grade.URGENT
    assert ev["ceiling"] != str(Grade.URGENT)
    # The clarifying question that settles it is offered.
    asks = " ".join(q["ask"] for q in r.features["clarifying_questions"])
    assert "flash" in asks.lower()


def test_10_background_interference_is_declared_not_absorbed():
    """A skin-coloured backdrop. The measurement is still made, but the
    denominator it was made against is stated."""
    r = _result(backdrop=(150, 175, 205), slough=90)
    assert "denominator" in r.features
    note = r.features["denominator"]["note"].lower()
    assert "whole frame" in note or "segmented foot region" in note


def test_10b_scattered_colour_is_not_a_wound():
    """Twenty flecks summing past the threshold are still twenty flecks. The
    area alone cannot tell them from one wound of the same total size."""
    r = _result(scatter=40)
    assert r.features["breakdown_pct"] >= 1.5, "fixture did not clear the threshold"
    assert r.features["breakdown_coherence"]["components"] > 5
    assert r.triage.grade is not Grade.URGENT
    assert r.features["grade_capped_by_evidence"] is True


# --- the invariants the layer must hold --------------------------------------

def test_the_evidence_layer_can_only_ever_lower_a_grade():
    """A layer that could raise a grade could invent an emergency out of a bad
    photograph. Asserted over the whole constructed set."""
    cases = [
        {}, {"shadow": 0.60}, {"shadow": 0.60, "noise": 14.0}, {"callus": 90},
        {"scatter": 40}, {"eschar": 95}, {"slough": 80}, {"erythema": 110},
        {"slough": 80, "shadow": 0.55}, {"eschar": 95, "noise": 12.0},
    ]
    for kw in cases:
        out = _foot(**kw)
        if out.result is None:
            continue
        f = out.result.features
        if f.get("grade_capped_by_evidence"):
            # A cap must have moved the grade DOWN to the ceiling, never up.
            assert out.result.triage.grade.rank <= Grade.REVIEW.rank, kw


def test_no_finding_is_ever_deleted_only_capped():
    """The gate lowers what a measurement is allowed to CLAIM. It must never
    remove the measurement, or a reviewer loses the thing they need to check."""
    r = _result(callus=120)
    assert r.features["breakdown_pct"] > 0
    assert any(l.kind == "tissue_breakdown" for l in r.lesions)
    assert r.features["evidence"]["findings"]


def test_observation_is_never_phrased_as_a_diagnosis():
    """Section 3 of the specification, enforced. 'observed' describes pixels."""
    banned = ["necrosis", "necrotic", "gangrene", "infected", "infection",
              "osteomyelitis", "ischaemia", "ischemia", "cellulitis", "sepsis"]
    for kw in ({"eschar": 95}, {"slough": 80}, {"callus": 90}, {"erythema": 110}):
        out = _foot(**kw)
        if out.result is None:
            continue
        for finding in out.result.features["evidence"]["findings"]:
            text = finding["observed"].lower()
            assert not any(b in text for b in banned), (kw, finding["observed"])


def test_the_parameters_declare_they_are_not_validated():
    report = evidence.assess({"dark_area_pct": 0.0}, quality_factor=1.0)
    j = report.to_json()
    assert "not clinically validated" in j["parameter_status"].lower()
    assert set(j["parameters"]) == set(evidence.PARAMS)
    # And what a photograph cannot settle is carried on every report.
    assert "tissue viability" in j["cannot_be_determined_from_a_photograph"]
    assert "infection" in j["cannot_be_determined_from_a_photograph"]


# === CASE H: a real ulcer with surrounding callus ============================
#
# The second safety audit found this scenario verified only by an ad-hoc probe,
# not by a committed test. It is the case where the false-positive fix is most
# likely to have quietly broken something: callus caps grades, and a wound
# ringed by callus must not be dragged down by it. Pinned here permanently,
# through the real pipeline. Two sub-cases, because the honest behaviour has
# two branches.

def test_case_H_visible_ulcer_ringed_by_callus_reaches_urgent_uncapped():
    """The wound is visible through/beside the callus.

    Proves, in one real-pipeline run:
      1. the ulcer is characterised INDEPENDENTLY of the callus (its bed reads
         slough_like on its own);
      2. the callus does not SUPPRESS it (breakdown area survives);
      3. the callus does not turn it NORMAL (appearance is abnormal);
      4. the genuine ulcer still reaches URGENT;
      5. the callus ceiling does NOT cap this genuine slough-like wound.
    """
    out, core_char = _foot(slough=70, callus_ring=150, return_core=True)
    assert out.result is not None
    r = out.result
    f = r.features

    # 1. Detected independently of the surrounding callus.
    assert core_char["verdict"] == "slough_like", (
        "the wound bed alone did not read as slough — the fixture is wrong, "
        f"got {core_char}")

    # 2. Not suppressed.
    assert f["breakdown_pct"] > 0
    assert any(les.kind == "tissue_breakdown" for les in r.lesions)

    # 3. Not turned normal by the presence of callus.
    assert f["evidence"]["appearance"] != evidence.NORMAL

    # 4. Still reaches urgent.
    assert r.triage.grade is Grade.URGENT

    # 5. The callus ceiling did not cap a genuine wound. This is the specific
    #    regression: a callus_like verdict caps to REVIEW, and it must not fire
    #    on a wound the detector can actually see.
    assert f["grade_capped_by_evidence"] is False
    assert f["evidence"]["ceiling"] == str(Grade.URGENT)


def test_case_H_callus_dominant_reading_caps_but_never_reassures():
    """The other branch: callus is the dominant surface reading (pure callus,
    no visible wound bed). The platform cannot confirm a wound from the image,
    so the SAFE answer is to route a person to look and pare — never to fall
    silent, and never to call it reassurance.

    Proves:
      3. callus does not turn the image NORMAL;
      6. the rationale states, in plain words, that callus is NOT reassurance;
      + the wound is not suppressed to a monitor/no-flag level, and the
        clarifying question that settles it (pare and look) is asked.
    """
    r = _result(callus=120)

    # Not normal, not silent.
    assert r.features["evidence"]["appearance"] != evidence.NORMAL
    assert r.triage.grade.rank >= Grade.REVIEW.rank
    assert r.features["grade_capped_by_evidence"] is True

    # 6. The rationale says callus is not reassurance, in words a clinician reads.
    rationale = " ".join(r.triage.rationale)
    assert "NOT REASSURANCE" in rationale
    assert "ulcer frequently lies underneath callus" in rationale

    # And the operative question — is the skin actually broken under it? — fires.
    asks = " ".join(q["ask"] for q in r.features["clarifying_questions"])
    assert "skin actually broken" in asks


# === THE ORIGINAL HEALTHY-FOOT FALSE POSITIVE ================================
#
# One consolidated, permanent guard on the exact failure that started this
# work: a visually healthy foot graded URGENT. Every assertion runs the real
# pipeline. If any of these flips, the platform has regressed to the state it
# shipped once already.

def test_the_original_healthy_foot_false_positive_stays_closed():
    # (a) A shadow whose character reads INDETERMINATE — the module's own
    #     statement that it cannot tell — must not reach urgent. This is the
    #     fail-open path that produced the original 0.68-confidence URGENT.
    shadow = _result(shadow=0.60, noise=14.0)
    assert shadow.features["dark_area_character"]["verdict"] == "indeterminate", (
        "fixture no longer reproduces the indeterminate reading")
    assert shadow.features["breakdown_pct"] == 0.0
    assert shadow.triage.grade is not Grade.URGENT

    # (b) Dry keratin (callus) cannot INDEPENDENTLY produce urgent — the
    #     0.85-confidence path. It reads callus_like and caps.
    callus = _result(callus=120)
    assert callus.features["yellow_area_character"]["verdict"] == "callus_like"
    assert callus.triage.grade is not Grade.URGENT

    # (c) Isolated colour variation — a scatter of specks summing past the
    #     area threshold — cannot escalate to urgent.
    scatter = _result(scatter=40)
    assert scatter.features["breakdown_pct"] >= 1.5
    assert scatter.triage.grade is not Grade.URGENT

    # (d) The plain healthy foot stays NO_FLAG, and says "no significant visual
    #     abnormality" rather than "healthy".
    healthy = _result()
    assert healthy.triage.grade is Grade.NO_FLAG
    assert healthy.features["evidence"]["appearance"] == evidence.NORMAL

    # (e) The fix did not silence real disease: a genuine ulcer on the same
    #     pipeline still reaches urgent. A regression guard that only checks the
    #     negative side can be satisfied by breaking everything.
    ulcer = _result(slough=110)
    assert ulcer.triage.grade is Grade.URGENT
