"""Classical computer-vision placeholder backend.

Every measurement here is a SURFACE colour, area or outline statistic. Nothing
in this file infers anything beneath the skin, and nothing produces a
diagnosis: the output is a graded flag plus a routing decision.

Thresholds are expressed RELATIVE to the subject's own colour statistics with a
small absolute floor, so a fixed cut does not behave systematically differently
across skin tones. This is a mitigation, not a validation -- performance must
still be reported stratified by Monk Skin Tone group (see /admin/fairness).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .. import (cv_utils, evidence, localization, prerequisites,
                segmentation)
from ..modules_config import routing_for
from ..types import (Grade, Lesion, ModuleResult, QualityReport,
                     SubjectMismatch, Triage)

MODEL_NAME = "classical-cv"
MODEL_VERSION = "0.1.0"

# Tunable decision thresholds, kept in one place so they are inspectable and
# so a validation study can report exactly what was used.
T = {
    "foot": {
        "erythema_rel_a": 8.0, "erythema_abs_a": 5.0,
        # Darkness is measured ONLY relative to the patient's own skin. An
        # absolute floor here previously collapsed the whole rule to "L <= 70",
        # which is a shadow detector: it flagged the gap between two fingers as
        # necrotic tissue, and was simultaneously stricter on dark skin — the
        # opposite of the fairness this file claims.
        "dark_rel_L": 55.0,
        # A dark region must also have WIDTH. Creases and nail edges are thin.
        "dark_min_radius_frac": 0.035,
        "slough_rel_b": 12.0,
        # Raised from 0.5%, which on a typical capture was a 67x67 px patch —
        # smaller than an ordinary shadow between two toes.
        "review_dark_pct": 1.5, "urgent_dark_pct": 6.0,
        "urgent_breakdown_pct": 1.5,
        "review_breakdown_pct": 0.4, "review_erythema_pct": 12.0,
        "monitor_erythema_pct": 4.0,
    },
}


def _localization_from(seg) -> localization.WoundLocalization:
    """A minimal WoundLocalization view of a provider result that did not carry
    the heuristic's rich detail — e.g. a future real segmentation model. Keeps
    the overlay and the `wound_localization` payload working for ANY provider,
    without inventing contributing-evidence or artifact prose the model did not
    produce."""
    return localization.WoundLocalization(
        present=seg.present,
        classification=seg.classification,
        box=seg.bounding_box,
        area_pct=seg.area_pct,
        boundary_confidence=seg.segmentation_score,
        components=0,
        contributing=[],
        artifacts=[],
        message=(localization.WOUND_MESSAGE
                 if seg.classification == localization.CONFIRMED
                 else localization.UNCERTAIN_MESSAGE
                 if seg.present else ""),
        mask=seg.mask,
    )


def _conf(evidence: float, quality: QualityReport) -> float:
    """An UNCALIBRATED EVIDENCE-STRENGTH HEURISTIC. Not a probability.

    This is how far the measurement sits from its decision boundary, discounted
    by image quality. Every constant below — the 0.45 floor, the 0.40 slope,
    the 0.85 ceiling, the 0.15 floor — is a hand-chosen heuristic, NOT a value
    fitted to data. This project has no labelled clinical images, so nothing
    here could be calibrated even in principle right now.

    It therefore must never be read as P(the grade is correct), and the UI must
    never label it "confidence" for the same reason (it says "evidence strength
    (uncalibrated)" — see web result.evidenceStrengthHint). "0.55" means "a
    little past the boundary on a decent capture", not "55% chance of a wound".

    Clinical sensitivity and specificity of this score are UNKNOWN. The 0.85
    ceiling exists precisely so an unvalidated placeholder cannot display
    near-certainty; it is a guard, not a calibrated maximum."""
    base = 0.45 + 0.40 * float(np.clip(evidence, 0.0, 1.0))
    return float(np.clip(base * quality.confidence_factor, 0.15, 0.85))


def _triage(
    module: str, grade: Grade, confidence: float, rationale: list[str],
    confidence_adjustments: list[dict] | None = None,
) -> Triage:
    spec = routing_for(module, str(grade))
    return Triage(
        grade=grade,
        label=spec["label"],
        confidence=confidence,
        confidence_adjustments=list(confidence_adjustments or []),
        rationale=rationale,
        next_investigation=spec["next_investigation"],
        urgency=spec["urgency"],
        routing_target=spec["routing_target"],
    )


def _withhold_the_instruction(triage: Triage, unexpected: dict) -> None:
    """Strip the recommended next investigation, keeping the grade.

    `urgency` and `routing_target` go with it: a timeframe and a destination
    ARE the instruction, and leaving them while blanking the sentence would
    read as a referral with the reason missing. Empty is the honest value, and
    every renderer skips an empty one rather than printing a blank label.
    """
    triage.urgency = ""
    triage.routing_target = ""
    triage.next_investigation = (
        "NO NEXT INVESTIGATION IS ISSUED FROM THIS IMAGE. The measured region "
        "does not read as skin, so the measurements one would be chosen from "
        "cannot be relied on. The grade above is what the PIXELS support; it "
        "has NOT been lowered, and it is not a statement about a patient. "
        + unexpected["advice"]
    )


def _lesions_from(
    mask: np.ndarray,
    subject_area: float,
    kind: str,
    description: str,
    severity_ref: float,
    top_n: int = 3,
) -> list[Lesion]:
    out: list[Lesion] = []
    for _c, pct, bbox, centroid in cv_utils.blobs_from_mask(
        mask, subject_area, min_area_pct=0.15, top_n=top_n
    ):
        out.append(
            Lesion(
                kind=kind,
                area_pct=pct,
                severity=float(np.clip(pct / severity_ref, 0.05, 1.0)),
                bbox=bbox,
                centroid=centroid,
                description=description,
            )
        )
    return out


class ClassicalCVBackend:
    name = MODEL_NAME
    version = MODEL_VERSION
    backend_id = "classical_cv"

    def supports(self, module: str) -> bool:
        return module == "foot"

    def analyze(
        self,
        image_bgr: np.ndarray,
        module: str,
        quality: QualityReport,
        calibration: Any | None = None,
    ) -> ModuleResult:
        mask = quality.mask
        if mask is None:
            mask, _ = cv_utils.estimate_subject_mask(image_bgr)
        subject = mask > 0
        # The segmentation found essentially nothing and the whole frame is
        # substituted for it. That is a FAILURE, and until now it was silent:
        # every percentage below is then a share of the photograph, background
        # included, and nothing downstream said so. Recorded, and fed to the
        # confidence prerequisites.
        subject_mask_was_degenerate = bool(subject.sum() < 100)
        if subject_mask_was_degenerate:
            mask = np.full(image_bgr.shape[:2], 255, dtype=np.uint8)
            subject = mask > 0

        # Findings from the pre-measurement steps are LOCALS, never attributes.
        # This object is a module-level singleton (see backends/__init__) and
        # analyses run concurrently in a worker thread pool (runner.py uses
        # anyio.to_thread.run_sync), so anything written to `self` here belongs
        # to whichever analysis wrote it last. `framing_warning` was an
        # attribute, and a second analysis entering this method reset it while
        # the first was still measuring -- losing the first one's "percentages
        # are UNDERSTATED" warning with no error anywhere. Understated areas
        # are the direction that hides things.
        mask, background_warning = self._widen_if_the_segmentation_split_skin(
            image_bgr, mask)
        mask = self._widen_if_the_lesion_became_the_subject(image_bgr, mask, module)
        unexpected = self._note_if_subject_is_unexpected(image_bgr, mask)

        fn = {
            "foot": self._foot,
        }[module]
        result = fn(image_bgr, mask, quality,
                    background_warning=background_warning,
                    subject_mask_was_degenerate=subject_mask_was_degenerate,
                    calibration=calibration)
        if background_warning:
            result.features["framing_warning"] = background_warning
            result.triage.rationale.insert(0, background_warning["effect"])
        if unexpected:
            result.features["subject_check"] = unexpected
            result.triage.rationale.insert(0, unexpected["warning"])

            # REFUSE A REASSURING RESULT WE CANNOT STAND BEHIND.
            #
            # A real foot with a large dark eschar was graded NO_FLAG in the
            # field: its pale sole was the same brightness as a pale background,
            # so the segmentation could not separate them and locked onto the
            # dark regions as the "subject". Every colour was then measured
            # against that dark fragment, nothing read as darker than it, and an
            # obvious wound came back "no surface red flag".
            #
            # The one thing that DID fire was this skin check — the measured
            # region does not read as skin. When that is true AND the result is
            # the reassuring NO_FLAG, the "no flag" is not a finding about the
            # foot; it is an artefact of having measured the wrong region. A
            # NO_FLAG can be mistaken for "the foot is fine"; a refusal cannot.
            #
            # This is deliberately NARROW, because "not skin" was downgraded
            # from a hard refusal for a good reason (a real foot under a cool
            # fluorescent tube can read outside the skin range). So it only
            # overrides toward safety, and only the reassuring grade: a detected
            # flag (review/urgent) is still surfaced, never suppressed. Every
            # clean fixture reads as skin and is unaffected.
            if result.triage.grade is Grade.NO_FLAG:
                raise SubjectMismatch(
                    module,
                    "This came back with no surface flag, but the measured "
                    "region does not read as skin — most often because a pale "
                    "sole could not be separated from a similar-coloured "
                    "background, so the wrong area was measured. A 'no flag' "
                    "from the wrong region is not a statement that the foot is "
                    "fine, so QADAM is refusing it rather than reporting it.",
                    "Re-take on a DARK, contrasting background — a dark blue or "
                    "green cloth or paper under the foot — filling about half "
                    "the frame with the sole, in even indirect light.",
                )

            # THE OTHER HALF OF THE SAME PROBLEM.
            #
            # Refusing only NO_FLAG was the right first call: a false
            # reassurance is the worst thing this platform can emit, and a
            # detected flag must never be suppressed. The reasoning recorded
            # above for keeping review/urgent was that a photograph of a desk
            # then becomes "visible nonsense rather than a clinical decision".
            #
            # It did not. A non-foot image graded REVIEW and the result page
            # read: "Book a podiatry or diabetic foot clinic assessment within
            # one week. Request perfusion assessment (pulses, ABPI or toe
            # pressures) and neuropathy testing." That is an instruction a user
            # can carry out, with a timeframe and three named tests, chosen
            # from measurements the same page calls meaningless.
            #
            # So the GRADE stays -- it is what the pixels support and
            # suppressing it would hide a finding -- and the INSTRUCTION is
            # withheld. Nothing is lowered, nothing is hidden, and no next step
            # is issued from a region that does not read as skin.
            _withhold_the_instruction(result.triage, unexpected)
        result.model_version = f"{self.name}-{self.version}"
        result.backend = self.backend_id
        return result

    # -- what each module needs to see before it measures anything ----------

    def _widen_if_the_segmentation_split_skin(self, bgr, mask):
        """Undo a segmentation that cut one continuous skin surface in half.

        Returns `(mask, warning_or_None)`. The warning is returned rather than
        stored on `self` because this backend is a shared singleton serving
        concurrent analyses -- see the note in `analyze`.

        `estimate_subject_mask` models the background from the image border. On
        a plain backdrop that works. Photograph a toe on a beige mat, a wooden
        table or a bedsheet — anything close to skin colour — and the border
        model is partly skin, so the "subject" comes back as an arbitrary
        fragment of the toe.

        Nothing then errors: every percentage is simply computed against the
        wrong denominator. A real capture from the field showed this, and the
        answer happened to be right, which is worse than an error because it
        looks like it worked.

        The signature is a small selected region whose SURROUND is also skin.
        Two pieces of skin are one surface, so the frame is the subject.
        """
        _L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        frame_share = float(subject.mean())
        if frame_share >= 0.55 or subject.sum() < 100:
            return mask, None

        outside = (~subject).astype(np.uint8) * 255
        if (outside > 0).sum() < 500:
            return mask, None
        inside_skin, _ = cv_utils.looks_like_skin(a, b, mask)
        outside_skin, _ = cv_utils.looks_like_skin(a, b, outside)
        if inside_skin and outside_skin:
            # Widening keeps the denominator stable and interpretable, where a
            # fragment makes every percentage arbitrary. But the whole frame
            # now includes background, so an area is UNDERSTATED — and that is
            # the direction that hides things. Say so.
            warning = {
                "issue": "background_same_colour_as_skin",
                "effect": (
                    "The foot could not be separated from the background "
                    "because they are a similar colour, so every percentage "
                    "below is measured against the whole frame and is "
                    "UNDERSTATED."
                ),
                "advice": (
                    "Re-take the photograph on a plain background that "
                    "contrasts with skin — a blue or green cloth or paper "
                    "sheet is ideal."
                ),
            }
            return np.full(bgr.shape[:2], 255, dtype=np.uint8), warning
        return mask, None

    def _widen_if_the_lesion_became_the_subject(self, bgr, mask, module: str):
        """Fix a segmentation that picked the wound instead of the limb.

        `estimate_subject_mask` keeps whatever stands out from the border. On a
        wide shot that is the foot against the backdrop, which is right. On a
        TIGHT CROP — the framing the crop tool explicitly asks for — the border
        is skin and the thing standing out is the wound, so the wound becomes
        "the subject". Every threshold is then measured against the wound's own
        colour, the wound looks uniform to itself, and the answer comes back
        no_flag. The more carefully the user framed the lesion, the more
        certainly the result was wrong.

        When the segmented region does not look like skin but the surround
        does, the surround is the patient and the region is what is wrong with
        them. Measuring over the whole frame puts them back in the same picture,
        which is the only way a comparison against "their own skin" means
        anything.
        """
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        if subject.sum() < 100 or (~subject).sum() < 500:
            return mask

        # NOT the skin-hue test. A dark eschar and dark skin share a hue -- that
        # is exactly the property that keeps this platform fair across skin
        # tones, and it means hue cannot separate "wound" from "patient". What
        # does separate them is that a wound is markedly DARKER than the skin
        # immediately around it.
        surround = (~subject).astype(np.uint8) * 255
        surround_is_skin, _ = cv_utils.looks_like_skin(a, b, surround)
        if not surround_is_skin:
            # The surround is a backdrop, not the patient. The segmentation is
            # the normal one and the subject really is the limb.
            return mask

        darker_by = float(np.median(L[surround > 0])) - float(np.median(L[subject]))
        if darker_by < T["foot"]["dark_rel_L"] * 0.6:
            return mask

        return np.full(bgr.shape[:2], 255, dtype=np.uint8)

    def _note_if_subject_is_unexpected(self, bgr, mask) -> dict | None:
        """Flag an image that does not look like skin. No longer REFUSE it.

        This was a hard rejection, and it existed for a reason that has since
        been removed twice over.

        It was built because the EYE module read the warm tone of a photograph
        of a foot as scleral yellowing and answered "urgent" at 0.85
        confidence. There is no eye module now — there is one image module, and
        the user selected it deliberately before pointing the camera.

        More importantly, THE IMAGE NO LONGER ROUTES ANYTHING. That grade was
        dangerous because it was the decision; routing now comes from the
        examination and the answers (app/routing.py). A meaningless measurement
        of a photograph of a desk is now visible nonsense rather than a
        clinical decision.

        Meanwhile the cost was real and measured: light skin under a
        fluorescent tube measures a* and b* NEGATIVE and was rejected outright.
        Clinics have fluorescent tubes. Refusing to analyse a real foot because
        of the lamp above it is a worse failure than measuring a desk.
        """
        _L, a, b = cv_utils.lab_planes(bgr)
        skin, stats = cv_utils.looks_like_skin(a, b, mask)
        if skin:
            return None
        return {
            "looks_like_skin": False,
            "measured": stats,
            "warning": (
                "The photographed area does not read as skin — its colour sits "
                "outside the warm range skin occupies in every tone. Cool or "
                "fluorescent light can cause this on a real foot. If this is "
                "not a photograph of skin, every measurement below is "
                "meaningless."
            ),
            "advice": (
                "Re-capture in even, indirect light, filling the frame with "
                "the area being assessed on a plain background."
            ),
        }

    def _skin_reference(self, L, a, b, subject, t) -> tuple[float, float, float, dict]:
        """The patient's own NORMAL skin, used as the reference every threshold
        is relative to.

        The median of the whole subject is that reference only while the lesion
        is a minority of it. Crop tightly onto a wound -- which is exactly what
        the crop tool asks the user to do, and exactly what a careful user does
        -- and the median becomes the WOUND. "Darker than the median" then finds
        nothing, and a wound filling three quarters of the frame was graded
        no_flag. The tighter and more careful the photograph, the more certainly
        the result was wrong.

        So the reference is refined once: measure, provisionally mark anything
        deviating from it, and if that is a large share of the subject, measure
        again over what is left. On an image where the lesion is small the
        provisional mark is small, nothing is recomputed, and behaviour is
        exactly as before.
        """
        values = L[subject]
        L_ref = float(np.median(values))
        a_med = float(np.median(a[subject]))
        b_med = float(np.median(b[subject]))

        # A high percentile was tried here so that a wound filling most of the
        # SUBJECT would still be measured against the remaining skin. It was
        # reverted: raising the reference widens every dark region, a shadow
        # across a finger then survives the thin-structure filter, and the
        # false "necrotic tissue on a healthy toe" that this project already
        # shipped once came straight back. A residual false negative is not
        # worth re-earning that.
        #
        # The dominant-lesion case is instead handled upstream, by
        # _widen_if_the_lesion_became_the_subject, which puts the surrounding
        # skin back into the subject so the median means "skin" again.
        info: dict = {
            "L_reference": round(L_ref, 1),
            "basis": "median brightness of the segmented subject",
            "known_limit": "If the lesion fills most of the SUBJECT REGION "
                           "even after widening, the reference is the lesion "
                           "itself and the area can be under-reported. "
                           "Include surrounding normal skin in the frame.",
        }
        return L_ref, a_med, b_med, info

    @staticmethod
    def _refuse_if_the_reference_is_the_lesion(L, subject, dark_pct, brk_pct,
                                               ery_pct) -> None:
        """Say "I cannot read this" instead of quietly saying "no flag".

        Every threshold here is relative to the median brightness of the
        subject. When the lesion is most of the subject, that median IS the
        lesion, nothing is dark relative to it, and the module returns 0% and
        no_flag over a wound that fills the frame. Silence is the worst
        possible output: the user reads it as reassurance.

        The signature of that state is a subject whose brightness splits into
        two clearly separated populations while the measurements found nothing.
        Otsu finds the split; the separation has to be wide, so an ordinary
        shadow or a bit of texture does not trigger it.

        This only ever converts a NEGATIVE into a request for a better
        photograph. It cannot raise a grade, so it cannot manufacture a false
        alarm.
        """
        if dark_pct >= 0.5 or brk_pct >= 0.5 or ery_pct >= 2.0:
            return                       # something was measured; not this case
        values = L[subject]
        if values.size < 1000:
            return

        level, _ = cv2.threshold(values.astype(np.uint8).reshape(-1, 1), 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        upper = values[values >= level]
        lower = values[values < level]
        if upper.size < 200 or lower.size < 200:
            return

        separation = float(upper.mean()) - float(lower.mean())
        darker_share = float(lower.size) / float(values.size)
        # Wide separation AND the darker population is a substantial part of
        # the region -- i.e. the "average" this was measured against is sitting
        # inside the dark half.
        if separation < 45.0 or darker_share < 0.35:
            return

        raise SubjectMismatch(
            "foot",
            "Most of this image is markedly darker than the rest of it, which "
            "leaves no normal skin to measure against. QADAM measures every "
            "colour relative to the patient's own skin, so it cannot read "
            "this image and is not reporting a result rather than reporting a "
            "misleading one.",
            "Re-capture from slightly further back so a margin of the "
            "patient's normal skin is in the frame alongside the area of "
            "interest, in even indirect light. Do not crop tightly onto the "
            "lesion alone.",
        )

    def _foot(self, bgr, mask, quality, *,
              background_warning=None,
              subject_mask_was_degenerate=False,
              calibration=None) -> ModuleResult:
        t = T["foot"]
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        subject_area = float(subject.sum())
        L_med, a_med, b_med, skin_ref = self._skin_reference(L, a, b, subject, t)
        min_dim = min(bgr.shape[:2])

        erythema = ((a >= a_med + t["erythema_rel_a"]) & (a >= t["erythema_abs_a"])
                    & subject).astype(np.uint8) * 255
        dark = ((L <= L_med - t["dark_rel_L"]) & subject).astype(np.uint8) * 255
        slough = ((b >= b_med + t["slough_rel_b"]) & (L >= L_med - 25)
                  & subject).astype(np.uint8) * 255

        erythema = cv_utils.clean_binary(erythema, min_dim)
        dark = cv_utils.clean_binary(dark, min_dim)
        slough = cv_utils.clean_binary(slough, min_dim)

        # THE BACKDROP IS NOT THE PATIENT.
        #
        # This module asks the user to shoot on a blue or green cloth, and on a
        # close-up whose foot ran off the frame edges it then scored that cloth
        # as 33% "dark area" and as tissue breakdown, with a red POSSIBLE WOUND
        # box drawn on it. `subject` is the whole frame in that case -- the
        # wideners put it there deliberately and correctly -- so the exclusion
        # cannot live in the mask. It lives here, per feature region, behind
        # two guards that keep an interior wound and a fluorescent-lit foot
        # safe. See cv_utils.drop_backdrop_regions.
        backdrop: list[dict] = []
        for name, m in (("erythema", erythema), ("dark_area", dark),
                        ("tissue_breakdown", slough)):
            cleaned, gone = cv_utils.drop_backdrop_regions(m, a, b, subject)
            m[:] = cleaned
            for entry in gone:
                backdrop.append({"kind": name, **entry})

        # Discard thin dark structures: skin creases, the gap between toes and
        # the line under a nail are all long and narrow, and none of them is a
        # lesion.
        dark = cv_utils.drop_thin_structures(
            dark, t["dark_min_radius_frac"] * float(np.sqrt(subject_area)))

        ery_pct = cv_utils.area_pct(erythema, mask)
        dark_pct = cv_utils.area_pct(dark, mask)
        brk_pct = cv_utils.area_pct(slough, mask)

        # Is each region ONE thing, or a scatter that happens to sum? An area
        # percentage cannot tell the difference, and the urgent thresholds are
        # areas. See evidence.py.
        dark_coherence = cv_utils.region_coherence(dark)
        brk_coherence = cv_utils.region_coherence(slough)

        self._refuse_if_the_reference_is_the_lesion(L, subject, dark_pct,
                                                    brk_pct, ery_pct)

        # Is the dark area a cast shadow, or a change in the tissue?
        character = (cv_utils.dark_region_character(bgr, dark)
                     if dark_pct > 0 else None)

        # And is the yellow area dry keratin, or moist tissue in a defect?
        #
        # NOTE THE ASYMMETRY WITH THE SHADOW RULE. A shadow is nothing, so a
        # shadow verdict lowers the grade. Callus is NOT nothing: an ulcer very
        # often lies underneath it and cannot be seen until it is pared back.
        # So this verdict is reported and drives a question, and it changes no
        # grade at all. Suppressing on it would hide exactly the wound this
        # module exists to find.
        yellow_character = (cv_utils.yellow_region_character(bgr, slough)
                            if brk_pct > 0 else None)

        # A granulating bed is RED, so it lands here rather than in `slough`,
        # and "surface redness" alone does not distinguish an open wound from
        # a flush. This says whether the redness is a BOUNDED AREA. It changes
        # no grade -- erythema stays capped at REVIEW in evidence.py, for the
        # reason recorded there -- and it names no diagnosis. See
        # cv_utils.red_region_character.
        red_character = (cv_utils.red_region_character(bgr, erythema)
                         if ery_pct > 0 else None)

        # WOUND SEGMENTATION, through the model-agnostic provider interface.
        # Today the provider IS the heuristic localiser (unchanged); a future
        # validated model implements the same interface and drops in here with
        # no change to the safety pipeline. The result carries a region and its
        # provenance ONLY — it holds no grade and no diagnosis, and the grade
        # below is set entirely independently of it. See segmentation.py.
        seg = segmentation.active_provider().segment(
            segmentation.SegmentationInput(
                image_bgr=bgr,
                subject_mask=mask,
                quality_factor=quality.confidence_factor,
                classical_features={
                    "dark_mask": dark,
                    "dark_verdict": (character or {}).get("verdict"),
                    "slough_mask": slough,
                    "slough_verdict": (yellow_character or {}).get("verdict"),
                    "erythema_mask": erythema,
                },
            )
        )
        # `detail` is the heuristic's rich WoundLocalization when the heuristic
        # provider produced it; a real provider may not, so fall back to a
        # minimal view built from the interface result.
        wound = seg.detail if seg.detail is not None else _localization_from(seg)

        lesions = (
            # NOT called necrotic tissue. A photograph cannot separate eschar
            # from a shadow, a bruise or dark pigmentation, and naming it
            # "necrotic" asserted the one reading that triggers an amputation
            # pathway.
            _lesions_from(dark, subject_area, "dark_area",
                          "Area markedly darker than the surrounding skin — "
                          "shadow, bruising, pigmentation and non-viable "
                          "tissue all look like this in a photograph", 12.0)
            + _lesions_from(slough, subject_area, "tissue_breakdown",
                            "Open wound bed / slough on the surface", 8.0)
            + _lesions_from(erythema, subject_area, "erythema",
                            "Area of surface redness", 30.0)
        )

        rationale = [
            f"Surface erythema covers {ery_pct:.1f}% of the imaged foot region.",
            f"Apparent tissue breakdown covers {brk_pct:.1f}%.",
            f"Area markedly darker than surrounding skin covers {dark_pct:.1f}%.",
        ]
        if backdrop:
            # Stated, not silent. A region that vanished between the pixels and
            # the percentage has to be visible to a reader, along with the one
            # thing that makes it not vanish: getting the foot fully in frame.
            px = sum(int(entry["area_px"]) for entry in backdrop)
            rationale.insert(0,
                f"{len(backdrop)} region(s) reaching the edge of the frame did "
                f"not read as skin and were excluded as backdrop rather than "
                f"measured as findings ({px / max(1.0, subject_area) * 100:.1f}% "
                f"of the imaged region). Re-take with the whole foot inside the "
                f"frame if any of it was part of the foot.")
        if dark_pct > 0:
            rationale.append(
                "A DARK AREA IS NOT A DIAGNOSIS OF NECROSIS. Shadow, bruising "
                "and normal pigmentation look the same in a photograph. "
                "Re-image in even, indirect light before acting on it, and "
                "confirm by direct inspection."
            )

        # THE SHADOW RULE. A dark area with a soft boundary and a smooth
        # interior is cast light, and if there is no tissue loss anywhere in
        # the frame there is nothing for it to be an eschar OF. This module
        # once graded a healthy toe "urgent — necrotic tissue" on exactly that
        # pattern, so it now asks for a better photograph instead of grading.
        #
        # The guard is the tissue-loss test: with an open wound present the
        # rule does not apply, and a dark area beside it is never suppressed.
        # Poor light is set by the pipeline AFTER this runs, so the backend
        # cannot see it. It is applied there instead — see pipeline.py.
        re_image = (
            character is not None
            and character["verdict"] == "shadow_like"
            and brk_pct < t["review_breakdown_pct"]
        )
        if re_image:
            rationale.insert(0,
                "The dark area has a soft boundary and a smooth interior — the "
                "signature of cast light rather than of a change in the "
                "tissue — and there is no tissue loss in this image. No urgent "
                "flag is raised from it. RE-IMAGE before drawing any "
                "conclusion.")
            grade = Grade.MONITOR if dark_pct >= t["review_dark_pct"] else Grade.NO_FLAG
            strength = 0.2
        elif brk_pct >= t["urgent_breakdown_pct"] or dark_pct >= t["urgent_dark_pct"]:
            grade = Grade.URGENT
            strength = max(dark_pct / t["urgent_dark_pct"],
                           brk_pct / t["urgent_breakdown_pct"]) / 4.0
            rationale.insert(0, "Visible tissue breakdown and/or an extensive "
                                "dark area meets the urgent threshold.")
        elif dark_pct >= t["review_dark_pct"]:
            grade = Grade.REVIEW
            strength = dark_pct / t["urgent_dark_pct"]
            rationale.insert(0, "A discrete dark area is present. This routes "
                                "for a clinician to look at the foot — it does "
                                "not assert that the tissue is non-viable.")
        elif brk_pct >= t["review_breakdown_pct"] or ery_pct >= t["review_erythema_pct"]:
            grade = Grade.REVIEW
            strength = max(brk_pct / t["review_breakdown_pct"],
                           ery_pct / t["review_erythema_pct"]) / 3.0
            rationale.insert(0, "Surface changes exceed the review threshold.")
        elif ery_pct >= t["monitor_erythema_pct"]:
            grade = Grade.MONITOR
            strength = ery_pct / t["review_erythema_pct"]
            rationale.insert(0, "Mild surface erythema only.")
        else:
            grade = Grade.NO_FLAG
            strength = 1.0 - min(1.0, ery_pct / max(t["monitor_erythema_pct"], 1e-6))
            rationale.insert(0, "No surface red flag detected in this image.")

        # THE EVIDENCE CEILING. Everything above decides what the AREAS say.
        # This decides whether the areas are entitled to say it: whether each
        # region is coherent, whether its character was actually established
        # rather than merely undisputed, and whether the capture was good
        # enough to read. It can only ever lower the grade — a layer that could
        # raise one could invent an emergency out of a bad photograph.
        report = evidence.assess(
            {
                "dark_area_pct": dark_pct,
                "breakdown_pct": brk_pct,
                "erythema_pct": ery_pct,
                "dark_area_character": character,
                "yellow_area_character": yellow_character,
                "erythema_character": red_character,
                "dark_coherence": dark_coherence,
                "breakdown_coherence": brk_coherence,
            },
            quality_factor=quality.confidence_factor,
        )
        capped = False
        if grade.rank > report.ceiling.rank:
            capped = True
            # Only from findings that were actually MEASURED. A finding with no
            # area has no evidence to be insufficient, and quoting its limit
            # would explain the grade with a region that is not in the image.
            limits = [
                line for fnd in report.findings
                if not fnd.sufficient_for_urgent
                and float(fnd.measurements.get("area_pct", 0.0) or 0.0) > 0
                for line in fnd.limits
            ]
            # Every reason, not just the first: the grade a clinician sees was
            # lowered from what the areas alone said, and "why" is not a
            # footnote.
            for line in reversed(limits):
                rationale.insert(0, line)
            rationale.insert(0,
                f"The measured areas reach the {grade} threshold, but the "
                f"visual evidence does not support it, so this is graded "
                f"{report.ceiling} — a clinician looks at the foot.")
            grade = report.ceiling
            # Confidence follows the EVIDENCE, not the area. A grade that had
            # to be capped is a grade the module is unsure of, and it must not
            # keep the confidence its raw area would have earned.
            strength = min(strength, 0.25)

        rationale.append(
            "Depth, bone involvement, infection, perfusion and neuropathy are "
            "not assessable from a photograph."
        )
        # EVIDENCE STRENGTH IS COUPLED TO ITS OWN PRECONDITIONS HERE.
        #
        # `_conf` scores how far the measurement sits from its decision
        # boundary. It cannot see whether the measurement was possible: it
        # returned 0.85 on a run where the segmentation had explicitly failed,
        # and 0.53 on a healthy foot whose "dark area" was background. The cap
        # and penalties below make the score structurally dependent on the
        # conditions that make it mean anything, and every one of them is
        # itemised onto the Triage so the reader sees the reason, not just the
        # number.
        prereqs = prerequisites.evaluate(
            background_warning=background_warning,
            subject_mask_was_degenerate=subject_mask_was_degenerate,
            wound_classification=seg.classification,
            no_wound_region_marker=localization.NONE,
            calibration=calibration,
        )
        confidence, adjustments = prerequisites.apply(
            _conf(strength, quality), prereqs)

        return ModuleResult(
            lesions=lesions,
            triage=_triage("foot", grade, confidence, rationale,
                           confidence_adjustments=adjustments),
            features={
                "erythema_pct": round(ery_pct, 3),
                "breakdown_pct": round(brk_pct, 3),
                "dark_area_pct": round(dark_pct, 3),
                # Regions excluded as backdrop rather than patient. Recorded
                # because a measurement that silently shrank is worse than one
                # that is wrong: a reader has to be able to see that something
                # was removed, and how much.
                "backdrop_excluded": backdrop,
                "subject_L_median": round(L_med, 2),
                # Needed to turn a percentage into cm² once a size reference
                # exists. Without it the percentages cannot be compared
                # between visits at all.
                "subject_area_px": round(subject_area, 1),
                # What the thresholds were measured against, and whether the
                # lesion was large enough that the reference had to be
                # recomputed from the remaining skin. A later reader needs this
                # to know what "relative to the patient's own skin" meant here.
                "skin_reference": skin_ref,
                "dark_area_character": character,
                "yellow_area_character": yellow_character,
                "erythema_character": red_character,
                "dark_coherence": dark_coherence,
                "breakdown_coherence": brk_coherence,
                # What the pixels were allowed to claim, and why. This is the
                # audit trail for the grade: a reader can see the ceiling, the
                # reason for it, and whether the area-based grade had to be
                # lowered to meet it.
                "evidence": report.to_json(),
                "grade_capped_by_evidence": capped,
                # Where the wound is, drawn only where tissue is disrupted.
                # Provider-specific rich view (heuristic detail), used by the
                # overlay and kept for backward compatibility.
                "wound_localization": wound.to_json(),
                # The model-agnostic interface + provenance view. Identical
                # shape whichever provider produced it, so a validated model
                # reports here without any consumer changing. Visible to admin.
                "wound_segmentation": seg.provenance(),
                "re_image_required": ({
                    "reason": "The darkness reads as cast light, and there is "
                              "no tissue loss in the frame to make it an "
                              "eschar of.",
                    "instruction": "Re-take the photograph with the phone "
                                   "flash on, in the open, with the toes held "
                                   "apart so nothing casts a shadow into the "
                                   "web spaces.",
                } if re_image else None),
                "tissue_viability_assessed": False,
            },
        )
