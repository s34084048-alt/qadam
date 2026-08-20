"""The pre-analysis input gate.

The live failure: a stock image carrying a clinic watermark -- a domain, a
phone number and a line of Persian text -- was processed end to end and
produced a full URGENT report at 0.78 confidence.

The tests here fall into two halves, and the second half is the important one.
Rejecting watermarks is easy to do too eagerly, and a gate that turns away a
glistening ulcer has done more damage than the failure it was built to fix.
So every rejection test is paired with a test that something which must NOT be
rejected still gets through.

Fixtures are drawings (see tests/fixture_images.py), and so are the thresholds
fitted to them. What these tests pin is the ordering and the direction.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis import input_gate
from app.analysis.input_gate import RejectionReason
from app.analysis.pipeline import AnalysisJob, execute
from app.config import settings
from tests import fixture_images as fx
from tests.conftest import API, make_case, make_patient


def _run(name: str):
    return execute(AnalysisJob(image_bytes=fx.jpeg_bytes(name), module="foot"))


def _encode(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY),
                                         fx.JPEG_QUALITY])
    assert ok
    return buf.tobytes()


# --- the failure this gate exists for ----------------------------------------

def test_a_watermarked_image_is_rejected_not_graded():
    """THE REGRESSION TEST. Fails against the code before the gate, which
    returned grade=urgent, urgency='Same day', confidence=0.78 for this exact
    fixture."""
    out = _run("watermarked_foot")

    assert out.input_rejection is not None, (
        "a clinic watermark was analysed instead of refused")
    assert out.input_rejection.reason == RejectionReason.OVERLAY

    # A rejection is not a quiet grade. Nothing downstream may exist.
    assert out.result is None
    assert out.overlay_png is None
    assert out.quality_rejected is False, (
        "an overlay is not a re-capture problem; a stock photograph does not "
        "become a capture by being photographed again")


def test_a_rejection_carries_a_reason_a_detail_and_an_instruction():
    rejection = _run("watermarked_foot").input_rejection
    assert rejection is not None
    body = rejection.to_json()

    assert body["rejected"] is True
    assert body["reason"] == "overlay"
    assert body["detail"] and body["hint"]
    # The evidence has to name what was actually found, or the reason is an
    # assertion rather than a finding.
    assert body["evidence"]["text_lines"], "rejected with no measurement behind it"
    assert body["evidence"]["text_lines"][0]["glyphs"] >= 4


def test_a_photograph_of_a_screen_is_rejected():
    out = _run("screen_photo")
    assert out.input_rejection is not None, (
        "a re-photographed display was analysed instead of refused")
    assert out.input_rejection.reason == RejectionReason.REPHOTOGRAPH
    assert out.result is None
    assert out.input_rejection.evidence["lattice_peak_z"] >= \
        settings.gate_lattice_peak_z


def test_a_frame_with_too_little_subject_is_rejected():
    out = _run("distant_foot")
    assert out.input_rejection is not None
    assert out.input_rejection.reason == RejectionReason.SUBJECT_ABSENT
    assert out.result is None


# --- the half that matters: what must still get through ----------------------

def test_a_clean_foot_passes_the_gate():
    out = _run("clean_foot")
    assert out.input_rejection is None
    assert out.result is not None
    assert str(out.result.triage.grade) == "no_flag"


def test_a_glistening_ulcer_is_not_mistaken_for_a_watermark():
    """THE FALSE POSITIVE THE GATE IS MOST LIKELY TO PRODUCE.

    Wet tissue throws specular highlights -- small, bright, high-contrast
    blobs, at the size range display text occupies. The fixture carries
    fourteen of them over an open wound bed. Rejecting this frame would be a
    worse failure than the watermark, because a wound that glistens is a wound
    that needs seeing, and the person who took the photograph would be told to
    take it again.
    """
    out = _run("wet_ulcer")

    assert out.input_rejection is None, (
        "a wet wound was refused as an overlay: "
        f"{out.input_rejection.detail if out.input_rejection else ''}")
    assert out.result is not None
    assert str(out.result.triage.grade) == "urgent", (
        "the ulcer survived the gate but lost its grade on the way")


@pytest.mark.parametrize("uniform_sizes", [True, False])
def test_specular_highlights_in_a_row_are_not_read_as_text(uniform_sizes):
    """The harder version: glints placed ON a shared baseline, evenly spaced.

    Baseline alignment alone therefore cannot be what the gate decides on, and
    this test is what stops a future change from making it so. Both variants
    are drawn here rather than committed, because they exist to constrain the
    detector rather than to describe a capture anyone would make.
    """
    rng = np.random.default_rng(4242)
    img, mask = fx._foot_base(91)
    cv2.ellipse(img, (400, 400), (170, 120), 0, 0, 360, (95, 115, 190), -1)
    cv2.ellipse(img, (400, 404), (130, 84), 0, 0, 360, (105, 150, 205), -1)
    fx._texture(img, mask, 94, amount=4.0)

    glare = np.zeros((fx.H, fx.W), np.float32)
    x = 290
    for _ in range(12):
        r = 9 if uniform_sizes else int(rng.uniform(4, 14))
        cv2.ellipse(glare, (x, 400), (r, int(r * 1.3)), 0, 0, 360, 255.0, -1)
        x += r * 2 + (6 if uniform_sizes else int(rng.uniform(4, 14)))
    glare = cv2.GaussianBlur(glare, (0, 0), 1.4)
    g = np.clip(glare / 255.0, 0, 1)[:, :, None]
    img = np.clip(img.astype(np.float32) * (1 - g) + 248.0 * g,
                  0, 255).astype(np.uint8)
    img = fx._sensor_noise(img, 91)

    assert input_gate.detect_overlay(img) is None, (
        "a row of specular highlights was read as a line of text")


def test_the_existing_samples_all_still_reach_the_gate_intact():
    """Nothing the pipeline already grades may be turned away by the gate."""
    from app import sample_data

    for sample in sample_data.SAMPLES:
        out = execute(AnalysisJob(
            image_bytes=sample_data.png_bytes(sample.name),
            module=sample.module))
        assert out.input_rejection is None, (
            f"{sample.name} was refused by the input gate: "
            f"{out.input_rejection.reason}")


def test_an_underexposed_frame_is_sent_back_for_light_not_for_distance():
    """Ordering, asserted rather than assumed.

    A dark frame measures 0.000 subject presence -- there is not enough light
    to separate anything from anything. If the presence check ran first it
    would say "move closer", and the user would re-take the same dark
    photograph from closer up.
    """
    from app import sample_data

    dark = sample_data.png_bytes("quality_dark")
    presence, _how = input_gate.measure_subject_presence(
        cv2.imdecode(np.frombuffer(dark, np.uint8), cv2.IMREAD_COLOR))
    assert presence < settings.gate_min_subject_presence, (
        "this test is only meaningful while a dark frame does read as empty")

    out = execute(AnalysisJob(image_bytes=dark, module="foot"))
    assert out.input_rejection is None
    assert out.quality_rejected is True
    assert "exposure" in [c.name for c in out.quality.failures]


# --- what the old check could not see ----------------------------------------

def test_presence_does_not_report_a_full_frame_when_it_found_nothing():
    """`estimate_subject_mask` returns 1.0 both for a true close-up and for a
    frame it failed on, which is why the old 0.08 check let a distant foot
    through. The gate's own measure has to tell those apart."""
    from app.analysis import cv_utils

    img = cv2.imdecode(np.frombuffer(fx.jpeg_bytes("distant_foot"), np.uint8),
                       cv2.IMREAD_COLOR)

    _mask, old = cv_utils.estimate_subject_mask(img)
    assert old == pytest.approx(1.0), (
        "this test documents the old behaviour; if it changed, re-derive the "
        "threshold in config.gate_min_subject_presence")

    presence, how = input_gate.measure_subject_presence(img)
    assert how == "uniform-frame"
    assert presence == 0.0


