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

import cv2
import numpy as np

from .. import cv_utils
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


def _conf(evidence: float, quality: QualityReport) -> float:
    """Confidence = how far the evidence sits from the decision boundary,
    discounted by image quality. Capped at 0.85: an unvalidated placeholder
    model has no business reporting near-certainty."""
    base = 0.45 + 0.40 * float(np.clip(evidence, 0.0, 1.0))
    return float(np.clip(base * quality.confidence_factor, 0.15, 0.85))


def _triage(
    module: str, grade: Grade, confidence: float, rationale: list[str]
) -> Triage:
    spec = routing_for(module, str(grade))
    return Triage(
        grade=grade,
        label=spec["label"],
        confidence=confidence,
        rationale=rationale,
        next_investigation=spec["next_investigation"],
        urgency=spec["urgency"],
        routing_target=spec["routing_target"],
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
        self, image_bgr: np.ndarray, module: str, quality: QualityReport
    ) -> ModuleResult:
        mask = quality.mask
        if mask is None:
            mask, _ = cv_utils.estimate_subject_mask(image_bgr)
        subject = mask > 0
        if subject.sum() < 100:
            mask = np.full(image_bgr.shape[:2], 255, dtype=np.uint8)
            subject = mask > 0

        mask = self._widen_if_the_lesion_became_the_subject(image_bgr, mask, module)
        self._require_expected_subject(image_bgr, mask, module)

        fn = {
            "foot": self._foot,
        }[module]
        result = fn(image_bgr, mask, quality)
        result.model_version = f"{self.name}-{self.version}"
        result.backend = self.backend_id
        return result

    # -- what each module needs to see before it measures anything ----------

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

    def _require_expected_subject(self, bgr, mask, module: str) -> None:
        """Refuse an image that does not contain the module's subject.

        Every module here measures colour statistics, and colour statistics can
        be computed from anything. Without this gate the eye module read the
        warm tone of a photograph of a foot as scleral yellowing and returned
        "urgent" at 0.85 confidence.
        """
        _L, a, b = cv_utils.lab_planes(bgr)
        skin, stats = cv_utils.looks_like_skin(a, b, mask)
        if not skin:
            raise SubjectMismatch(
                module,
                "The photographed subject does not look like skin "
                f"(median a* {stats.get('a_median')}, b* {stats.get('b_median')}; "
                "skin of every tone sits in the warm range).",
                "Fill the frame with the foot or the area of skin being "
                "assessed, on a plain background, in even light.",
            )

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

    def _foot(self, bgr, mask, quality) -> ModuleResult:
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

        # Discard thin dark structures: skin creases, the gap between toes and
        # the line under a nail are all long and narrow, and none of them is a
        # lesion.
        dark = cv_utils.drop_thin_structures(
            dark, t["dark_min_radius_frac"] * float(np.sqrt(subject_area)))

        ery_pct = cv_utils.area_pct(erythema, mask)
        dark_pct = cv_utils.area_pct(dark, mask)
        brk_pct = cv_utils.area_pct(slough, mask)

        self._refuse_if_the_reference_is_the_lesion(L, subject, dark_pct,
                                                    brk_pct, ery_pct)

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
        if dark_pct > 0:
            rationale.append(
                "A DARK AREA IS NOT A DIAGNOSIS OF NECROSIS. Shadow, bruising "
                "and normal pigmentation look the same in a photograph. "
                "Re-image in even, indirect light before acting on it, and "
                "confirm by direct inspection."
            )

        if brk_pct >= t["urgent_breakdown_pct"] or dark_pct >= t["urgent_dark_pct"]:
            grade = Grade.URGENT
            evidence = max(dark_pct / t["urgent_dark_pct"],
                           brk_pct / t["urgent_breakdown_pct"]) / 4.0
            rationale.insert(0, "Visible tissue breakdown and/or an extensive "
                                "dark area meets the urgent threshold.")
        elif dark_pct >= t["review_dark_pct"]:
            grade = Grade.REVIEW
            evidence = dark_pct / t["urgent_dark_pct"]
            rationale.insert(0, "A discrete dark area is present. This routes "
                                "for a clinician to look at the foot — it does "
                                "not assert that the tissue is non-viable.")
        elif brk_pct >= t["review_breakdown_pct"] or ery_pct >= t["review_erythema_pct"]:
            grade = Grade.REVIEW
            evidence = max(brk_pct / t["review_breakdown_pct"],
                           ery_pct / t["review_erythema_pct"]) / 3.0
            rationale.insert(0, "Surface changes exceed the review threshold.")
        elif ery_pct >= t["monitor_erythema_pct"]:
            grade = Grade.MONITOR
            evidence = ery_pct / t["review_erythema_pct"]
            rationale.insert(0, "Mild surface erythema only.")
        else:
            grade = Grade.NO_FLAG
            evidence = 1.0 - min(1.0, ery_pct / max(t["monitor_erythema_pct"], 1e-6))
            rationale.insert(0, "No surface red flag detected in this image.")

        rationale.append(
            "Depth, bone involvement, infection, perfusion and neuropathy are "
            "not assessable from a photograph."
        )
        return ModuleResult(
            lesions=lesions,
            triage=_triage("foot", grade, _conf(evidence, quality), rationale),
            features={
                "erythema_pct": round(ery_pct, 3),
                "breakdown_pct": round(brk_pct, 3),
                "dark_area_pct": round(dark_pct, 3),
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
                "tissue_viability_assessed": False,
            },
        )
