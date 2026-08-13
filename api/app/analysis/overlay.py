"""Annotated overlay rendering.

The overlay is an image that can be screenshotted, printed or forwarded on its
own, so the disclaimer is burned into it. Findings are labelled with what is
VISIBLE, never with a diagnosis.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..safety import DEVICE_NOTICE, DISCLAIMER
from .modules_config import GRADE_STYLE
from .types import Lesion, QualityReport, Triage

# BGR colours per finding kind.
KIND_COLOR = {
    "dark_area": (70, 70, 160),
    "tissue_breakdown": (0, 150, 235),
    "erythema": (90, 90, 240),
    "pigmented_lesion": (170, 60, 40),
    "inflammation": (90, 90, 240),
    "scleral_yellowing": (0, 190, 220),
    "ocular_redness": (70, 70, 235),
    "lip_cyanosis": (190, 110, 60),
    "lip_pallor": (200, 180, 170),
    "facial_flushing": (90, 90, 240),
    "bruising": (150, 60, 130),
    "asymmetric_swelling": (200, 140, 40),
    "visible_deformity": (40, 40, 200),
}
DEFAULT_COLOR = (200, 200, 200)

KIND_LABEL = {
    "dark_area": "dark area (shadow? bruise? tissue?)",
    "tissue_breakdown": "tissue breakdown",
    "erythema": "erythema",
    "pigmented_lesion": "pigmented lesion",
    "inflammation": "inflammation",
    "scleral_yellowing": "scleral yellowing",
    "ocular_redness": "ocular redness",
    "lip_cyanosis": "blue lips (measure SpO2)",
    "lip_pallor": "pale lips",
    "facial_flushing": "facial flushing",
    "bruising": "bruising",
    "asymmetric_swelling": "asymmetric swelling",
    "visible_deformity": "visible deformity",
}


def _ascii(text: str) -> str:
    """OpenCV's Hershey fonts are ASCII-only; anything else renders as '?'.
    Burned-in text must stay readable, so transliterate before drawing."""
    replacements = {
        "—": "-", "–": "-", "‘": "'", "’": "'",
        "“": '"', "”": '"', "…": "...", " ": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("ascii", "ignore").decode("ascii")


def _hex_to_bgr(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    r, g, b = (int(value[i: i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def _band(img: np.ndarray, y0: int, y1: int, color, alpha: float = 0.78) -> None:
    y0, y1 = max(0, y0), min(img.shape[0], y1)
    if y1 <= y0:
        return
    strip = img[y0:y1]
    overlay = np.full_like(strip, color, dtype=np.uint8)
    img[y0:y1] = cv2.addWeighted(overlay, alpha, strip, 1.0 - alpha, 0)


def render_overlay(
    image_bgr: np.ndarray,
    lesions: list[Lesion],
    triage: Triage,
    quality: QualityReport,
    module: str,
) -> np.ndarray:
    img = image_bgr.copy()
    h, w = img.shape[:2]
    # Text size tracks image width so the burned-in notice keeps a constant
    # RELATIVE size. Capping this at 1.0 made the disclaimer about a fifth of
    # its intended height on a 4000 px phone capture -- effectively unreadable
    # on the one artefact most likely to be forwarded on its own.
    scale = float(np.clip(w / 900.0, 0.4, 4.0))
    font = cv2.FONT_HERSHEY_SIMPLEX
    thin = max(1, int(round(1.4 * scale)))

    # Subject outline, faint.
    if quality.mask is not None:
        contours, _ = cv2.findContours(
            quality.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cv2.drawContours(img, contours, -1, (180, 180, 180), thin)

    # Findings.
    for lesion in lesions:
        color = KIND_COLOR.get(lesion.kind, DEFAULT_COLOR)
        x, y, bw, bh = lesion.bbox
        cv2.rectangle(img, (x, y), (x + bw, y + bh), color, max(1, thin + 1))
        label = _ascii(
            f"{KIND_LABEL.get(lesion.kind, lesion.kind)} {lesion.area_pct:.1f}%"
        )
        (tw, th), _ = cv2.getTextSize(label, font, 0.45 * scale, thin)
        ty = max(th + 4, y - 4)
        cv2.rectangle(img, (x, ty - th - 4), (x + tw + 6, ty + 2), color, cv2.FILLED)
        cv2.putText(img, label, (x + 3, ty - 2), font, 0.45 * scale,
                    (255, 255, 255), thin, cv2.LINE_AA)

    # Grade band, top.
    style = GRADE_STYLE[str(triage.grade)]
    grade_color = _hex_to_bgr(style["color"])
    band_h = int(38 * scale) + 14
    _band(img, 0, band_h, grade_color, alpha=0.85)
    grade_text = _ascii(f"{style['label_en'].upper()} - {triage.label}")
    cv2.putText(img, grade_text, (10, int(band_h * 0.45) + 4), font,
                0.62 * scale, (255, 255, 255), max(1, thin + 1), cv2.LINE_AA)
    meta = (f"module: {module} | confidence {triage.confidence:.2f} | "
            f"quality {'PASS' if quality.passed else 'DEGRADED'}")
    cv2.putText(img, meta, (10, band_h - 6), font, 0.42 * scale,
                (255, 255, 255), thin, cv2.LINE_AA)

    # Disclaimer band, bottom -- burned in, two lines.
    foot_h = int(46 * scale) + 16
    _band(img, h - foot_h, h, (25, 25, 25), alpha=0.82)
    cv2.putText(img, _ascii(DEVICE_NOTICE), (10, h - foot_h + int(20 * scale)), font,
                0.44 * scale, (60, 190, 255), max(1, thin + 1), cv2.LINE_AA)
    cv2.putText(img,
                "Research/decision-support tool - not a diagnosis. "
                "Not a substitute for clinical assessment.",
                (10, h - int(10 * scale)), font, 0.40 * scale,
                (235, 235, 235), thin, cv2.LINE_AA)
    return img


__all__ = ["render_overlay", "DISCLAIMER"]