def test_a_true_closeup_still_counts_as_full_presence():
    """The other side of the same branch. A frame that IS all skin must not be
    mistaken for a frame with nothing in it."""
    img = np.full((fx.H, fx.W, 3), fx.SKIN, dtype=np.uint8)
    fx._texture(img, np.full((fx.H, fx.W), 255, np.uint8), 3, amount=5.0)
    img = fx._sensor_noise(img, 3)

    presence, how = input_gate.measure_subject_presence(img)
    assert how == "uniform-frame"
    assert presence == 1.0


# --- the API contract --------------------------------------------------------

async def test_the_api_refuses_a_watermarked_upload_and_stores_nothing(
    client, auth, ref_factory
):
    ref = ref_factory("wm")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("watermarked_foot.jpg",
                        fx.jpeg_bytes("watermarked_foot"), "image/jpeg")},
    )
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "input_rejected"
    assert error["details"]["input_gate"]["reason"] == "overlay"
    assert error["hint"]

    # Not analysed, not stored, and no analysis attached to the case.
    case = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert case["status"] == "quality_failed"
    assert case["latest_analysis"] is None
    assert case["history"] == []


@pytest.mark.parametrize("fixture,reason", [
    ("watermarked_foot", "overlay"),
    ("screen_photo", "rephotograph"),
    ("distant_foot", "subject_absent"),
])
async def test_every_rejection_reason_reaches_the_client(
    client, auth, ref_factory, fixture, reason
):
    ref = ref_factory("gate")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": (f"{fixture}.jpg", fx.jpeg_bytes(fixture), "image/jpeg")},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "input_rejected"
    assert body["details"]["input_gate"]["reason"] == reason
    # No grade anywhere in the refusal.
    assert "triage" not in resp.json()
    assert "grade" not in str(body["details"]["input_gate"]["evidence"])


async def test_a_clean_capture_still_gets_a_report_through_the_api(
    client, auth, ref_factory
):
    ref = ref_factory("ok")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("wet_ulcer.jpg", fx.jpeg_bytes("wet_ulcer"),
                        "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["triage"]["grade"] == "urgent"
