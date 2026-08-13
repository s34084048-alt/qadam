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
    "skin": {
        "lesion_rel_L": 18.0, "inflam_rel_a": 15.0,
        "border_irregular": 1.35, "asymmetry": 0.25,
        "colours": 3, "large_area_pct": 3.0, "min_lesion_pct": 0.3,
    },
    "eye": {
        "sclera_L_drop": 55.0, "sclera_max_chroma_a": 12.0,
        "yellow_b": 16.0, "red_a": 8.0,
        "urgent_yellow_frac": 0.15, "urgent_yellow_b_mean": 12.0,
        "review_red_frac": 0.35, "monitor_red_frac": 0.12,
        # Physiological anisocoria is present in roughly one person in five and
        # is usually under 0.5 mm. A difference of 1 mm or more is the
        # conventional line for "get this looked at", and a photograph cannot
        # tell a benign cause from a dangerous one.
        "anisocoria_urgent_mm": 1.0, "anisocoria_review_mm": 0.5,
    },
    "face": {
        # All thresholds are DIFFERENCES between facial regions, not absolute
        # colours: auto white-balance shifts every region together, so a
        # difference survives it where an absolute value does not.
        "cyanosis_lip_b_drop": 10.0,   # lips less yellow/more blue than cheek
        "cyanosis_lip_a_drop": 4.0,    # and not compensating with redness
        "pallor_lip_a_margin": 3.0,    # lips barely redder than cheek
        "jaundice_sclera_b": 14.0,     # sclera is the built-in white reference
        "jaundice_skin_b_excess": 12.0,
        "flush_cheek_a_excess": 10.0,
        "urgent_cyanosis": 1.0,
        "urgent_jaundice": 1.0,
    },
    "injury": {
        "bruise_b_drop": 8.0, "bruise_resolving_b": 15.0,
        "urgent_solidity": 0.85, "urgent_defect": 0.16, "urgent_asym": 0.30,
        "review_bruise_pct": 2.0, "review_asym": 0.18,
        "monitor_bruise_pct": 0.5,
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
        return module in {"foot", "skin", "eye", "injury", "face"}

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

        self._require_expected_subject(image_bgr, mask, module)

        fn = {
            "foot": self._foot,
            "skin": self._skin,
            "eye": self._eye,
            "injury": self._injury,
            "face": self._face,
        }[module]
        result = fn(image_bgr, mask, quality)
        result.model_version = f"{self.name}-{self.version}"
        result.backend = self.backend_id
        return result

    # -- what each module needs to see before it measures anything ----------

    def _require_expected_subject(self, bgr, mask, module: str) -> None:
        """Refuse an image that does not contain the module's subject.

        Every module here measures colour statistics, and colour statistics can
        be computed from anything. Without this gate the eye module read the
        warm tone of a photograph of a foot as scleral yellowing and returned
        "urgent" at 0.85 confidence.
        """
        _L, a, b = cv_utils.lab_planes(bgr)

        if module in ("foot", "skin", "face"):
            skin, stats = cv_utils.looks_like_skin(a, b, mask)
            if not skin:
                raise SubjectMismatch(
                    module,
                    "The photographed subject does not look like skin "
                    f"(median a* {stats.get('a_median')}, b* {stats.get('b_median')}; "
                    "skin of every tone sits in the warm range).",
                    "Fill the frame with the area of skin being assessed, on a "
                    "plain background, in even light. If you meant to assess an "
                    "eye, choose the eye module.",
                )

        if module == "eye":
            # An eye has one of two structures that skin never has: a dark
            # iris/pupil disc ringed by bright sclera, or a substantial region
            # that is BOTH bright and near-neutral. Brightness matters as much
            # as neutrality -- mid-tone skin scatters enough near-neutral
            # pixels around its own median to clear a neutrality test on its
            # own.
            #
            # The two tests are OR-ed because a JAUNDICED sclera is yellow, not
            # neutral, and would fail the colour test — the very case the eye
            # module exists to catch. Its pupil is still found.
            pupils = cv_utils.measure_pupils(bgr)
            subject = mask > 0
            L_all, _a2, _b2 = cv_utils.lab_planes(bgr)
            sclera_like = 0.0
            if subject.sum() > 0:
                bright = float(np.percentile(L_all[subject], 60))
                sclera_like = float(
                    (subject & (L_all >= bright)
                     & (np.abs(a) <= 8) & (np.abs(b) <= 12)).sum()
                    / float(subject.sum())
                )
            if not pupils and sclera_like < 0.15:
                raise SubjectMismatch(
                    module,
                    "No eye structure was found in this image: neither an "
                    "iris and pupil, nor a region of visible sclera.",
                    "Fill the frame with one open eye, front-on, with the "
                    "eyelids held apart and even light. If you meant to assess "
                    "skin, choose the skin or foot module.",
                )

    # -- foot ---------------------------------------------------------------

    def _foot(self, bgr, mask, quality) -> ModuleResult:
        t = T["foot"]
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        subject_area = float(subject.sum())
        L_med = float(np.median(L[subject]))
        a_med = float(np.median(a[subject]))
        b_med = float(np.median(b[subject]))
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
                "tissue_viability_assessed": False,
            },
        )

    # -- skin ---------------------------------------------------------------

    def _skin(self, bgr, mask, quality) -> ModuleResult:
        t = T["skin"]
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        subject_area = float(subject.sum())
        L_med = float(np.median(L[subject]))
        a_med = float(np.median(a[subject]))
        min_dim = min(bgr.shape[:2])

        pigmented = ((L <= L_med - t["lesion_rel_L"]) & subject).astype(np.uint8) * 255
        inflamed = ((a >= a_med + t["inflam_rel_a"]) & subject).astype(np.uint8) * 255
        pigmented = cv_utils.clean_binary(pigmented, min_dim)
        inflamed = cv_utils.clean_binary(inflamed, min_dim)

        lesion_pct = cv_utils.area_pct(pigmented, mask)
        inflam_pct = cv_utils.area_pct(inflamed, mask)

        blobs = cv_utils.blobs_from_mask(pigmented, subject_area, min_area_pct=0.15, top_n=3)
        lesions: list[Lesion] = []
        irregularity = 0.0
        asymmetry = 0.0
        colours = 1
        largest_pct = 0.0

        if blobs:
            contour, largest_pct, bbox, centroid = blobs[0]
            single = np.zeros(bgr.shape[:2], dtype=np.uint8)
            import cv2  # local: only needed for the single-lesion mask

            cv2.drawContours(single, [contour], -1, 255, thickness=cv2.FILLED)
            irregularity = cv_utils.border_irregularity(contour)
            asymmetry = cv_utils.mask_asymmetry(single)
            colours = cv_utils.colour_cluster_count(bgr, single)
            for c, pct, bb, ct in blobs:
                lesions.append(
                    Lesion(
                        kind="pigmented_lesion",
                        area_pct=pct,
                        severity=float(np.clip(pct / 5.0, 0.05, 1.0)),
                        bbox=bb,
                        centroid=ct,
                        description="Area darker than the surrounding skin",
                    )
                )
        lesions += _lesions_from(inflamed, subject_area, "inflammation",
                                 "Area of surface redness / inflammation", 20.0, top_n=2)

        criteria: list[str] = []
        if largest_pct >= t["min_lesion_pct"]:
            if irregularity >= t["border_irregular"]:
                criteria.append(f"irregular border (index {irregularity:.2f})")
            if asymmetry >= t["asymmetry"]:
                criteria.append(f"asymmetry {asymmetry:.2f}")
            if colours >= t["colours"]:
                criteria.append(f"{colours} distinct colours within the lesion")
            if largest_pct >= t["large_area_pct"]:
                criteria.append(f"lesion covers {largest_pct:.1f}% of the field")
        n = len(criteria)

        rationale = []
        if largest_pct < t["min_lesion_pct"]:
            rationale.append("No discrete pigmented lesion isolated in this image.")
        else:
            rationale.append(
                f"Discrete lesion isolated, {largest_pct:.1f}% of the imaged area."
            )
            rationale.append(
                "Concerning surface features: " + (", ".join(criteria) if criteria
                                                   else "none of the four checked")
                + "."
            )
        if inflam_pct >= 1.0:
            rationale.append(f"Surrounding inflammation covers {inflam_pct:.1f}%.")

        if n >= 3:
            grade, evidence = Grade.URGENT, 0.8
        elif n == 2:
            grade, evidence = Grade.REVIEW, 0.6
        elif n == 1:
            grade, evidence = Grade.MONITOR, 0.45
        else:
            grade, evidence = Grade.NO_FLAG, 0.5

        rationale.append(
            "This is not a dermoscopic assessment. Only dermoscopy and, where "
            "indicated, histopathology can characterise a skin lesion."
        )
        return ModuleResult(
            lesions=lesions,
            triage=_triage("skin", grade, _conf(evidence, quality), rationale),
            features={
                "lesion_area_pct": round(largest_pct, 3),
                "pigmented_total_pct": round(lesion_pct, 3),
                "border_irregularity": round(irregularity, 3),
                "asymmetry": round(asymmetry, 3),
                "colour_clusters": colours,
                "inflammation_pct": round(inflam_pct, 3),
                "criteria_met": criteria,
            },
        )

    # -- eye ----------------------------------------------------------------

    def _eye(self, bgr, mask, quality) -> ModuleResult:
        t = T["eye"]
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        subject_area = float(subject.sum())
        min_dim = min(bgr.shape[:2])

        # Sclera candidate: bright, low red-green chroma. Excludes the iris
        # (dark) and warm periocular skin (high a*). The brightness cut is
        # anchored to the subject's own brightest tissue rather than an
        # absolute value or a mid percentile: the sclera is the brightest
        # structure in an eye photograph at every skin tone, and a mid
        # percentile would land on the sclera's own modal value and shatter
        # the mask into speckle.
        L_cut = float(np.percentile(L[subject], 95)) - t["sclera_L_drop"]
        sclera = (subject & (L >= L_cut) & (np.abs(a) <= t["sclera_max_chroma_a"]))
        sclera_mask = (sclera.astype(np.uint8)) * 255
        sclera_mask = cv_utils.clean_binary(sclera_mask, min_dim)
        sclera_px = sclera_mask > 0
        n_sclera = float(sclera_px.sum())
        if n_sclera < 50:
            sclera_px = subject
            sclera_mask = mask.copy()
            n_sclera = float(subject.sum())

        b_sclera = b[sclera_px]
        a_sclera = a[sclera_px]
        yellow_frac = float((b_sclera >= t["yellow_b"]).mean())
        b_mean = float(b_sclera.mean())
        red_frac = float((a_sclera >= t["red_a"]).mean())
        a_mean = float(a_sclera.mean())

        yellow_mask = cv_utils.clean_binary(
            ((b >= t["yellow_b"]) & sclera_px).astype(np.uint8) * 255, min_dim
        )
        red_mask = cv_utils.clean_binary(
            ((a >= t["red_a"]) & sclera_px).astype(np.uint8) * 255, min_dim
        )

        lesions = (
            _lesions_from(yellow_mask, subject_area, "scleral_yellowing",
                          "Yellow discolouration of the visible sclera", 12.0)
            + _lesions_from(red_mask, subject_area, "ocular_redness",
                            "Redness of the anterior ocular surface", 25.0)
        )

        rationale = [
            f"Yellow tint over {yellow_frac * 100:.0f}% of the visible sclera "
            f"(mean b* {b_mean:.1f}).",
            f"Redness over {red_frac * 100:.0f}% of the visible sclera "
            f"(mean a* {a_mean:.1f}).",
        ]

        if yellow_frac >= t["urgent_yellow_frac"] or b_mean >= t["urgent_yellow_b_mean"]:
            grade = Grade.URGENT
            evidence = min(1.0, max(yellow_frac / t["urgent_yellow_frac"],
                                    b_mean / t["urgent_yellow_b_mean"]) / 2.5)
            rationale.insert(0, "Scleral yellowing suggestive of possible jaundice "
                                "on the image surface.")
        elif red_frac >= t["review_red_frac"]:
            grade = Grade.REVIEW
            evidence = min(1.0, red_frac / t["review_red_frac"] / 2.0)
            rationale.insert(0, "Marked ocular surface redness.")
        elif red_frac >= t["monitor_red_frac"]:
            grade = Grade.MONITOR
            evidence = 0.45
            rationale.insert(0, "Mild ocular surface redness.")
        else:
            grade = Grade.NO_FLAG
            evidence = 0.5
            rationale.insert(0, "No anterior-surface red flag detected.")

        # --- pupils --------------------------------------------------------
        pupils = cv_utils.measure_pupils(bgr)
        anisocoria_mm = None
        if len(pupils) == 2:
            anisocoria_mm = abs(pupils[0]["pupil_diameter_mm"]
                                - pupils[1]["pupil_diameter_mm"])

        pupil_grade = Grade.NO_FLAG
        if anisocoria_mm is not None:
            if anisocoria_mm >= t["anisocoria_urgent_mm"]:
                pupil_grade = Grade.URGENT
                rationale.insert(0,
                    f"Pupils differ by {anisocoria_mm:.1f} mm "
                    f"({pupils[0]['pupil_diameter_mm']:.1f} mm and "
                    f"{pupils[1]['pupil_diameter_mm']:.1f} mm, estimated "
                    f"against an assumed 11.7 mm iris). A difference this size "
                    f"needs same-day assessment; a photograph cannot tell a "
                    f"benign cause from a dangerous one.")
            elif anisocoria_mm >= t["anisocoria_review_mm"]:
                pupil_grade = Grade.REVIEW
                rationale.insert(0,
                    f"Pupils differ by {anisocoria_mm:.1f} mm. Small "
                    f"differences are common and usually benign, but this was "
                    f"measured in one lighting condition only.")

        if pupils:
            rationale.append(
                "Pupil sizes are estimated by scaling against the iris, taken "
                "as 11.7 mm. Ambient light at capture is unknown and PUPIL "
                "REACTION TO LIGHT IS NOT ASSESSED — a still image cannot show "
                "it, and reaction matters more than size."
            )
        else:
            rationale.append(
                "Pupils could not be measured on this image. A close, "
                "front-on, in-focus capture of the eye is needed."
            )

        # The higher of the colour and pupil grades wins: a red eye does not
        # cancel an unequal pupil.
        if pupil_grade.rank > grade.rank:
            grade = pupil_grade
            evidence = max(evidence, 0.6)

        rationale.append(
            "ANTERIOR SURFACE ONLY — the retina is not imaged here. Diabetic "
            "retinopathy and other retinal disease cannot be assessed without a "
            "fundus camera."
        )
        return ModuleResult(
            lesions=lesions,
            triage=_triage("eye", grade, _conf(evidence, quality), rationale),
            features={
                "yellow_fraction": round(yellow_frac, 4),
                "sclera_b_mean": round(b_mean, 2),
                "red_fraction": round(red_frac, 4),
                "sclera_a_mean": round(a_mean, 2),
                "sclera_px_fraction": round(n_sclera / max(subject_area, 1.0), 4),
                "retina_assessed": False,
                "pupils": pupils,
                "pupils_measured": len(pupils),
                "anisocoria_mm": (round(anisocoria_mm, 2)
                                  if anisocoria_mm is not None else None),
                "iris_reference_mm": cv_utils.IRIS_DIAMETER_MM,
                "pupil_reaction_assessed": False,
                "rapd_assessed": False,
            },
        )

    # -- face ---------------------------------------------------------------

    def _face(self, bgr, mask, quality) -> ModuleResult:
        import cv2

        t = T["face"]
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        subject_area = float(subject.sum())
        min_dim = min(bgr.shape[:2])

        box, detector = cv_utils.locate_face(bgr, mask)
        fx, fy, fw, fh = box

        def region(y0, y1, x0, x1):
            """Proportional sub-region of the face box, as a boolean mask."""
            sel = np.zeros(bgr.shape[:2], dtype=bool)
            sel[int(fy + fh * y0): int(fy + fh * y1),
                int(fx + fw * x0): int(fx + fw * x1)] = True
            return sel & subject

        forehead = region(0.10, 0.24, 0.28, 0.72)
        cheeks = region(0.44, 0.62, 0.06, 0.30) | region(0.44, 0.62, 0.70, 0.94)
        lips = region(0.66, 0.82, 0.30, 0.70)
        eye_band = region(0.26, 0.44, 0.10, 0.90)

        def mean_of(sel, plane, fallback=0.0):
            return float(plane[sel].mean()) if sel.sum() > 40 else fallback

        skin_ref = cheeks if cheeks.sum() > 40 else subject
        cheek_a, cheek_b = mean_of(skin_ref, a), mean_of(skin_ref, b)
        fore_a = mean_of(forehead, a, cheek_a)
        lip_a, lip_b = mean_of(lips, a, cheek_a), mean_of(lips, b, cheek_b)

        # The sclera is a near-white surface on the patient, so it doubles as an
        # in-frame white reference: a yellow sclera reading survives white
        # balance in a way an absolute skin reading does not.
        sclera = eye_band & (L >= np.percentile(L[subject], 92)) & (np.abs(a) <= 12)
        sclera_found = bool(sclera.sum() > 30)
        sclera_b = mean_of(sclera, b) if sclera_found else 0.0

        lip_a_margin = lip_a - cheek_a          # lips normally redder than cheek
        lip_b_drop = cheek_b - lip_b            # lips bluer than cheek
        cheek_a_excess = cheek_a - fore_a
        skin_b_excess = cheek_b - sclera_b if sclera_found else 0.0

        cyanosis = (lip_b_drop >= t["cyanosis_lip_b_drop"]
                    and lip_a_margin <= t["cyanosis_lip_a_drop"])
        jaundice = (sclera_found and sclera_b >= t["jaundice_sclera_b"])
        pallor = lip_a_margin <= t["pallor_lip_a_margin"] and not cyanosis
        flushing = cheek_a_excess >= t["flush_cheek_a_excess"]

        lesions: list[Lesion] = []

        def add(sel, kind, description, severity):
            m = cv_utils.clean_binary((sel.astype(np.uint8)) * 255, min_dim)
            found = cv_utils.blobs_from_mask(m, subject_area, 0.05, 1)
            if not found:
                return
            _c, pct, bbox, centroid = found[0]
            lesions.append(Lesion(kind=kind, area_pct=pct,
                                  severity=float(np.clip(severity, 0.05, 1.0)),
                                  bbox=bbox, centroid=centroid,
                                  description=description))

        if cyanosis:
            add(lips, "lip_cyanosis",
                "Lips read blue relative to the cheek in this image",
                lip_b_drop / 25.0)
        if jaundice:
            add(sclera, "scleral_yellowing",
                "Visible sclera reads yellow against the in-frame white "
                "reference", sclera_b / 30.0)
        if pallor:
            add(lips, "lip_pallor",
                "Lips are barely redder than the surrounding skin", 0.4)
        if flushing:
            add(cheeks, "facial_flushing",
                "Cheeks read redder than the forehead", cheek_a_excess / 25.0)

        rationale = [
            f"Face located by {detector}.",
            f"Lip-to-cheek redness margin {lip_a_margin:+.1f} "
            f"(low margin suggests pallor).",
            f"Lip-to-cheek blue shift {lip_b_drop:+.1f} "
            f"(high value suggests blue lips).",
            (f"Sclera yellowness {sclera_b:+.1f} against the in-frame white "
             f"reference." if sclera_found else
             "No sclera visible, so the in-frame white reference is absent and "
             "yellowing could not be assessed."),
        ]

        if cyanosis or jaundice:
            grade = Grade.URGENT
            evidence = 0.6
            if cyanosis:
                rationale.insert(0, "Lips read blue relative to facial skin. "
                                    "MEASURE SpO₂ NOW — this image cannot.")
            if jaundice:
                rationale.insert(0, "Visible sclera reads yellow against the "
                                    "in-frame white reference. Only a serum "
                                    "bilirubin measurement establishes whether "
                                    "this is clinically significant.")
        elif pallor or (jaundice is False and skin_b_excess
                        >= t["jaundice_skin_b_excess"] and sclera_found):
            grade = Grade.REVIEW
            evidence = 0.45
            rationale.insert(0, "Lips are pale relative to the surrounding "
                                "skin. Pallor is judged clinically at the "
                                "conjunctivae, palms and nail beds.")
        elif flushing:
            grade = Grade.MONITOR
            evidence = 0.35
            rationale.insert(0, "Cheeks read flushed relative to the forehead.")
        else:
            grade = Grade.NO_FLAG
            evidence = 0.3
            rationale.insert(0, "No colour flag detected on this image.")

        rationale.append(
            "Facial colour in a photograph is dominated by lighting and camera "
            "white balance. Only relative comparisons between regions are used, "
            "and this is not a pulse oximeter."
        )

        # Colour judgement from a photograph is weak evidence whatever the
        # measurement says. The ceiling here is deliberately below every other
        # module's.
        confidence = min(_conf(evidence, quality), 0.55)

        return ModuleResult(
            lesions=lesions,
            triage=_triage("face", grade, confidence, rationale),
            features={
                "face_detector": detector,
                "lip_to_cheek_redness_margin": round(lip_a_margin, 2),
                "lip_to_cheek_blue_shift": round(lip_b_drop, 2),
                "cheek_to_forehead_redness": round(cheek_a_excess, 2),
                "sclera_yellowness": round(sclera_b, 2) if sclera_found else None,
                "white_reference_available": sclera_found,
                "spo2_measured": False,
                "stroke_assessed": False,
            },
        )

    # -- injury (ROUTING ONLY) ----------------------------------------------

    def _injury(self, bgr, mask, quality) -> ModuleResult:
        t = T["injury"]
        L, a, b = cv_utils.lab_planes(bgr)
        subject = mask > 0
        subject_area = float(subject.sum())
        L_med = float(np.median(L[subject]))
        b_med = float(np.median(b[subject]))
        a_med = float(np.median(a[subject]))
        min_dim = min(bgr.shape[:2])

        # Fresh bruise: shifted blue/purple (b* below the skin's own baseline)
        # and darker. Resolving bruise: green-yellow (b* above, a* below).
        fresh = ((b <= b_med - t["bruise_b_drop"]) & (L <= L_med + 8) & subject)
        resolving = ((b >= b_med + t["bruise_resolving_b"]) & (a <= a_med - 2) & subject)
        bruise = cv_utils.clean_binary(
            ((fresh | resolving).astype(np.uint8)) * 255, min_dim
        )
        bruise_pct = cv_utils.area_pct(bruise, mask)

        asym = cv_utils.mask_asymmetry(mask)
        solidity, defect = cv_utils.contour_solidity(mask)

        lesions = _lesions_from(
            bruise, subject_area, "bruising",
            "Surface discolouration consistent with bruising", 10.0
        )
        if asym >= t["review_asym"]:
            ys, xs = np.where(subject)
            if xs.size:
                bbox = (int(xs.min()), int(ys.min()),
                        int(xs.max() - xs.min()), int(ys.max() - ys.min()))
                lesions.append(
                    Lesion(
                        kind="asymmetric_swelling",
                        area_pct=100.0,
                        severity=float(np.clip(asym / 0.5, 0.05, 1.0)),
                        bbox=bbox,
                        centroid=(int(xs.mean()), int(ys.mean())),
                        description="Outline is asymmetric about its long axis",
                    )
                )
        if solidity <= t["urgent_solidity"] or defect >= t["urgent_defect"]:
            ys, xs = np.where(subject)
            if xs.size:
                bbox = (int(xs.min()), int(ys.min()),
                        int(xs.max() - xs.min()), int(ys.max() - ys.min()))
                lesions.append(
                    Lesion(
                        kind="visible_deformity",
                        area_pct=100.0,
                        severity=float(np.clip((1.0 - solidity) / 0.3, 0.05, 1.0)),
                        bbox=bbox,
                        centroid=(int(xs.mean()), int(ys.mean())),
                        description="Contour step or bulge visible in the outline",
                    )
                )

        rationale = [
            f"Surface discolouration consistent with bruising over "
            f"{bruise_pct:.1f}% of the imaged region.",
            f"Outline asymmetry index {asym:.2f}.",
            f"Contour solidity {solidity:.2f} (deepest defect {defect:.2f}).",
        ]

        if (solidity <= t["urgent_solidity"] or defect >= t["urgent_defect"]
                or asym >= t["urgent_asym"]):
            grade = Grade.URGENT
            evidence = 0.75
            rationale.insert(0, "Visible contour deformity and/or marked "
                                "asymmetry — an external red flag.")
        elif bruise_pct >= t["review_bruise_pct"] or asym >= t["review_asym"]:
            grade = Grade.REVIEW
            evidence = 0.6
            rationale.insert(0, "External red flag present (bruising and/or "
                                "asymmetric swelling).")
        elif bruise_pct >= t["monitor_bruise_pct"]:
            grade = Grade.MONITOR
            evidence = 0.45
            rationale.insert(0, "Minor surface discolouration only.")
        else:
            grade = Grade.NO_FLAG
            evidence = 0.4
            rationale.insert(0, "No external red flag detected on the surface.")

        rationale.append(
            "ROUTING ONLY — this module cannot confirm or exclude fracture, "
            "dislocation, tendon or muscle rupture, or internal bleeding. "
            "Imaging and clinical assessment decide that."
        )
        if grade is Grade.NO_FLAG:
            rationale.append(
                "A NO-FLAG RESULT DOES NOT EXCLUDE INTERNAL INJURY."
            )
        return ModuleResult(
            lesions=lesions,
            triage=_triage("injury", grade, _conf(evidence, quality), rationale),
            features={
                "bruise_pct": round(bruise_pct, 3),
                "asymmetry": round(asym, 3),
                "solidity": round(solidity, 3),
                "convexity_defect": round(defect, 3),
                "routing_only": True,
                "internal_injury_assessed": False,
            },
        )
