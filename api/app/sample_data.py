"""Deterministic SYNTHETIC sample images.

Drawn from primitives. No patient data, no scraped images, nothing derived from
a real person. They exist so the pipeline, the seed script and the test suite
have inputs with a known expected grade -- they are not training data and they
are not evidence that the placeholder model works on real skin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

W, H = 800, 600
BACKDROP = (108, 104, 100)          # plain clinical backdrop (BGR)
SKIN = (150, 175, 205)              # mid-tone skin (BGR)


def _canvas(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), BACKDROP, dtype=np.uint8)
    noise = rng.normal(0, 3.0, (H, W, 3))
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _texture(img: np.ndarray, mask: np.ndarray, seed: int, amount: float = 5.0) -> None:
    """Skin is never flat; give the subject fine texture so focus is realistic."""
    rng = np.random.default_rng(seed + 991)
    noise = rng.normal(0, amount, img.shape).astype(np.float32)
    blended = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    img[mask > 0] = blended[mask > 0]


def _blob_mask(draw: Callable[[np.ndarray], None]) -> np.ndarray:
    mask = np.zeros((H, W), dtype=np.uint8)
    draw(mask)
    return mask


def _irregular_polygon(cx: int, cy: int, r: int, seed: int, spikes: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pts = []
    for i in range(spikes * 2):
        angle = np.pi * 2 * i / (spikes * 2)
        radius = r * (1.35 if i % 2 == 0 else 0.55) * float(rng.uniform(0.8, 1.25))
        # Squash one side so the shape is genuinely asymmetric.
        squash = 0.62 if np.cos(angle) < 0 else 1.0
        pts.append([cx + radius * np.cos(angle) * squash, cy + radius * np.sin(angle)])
    return np.array(pts, dtype=np.int32)


# --- foot --------------------------------------------------------------------

def _foot_base(seed: int) -> tuple[np.ndarray, np.ndarray]:
    img = _canvas(seed)
    mask = _blob_mask(
        lambda m: cv2.ellipse(m, (400, 320), (185, 250), 8, 0, 360, 255, -1)
    )
    cv2.ellipse(img, (400, 320), (185, 250), 8, 0, 360, SKIN, -1)
    _texture(img, mask, seed)
    return img, mask


def foot_dark_area(seed: int = 11) -> np.ndarray:
    """A discrete dark area with surrounding erythema.

    Graded REVIEW, not urgent. A photograph cannot tell eschar from a shadow,
    a bruise or pigmentation, so the module routes it to be looked at rather
    than asserting the tissue is dead.
    """
    img, mask = _foot_base(seed)
    cv2.ellipse(img, (415, 430), (86, 62), 0, 0, 360, (95, 115, 190), -1)   # erythema
    cv2.ellipse(img, (415, 435), (44, 32), 0, 0, 360, (38, 40, 48), -1)     # dark area
    _texture(img, mask, seed + 3, amount=4.0)
    return img


def foot_urgent(seed: int = 13) -> np.ndarray:
    """An open wound bed with slough -- breakdown of the surface itself, which
    is a far more specific finding than darkness. -> urgent."""
    img, mask = _foot_base(seed)
    cv2.ellipse(img, (410, 420), (96, 74), 0, 0, 360, (95, 115, 190), -1)   # erythema
    cv2.ellipse(img, (410, 424), (60, 46), 0, 0, 360, (110, 190, 215), -1)  # slough
    cv2.ellipse(img, (398, 418), (30, 22), 20, 0, 360, (120, 205, 228), -1)
    _texture(img, mask, seed + 3, amount=4.0)
    return img


def foot_shadow_only(seed: int = 14) -> np.ndarray:
    """Healthy skin with an ordinary shadow crease. Regression guard: this is
    the shape that used to be reported as urgent necrotic tissue."""
    img, mask = _foot_base(seed)
    cv2.line(img, (330, 130), (318, 520), (48, 54, 64), 20)
    cv2.line(img, (470, 140), (486, 540), (50, 56, 66), 16)
    _texture(img, mask, seed + 4, amount=4.0)
    return img


def foot_clean(seed: int = 12) -> np.ndarray:
    img, _mask = _foot_base(seed)
    return img


# --- skin --------------------------------------------------------------------


# --- eye ---------------------------------------------------------------------


def _both_eyes(seed: int, pupil_left: int, pupil_right: int) -> np.ndarray:
    """Both eyes in one frame, drawn with a fixed iris radius so the pupil
    difference is the only variable. Iris 62 px stands in for 11.7 mm."""
    img = _canvas(seed)
    cv2.rectangle(img, (0, 0), (W, H), SKIN, -1)
    _texture(img, np.full((H, W), 255, dtype=np.uint8), seed, amount=4.0)
    for cx, pupil in ((250, pupil_left), (550, pupil_right)):
        cv2.ellipse(img, (cx, 300), (150, 82), 0, 0, 360, (238, 240, 242), -1)
        cv2.circle(img, (cx, 300), 62, (92, 78, 64), -1)
        cv2.circle(img, (cx, 300), pupil, (22, 20, 18), -1)
    return img



# --- face --------------------------------------------------------------------


# --- injury ------------------------------------------------------------------

def _limb(img: np.ndarray, mask: np.ndarray) -> None:
    cv2.ellipse(img, (400, 300), (128, 236), 0, 0, 360, SKIN, -1)
    cv2.ellipse(mask, (400, 300), (128, 236), 0, 0, 360, 255, -1)





# --- quality-gate negatives --------------------------------------------------

def blurred(seed: int = 51) -> np.ndarray:
    return cv2.GaussianBlur(foot_urgent(seed), (0, 0), 11.0)


def too_dark(seed: int = 52) -> np.ndarray:
    img = foot_urgent(seed).astype(np.float32) * 0.14
    return np.clip(img, 0, 255).astype(np.uint8)


def too_small(seed: int = 53) -> np.ndarray:
    return cv2.resize(foot_urgent(seed), (200, 150), interpolation=cv2.INTER_AREA)


# --- registry ----------------------------------------------------------------

@dataclass(frozen=True)
class Sample:
    name: str
    module: str
    expected_grade: str | None      # None = expected to fail the quality gate
    builder: Callable[[], np.ndarray]
    description: str


SAMPLES: list[Sample] = [
    Sample("foot_urgent", "foot", "urgent", foot_urgent,
           "Open wound bed with slough — breakdown of the surface itself."),
    Sample("foot_dark_area", "foot", "review", foot_dark_area,
           "Discrete dark area. Routed for inspection, NOT called necrotic."),
    Sample("foot_shadow_only", "foot", "no_flag", foot_shadow_only,
           "Healthy skin with shadow creases — must not alarm."),
    Sample("foot_clean", "foot", "no_flag", foot_clean,
           "Intact-appearing skin, no surface red flag."),
    Sample("quality_blurred", "foot", None, blurred,
           "Out of focus — must be rejected by the quality gate."),
    Sample("quality_dark", "foot", None, too_dark,
           "Under-exposed — must be rejected by the quality gate."),
    Sample("quality_small", "foot", None, too_small,
           "Below minimum resolution — must be rejected by the quality gate."),
]

BY_NAME = {s.name: s for s in SAMPLES}


def png_bytes(name: str) -> bytes:
    img = BY_NAME[name].builder()
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError(f"failed to encode sample {name}")
    return buf.tobytes()
