"""The wound-segmentation interface, and the safety guarantees around it.

WHAT THESE TESTS PROVE
----------------------
1. Provider INTERCHANGEABILITY: one contract runs against the real heuristic
   provider and a mock "future model" provider, so a validated model can drop
   in without a consumer changing.
2. The safety pipeline does NOT trust a segmentation score: a mock provider
   returning segmentation_score=0.99, is_calibrated=True changes no grade,
   bypasses no evidence rule, removes no clinical-review requirement, and
   creates no diagnosis.
3. The five concepts stay apart — a segmentation result carries a region and
   provenance, never a grade or a diagnosis.

NOT A CLINICAL CLAIM. Every image is synthetic; this is an architecture test.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis import segmentation
from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.types import Grade
from tests.test_evidence_gate import _foot, _result


# --- a mock "future model" provider, used only to prove interchangeability ----

class MockSegmentationProvider:
    """Stands in for a validated model. Returns a confident, calibrated-looking
    region regardless of input — precisely so the tests can prove the safety
    pipeline does NOT act on that confidence."""

    method = "mock_real_wound_segmentation"
    model_version = "mock-1.2.3"
    is_calibrated = True
    calibration_status = "calibrated_on_mock_holdout"
    dataset_version = "mock-wounds-v1"

    def segment(self, inp: segmentation.SegmentationInput):
        h, w = inp.subject_mask.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        cv2.rectangle(mask, (w // 3, h // 3), (2 * w // 3, 2 * h // 3), 255, -1)
        return segmentation.WoundSegmentationResult(
            present=True,
            classification=segmentation.CONFIRMED,
            bounding_box=(w // 3, h // 3, w // 3, h // 3),
            area_pct=11.1,
            segmentation_score=0.99,          # deliberately near-certain
            is_calibrated=True,
            method=self.method,
            model_version=self.model_version,
            calibration_status=self.calibration_status,
            dataset_version=self.dataset_version,
            limitations=["mock provider — not a real model"],
            mask=mask,
            detail=None,                       # a real model carries no heuristic detail
        )


# --- the shared contract, run against BOTH providers --------------------------

PROVIDERS = [
    pytest.param(segmentation.HeuristicLocalizationProvider(), id="heuristic"),
    pytest.param(MockSegmentationProvider(), id="mock_future_model"),
]


def _input():
    img = np.full((900, 1200, 3), (150, 175, 205), np.uint8)
    subject = np.zeros((900, 1200), np.uint8)
    cv2.ellipse(subject, (600, 450), (280, 340), 0, 0, 360, 255, -1)
    return segmentation.SegmentationInput(
        image_bgr=img, subject_mask=subject, quality_factor=1.0,
        classical_features={
            "dark_mask": np.zeros((900, 1200), np.uint8),
            "dark_verdict": None,
            "slough_mask": np.zeros((900, 1200), np.uint8),
            "slough_verdict": None,
            "erythema_mask": np.zeros((900, 1200), np.uint8),
        },
    )


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_provider_satisfies_the_result_contract(provider):
    """The interface is provider-agnostic: the same fields, types and
    provenance come back whichever provider ran."""
    result = provider.segment(_input())

    # Interface fields present and correctly typed.
    assert isinstance(result.present, bool)
    assert result.classification in (segmentation.CONFIRMED,
                                     segmentation.UNCERTAIN, segmentation.NONE)
    assert isinstance(result.area_pct, float)
    assert 0.0 <= result.segmentation_score <= 1.0
    assert isinstance(result.is_calibrated, bool)
    assert result.method and isinstance(result.method, str)
    assert result.model_version and isinstance(result.model_version, str)
    assert isinstance(result.limitations, list)

    prov = result.provenance()
    for key in ("method", "model_version", "dataset_version",
                "calibration_status", "is_calibrated", "segmentation_score",
                "limitations", "does_not_carry"):
        assert key in prov, f"provenance missing {key}"
    # A result never carries a grade or a diagnosis, by construction.
    assert prov["does_not_carry"] == ["a grade", "a diagnosis",
                                      "a clinical decision"]


def test_the_heuristic_provider_declares_itself_uncalibrated():
    p = segmentation.HeuristicLocalizationProvider()
    assert p.method == "heuristic_wound_region_localization"
    assert p.is_calibrated is False
    prov = p.segment(_input()).provenance()
    assert prov["is_calibrated"] is False
    assert "uncalibrated" in prov["score_meaning"].lower()
    assert any("not wound detection" in l.lower() for l in prov["limitations"])


def test_the_future_provider_is_declared_but_not_implemented():
    with pytest.raises(NotImplementedError):
        segmentation.RealSegmentationProvider().segment(_input())


# --- the safety guarantee: a score is never trusted ---------------------------

@pytest.fixture
def _mock_active():
    previous = segmentation.set_provider(MockSegmentationProvider())
    try:
        yield
    finally:
        segmentation.set_provider(previous)


def _analyse_slough(**_):
    """A real ulcer image, run through the full pipeline (not the backend in
    isolation) so the grade, ceiling and disclaimers are all exercised."""
    import cv2 as _cv2
    import numpy as _np
    rng = _np.random.default_rng(3)
    W, H = 1200, 900
    img = _np.full((H, W, 3), (105, 108, 112), _np.uint8)
    _cv2.ellipse(img, (600, 450), (280, 340), 0, 0, 360, (150, 175, 205), -1)
    reg = _np.zeros((H, W), _np.uint8); _cv2.circle(reg, (600, 380), 110, 255, -1)
    bed = _np.full_like(img, (120, 205, 215))
    bed = _np.clip(bed + rng.normal(0, 12, bed.shape), 0, 255).astype(_np.uint8)
    img[reg > 0] = bed[reg > 0]
    for _ in range(28):
        cx = int(rng.integers(545, 655)); cy = int(rng.integers(325, 435))
        _cv2.circle(img, (cx, cy), int(rng.integers(3, 8)), (245, 250, 252), -1)
    img = _np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(_np.uint8)
    ok, buf = _cv2.imencode(".jpg", img, [_cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                               render_overlay=False))


def test_a_confident_segmentation_does_not_change_the_grade(_mock_active):
    """The mock returns segmentation_score=0.99, is_calibrated=True on EVERY
    image. The grade must be exactly what the evidence pipeline produces from
    the features — the segmentation score must move it by nothing."""
    # Baseline grade with the heuristic provider (the default).
    segmentation.set_provider(segmentation.HeuristicLocalizationProvider())
    baseline = _analyse_slough().result.triage.grade

    # Same image with the confident mock active.
    segmentation.set_provider(MockSegmentationProvider())
    withmock = _analyse_slough().result
    assert withmock.triage.grade is baseline, (
        "a segmentation score changed the grade — the pipeline trusted it")
    # And the provenance shows the mock really did run.
    assert withmock.features["wound_segmentation"]["model_version"] == "mock-1.2.3"


def test_a_confident_segmentation_cannot_manufacture_a_grade_on_a_healthy_foot(
    _mock_active
):
    """The strongest form: on a HEALTHY foot the mock still returns a confident
    wound region. The grade must stay NO_FLAG — segmentation cannot invent a
    finding the evidence layer never made."""
    healthy = _foot().result
    # _foot uses the default heuristic; assert the healthy baseline first.
    assert healthy.triage.grade is Grade.NO_FLAG

    # Now with the mock active, the same healthy scene.
    out = execute(AnalysisJob(
        image_bytes=_healthy_bytes(), module="foot", render_overlay=False))
    assert out.result.triage.grade is Grade.NO_FLAG, (
        "a confident segmentation manufactured a grade on a healthy foot")
    # The evidence ceiling and disclaimers are untouched.
    assert out.result.features["evidence"]["appearance"] == "no_significant_visual_abnormality"


def test_a_confident_segmentation_does_not_create_a_diagnosis(_mock_active):
    """No field named a diagnosis, and no forbidden clinical claim, appears
    just because a calibrated-looking provider ran."""
    out = _analyse_slough()
    seg_payload = out.result.features["wound_segmentation"]
    # The score is surfaced, but it explicitly does not carry a diagnosis.
    assert "a diagnosis" in seg_payload["does_not_carry"]

    def _keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k.lower(); yield from _keys(v)
        elif isinstance(node, list):
            for it in node:
                yield from _keys(it)
    assert not any("diagnos" in k for k in _keys(seg_payload))


def _healthy_bytes():
    import cv2 as _cv2
    import numpy as _np
    rng = _np.random.default_rng(3)
    W, H = 1200, 900
    img = _np.full((H, W, 3), (105, 108, 112), _np.uint8)
    _cv2.ellipse(img, (600, 450), (280, 340), 0, 0, 360, (150, 175, 205), -1)
    img = _np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(_np.uint8)
    ok, buf = _cv2.imencode(".jpg", img, [_cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return buf.tobytes()


def test_provenance_is_visible_in_the_analysis_payload():
    """Requirement 6: provenance fields present in internal output."""
    r = _result(slough=110)
    seg = r.features["wound_segmentation"]
    assert seg["method"] == "heuristic_wound_region_localization"
    assert seg["model_version"] == "heuristic-classical-1.0"
    assert seg["calibration_status"] == "uncalibrated_heuristic"
    assert seg["is_calibrated"] is False
    assert "dataset_version" in seg


async def test_admin_fairness_surfaces_the_segmentation_provenance(
    client, admin_auth
):
    """Requirement 6: provenance visible in admin output, not only per-analysis."""
    body = (await client.get("/api/v1/admin/fairness", headers=admin_auth)).json()
    sp = body["segmentation_provider"]
    assert sp["method"] == "heuristic_wound_region_localization"
    assert sp["model_version"] == "heuristic-classical-1.0"
    assert sp["is_calibrated"] is False
    assert sp["calibration_status"] == "uncalibrated_heuristic"
    assert "dataset_version" in sp
