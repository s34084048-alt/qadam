"""No clinical instruction is issued from a region that does not read as skin.

WHAT THIS PINS
--------------
A photograph that was not a foot was analysed. The skin check fired correctly
and the page said, in its own words:

    "The photographed area does not read as skin ... If this is not a
     photograph of skin, every measurement below is meaningless."

Three cards above that sentence, the same page said:

    "Book a podiatry or diabetic foot clinic assessment within one week.
     Request perfusion assessment (pulses, ABPI or toe pressures) and
     neuropathy testing."

A timeframe, a destination and three named tests -- an instruction a user can
carry out -- chosen from the measurements the page had just called meaningless.

The existing refusal (test_subject_not_skin_refusal.py) covers the reassuring
direction only: a NO_FLAG from a non-skin region is refused outright. That
asymmetry is deliberate and stays. This is the other half: for the grades that
are correctly NOT suppressed, the GRADE is kept and the INSTRUCTION is
withheld. Nothing is lowered and nothing is hidden.

Synthetic images only; not a clinical claim.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.analysis.pipeline import AnalysisJob, execute
from app.sample_data import png_bytes
from app.summary import build_summary

W, H = 900, 700

# Phrases from routing.py that only ever appear in a real instruction.
INSTRUCTION_MARKERS = ("podiatry", "abpi", "monofilament", "book ", "request ")


def _not_skin_with_findings() -> bytes:
    """Something that is not skin, carrying regions large enough to grade.

    Cool blue-green throughout, so a* and b* sit outside the warm range skin
    occupies in every tone, with a dark patch and a yellow patch big enough to
    cross the measurement thresholds.
    """
    rng = np.random.default_rng(19)
    img = np.full((H, W, 3), (200, 130, 70), np.uint8)      # cool, non-skin
    cv2.rectangle(img, (120, 110), (470, 430), (120, 70, 35), -1)  # dark region
    cv2.ellipse(img, (620, 330), (150, 130), 0, 0, 360, (90, 190, 210), -1)
    img = cv2.GaussianBlur(img, (0, 0), 5)
    img = np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _non_skin_output():
    out = execute(AnalysisJob(image_bytes=_not_skin_with_findings(),
                              module="foot", render_overlay=False))
    assert out.result is not None, (
        "this fixture must be GRADED, not refused — the refusal path is "
        "covered by test_subject_not_skin_refusal.py")
    assert out.result.features.get("subject_check") is not None, (
        "fixture no longer trips the skin check; it cannot pin this rule")
    return out


def _non_skin_result():
    return _non_skin_output().result


def test_a_non_skin_region_issues_no_next_investigation():
    """The core rule. FAILS against the unfixed code, which emitted the full
    podiatry referral here."""
    triage = _non_skin_result().triage

    lowered = triage.next_investigation.lower()
    for marker in INSTRUCTION_MARKERS:
        assert marker not in lowered, (
            f"a clinical instruction ({marker!r}) was issued from a region "
            f"that does not read as skin: {triage.next_investigation!r}")
    assert "NO NEXT INVESTIGATION IS ISSUED" in triage.next_investigation


def test_the_timeframe_and_destination_go_with_it():
    """A timeframe and a routing target ARE the instruction. Leaving them
    behind would read as a referral with its reason missing."""
    triage = _non_skin_result().triage
    assert triage.urgency == ""
    assert triage.routing_target == ""


def test_the_grade_is_kept_not_lowered():
    """Withholding the instruction must not become a quiet downgrade. The
    finding is still surfaced -- that is the whole reason review/urgent is not
    refused in the first place."""
    result = _non_skin_result()
    assert str(result.triage.grade) != "no_flag", (
        "the grade was lowered to the reassuring one — the opposite of the "
        "intent")
    assert result.triage.rationale, "the basis for the grade was dropped"


def test_the_reason_is_stated_and_actionable():
    """A withheld instruction that does not say why, or what to do instead, is
    just a missing field."""
    triage = _non_skin_result().triage
    assert "does not read as skin" in triage.next_investigation
    assert "Re-capture" in triage.next_investigation


def test_the_clinician_summary_omits_the_withheld_labels():
    """The text summary is forwarded on its own. A bare "Timeframe:" with
    nothing after it reads as a value that failed to load."""
    out = _non_skin_output()
    text = build_summary(
        result=out.result, quality=out.quality, module="foot",
        patient_ref="TEST-1", captured_at="2026-01-01T00:00:00",
        body_site=None,
    )
    assert "Timeframe:" not in text
    assert "Route to:" not in text
    assert "NO NEXT INVESTIGATION IS ISSUED" in text


def test_a_real_foot_keeps_its_instruction():
    """The withholding is narrow. Every fixture that reads as skin must keep
    its timeframe, its destination and its recommended investigation."""
    for sample in ("foot_urgent", "foot_clean", "foot_dark_area"):
        out = execute(AnalysisJob(image_bytes=png_bytes(sample), module="foot",
                                  render_overlay=False))
        assert out.result is not None, f"{sample} was refused"
        triage = out.result.triage
        assert out.result.features.get("subject_check") is None, (
            f"{sample} unexpectedly tripped the skin check")
        assert triage.urgency, f"{sample} lost its timeframe"
        assert triage.routing_target, f"{sample} lost its routing target"
        assert "NO NEXT INVESTIGATION IS ISSUED" not in triage.next_investigation
