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

def _skin_base(seed: int) -> tuple[np.ndarray, np.ndarray]:
    img = _canvas(seed)
    mask = _blob_mask(
        lambda m: cv2.ellipse(m, (400, 300), (300, 235), 0, 0, 360, 255, -1)
    )
    cv2.ellipse(img, (400, 300), (300, 235), 0, 0, 360, SKIN, -1)
    _texture(img, mask, seed)
    return img, mask


def skin_urgent(seed: int = 21) -> np.ndarray:
    """Irregular border, asymmetry, several colours, large -> urgent."""
    img, mask = _skin_base(seed)
    poly = _irregular_polygon(395, 300, 95, seed)
    cv2.fillPoly(img, [poly], (58, 52, 74))                                 # brown-black
    cv2.ellipse(img, (360, 272), (44, 34), 25, 0, 360, (26, 24, 30), -1)    # near-black
    cv2.ellipse(img, (438, 330), (38, 30), -15, 0, 360, (72, 68, 152), -1)  # red-brown
    cv2.ellipse(img, (410, 258), (26, 20), 40, 0, 360, (104, 96, 92), -1)   # slate
    _texture(img, mask, seed + 5, amount=4.0)
    return img


def skin_clean(seed: int = 22) -> np.ndarray:
    img, _mask = _skin_base(seed)
    return img


# --- eye ---------------------------------------------------------------------

def _eye_base(seed: int, sclera_bgr: tuple[int, int, int]) -> np.ndarray:
    img = _canvas(seed)
    # Periocular skin fills the frame; the eye is the subject.
    cv2.rectangle(img, (0, 0), (W, H), SKIN, -1)
    skin_mask = np.full((H, W), 255, dtype=np.uint8)
    _texture(img, skin_mask, seed, amount=4.0)

    eye = _blob_mask(
        lambda m: cv2.ellipse(m, (400, 300), (250, 118), 0, 0, 360, 255, -1)
    )
    cv2.ellipse(img, (400, 300), (250, 118), 0, 0, 360, sclera_bgr, -1)
    cv2.circle(img, (400, 300), 86, (86, 74, 62), -1)     # iris
    cv2.circle(img, (400, 300), 38, (24, 22, 20), -1)     # pupil
    cv2.circle(img, (372, 272), 14, (250, 250, 250), -1)  # catchlight
    _texture(img, eye, seed + 7, amount=3.0)
    return img


def eye_urgent(seed: int = 31) -> np.ndarray:
    """Yellow sclera -> possible jaundice -> urgent, same-day medical review."""
    return _eye_base(seed, (118, 214, 232))


def eye_clean(seed: int = 32) -> np.ndarray:
    return _eye_base(seed, (238, 240, 242))


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


def eye_pupils_equal(seed: int = 33) -> np.ndarray:
    return _both_eyes(seed, 26, 27)


def eye_anisocoria(seed: int = 34) -> np.ndarray:
    """~2.5 mm difference between the pupils — an urgent routing flag."""
    return _both_eyes(seed, 22, 36)


# --- face --------------------------------------------------------------------

def _face_base(
    seed: int,
    skin: tuple[int, int, int],
    lip: tuple[int, int, int],
    sclera: tuple[int, int, int],
) -> np.ndarray:
    """A schematic face. Regions sit where the module samples them, so the
    relative-colour logic is exercised end to end."""
    img = _canvas(seed)
    mask = _blob_mask(
        lambda m: cv2.ellipse(m, (400, 300), (200, 262), 0, 0, 360, 255, -1)
    )
    cv2.ellipse(img, (400, 300), (200, 262), 0, 0, 360, skin, -1)

    # Eyes, sitting in the module's 0.26-0.44 band.
    for cx in (318, 482):
        cv2.ellipse(img, (cx, 262), (46, 24), 0, 0, 360, sclera, -1)
        cv2.circle(img, (cx, 262), 18, (92, 78, 64), -1)
        cv2.circle(img, (cx, 262), 8, (26, 24, 22), -1)

    # Lips, in the 0.66-0.82 band.
    cv2.ellipse(img, (400, 432), (70, 26), 0, 0, 360, lip, -1)
    _texture(img, mask, seed, amount=4.0)
    return img


def face_normal(seed: int = 61) -> np.ndarray:
    return _face_base(seed, SKIN, (120, 110, 200), (238, 240, 242))


def face_cyanosis(seed: int = 62) -> np.ndarray:
    """Lips read blue against the cheek -> urgent, measure SpO2 now."""
    return _face_base(seed, SKIN, (185, 120, 120), (236, 238, 240))


def face_jaundice(seed: int = 63) -> np.ndarray:
    """Yellow sclera against the in-frame white reference -> urgent."""
    return _face_base(seed, (140, 190, 215), (120, 110, 200), (120, 214, 232))


# --- injury ------------------------------------------------------------------

def _limb(img: np.ndarray, mask: np.ndarray) -> None:
    cv2.ellipse(img, (400, 300), (128, 236), 0, 0, 360, SKIN, -1)
    cv2.ellipse(mask, (400, 300), (128, 236), 0, 0, 360, 255, -1)


def injury_urgent(seed: int = 41) -> np.ndarray:
    """A limb whose outline is sharply angulated -- an external deformity red
    flag. ROUTING ONLY: this says nothing about what is under the skin."""
    img = _canvas(seed)
    mask = np.zeros((H, W), dtype=np.uint8)
    for shape in (img, mask):
        colour = SKIN if shape is img else 255
        cv2.ellipse(shape, (286, 196), (88, 176), 8, 0, 360, colour, -1)
        cv2.ellipse(shape, (498, 402), (86, 158), 68, 0, 360, colour, -1)
        cv2.ellipse(shape, (372, 300), (74, 66), 0, 0, 360, colour, -1)
    _texture(img, mask, seed, amount=4.0)
    return img


def injury_review(seed: int = 42) -> np.ndarray:
    """Extensive bruising on a symmetric limb -> imaging + clinician review."""
    img = _canvas(seed)
    mask = np.zeros((H, W), dtype=np.uint8)
    _limb(img, mask)
    cv2.ellipse(img, (400, 330), (92, 118), 0, 0, 360, (156, 118, 128), -1)
    cv2.ellipse(img, (392, 322), (58, 74), 0, 0, 360, (168, 104, 108), -1)
    _texture(img, mask, seed, amount=4.0)
    return img


def injury_clean(seed: int = 43) -> np.ndarray:
    img = _canvas(seed)
    mask = np.zeros((H, W), dtype=np.uint8)
    _limb(img, mask)
    _texture(img, mask, seed, amount=4.0)
    return img


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
    Sample("skin_urgent", "skin", "urgent", skin_urgent,
           "Irregular, asymmetric, multi-coloured pigmented lesion."),
    Sample("skin_clean", "skin", "no_flag", skin_clean,
           "Uniform skin, no discrete lesion."),
    Sample("eye_urgent", "eye", "urgent", eye_urgent,
           "Yellow sclera — possible jaundice on the image surface."),
    Sample("eye_clean", "eye", "no_flag", eye_clean,
           "White sclera, no anterior-surface flag."),
    Sample("eye_anisocoria", "eye", "urgent", eye_anisocoria,
           "Pupils differ by ~2.6 mm — routing flag, cause not determined."),
    Sample("eye_pupils_equal", "eye", "no_flag", eye_pupils_equal,
           "Pupils within 0.2 mm of each other in this lighting."),
    Sample("face_cyanosis", "face", "urgent", face_cyanosis,
           "Lips read blue against the cheek — possible central cyanosis."),
    Sample("face_jaundice", "face", "urgent", face_jaundice,
           "Sclera reads yellow against the in-frame white reference."),
    Sample("face_normal", "face", "no_flag", face_normal,
           "No colour flag. Does not exclude hypoxaemia or anaemia."),
    Sample("injury_urgent", "injury", "urgent", injury_urgent,
           "Visible contour deformity — routing red flag only."),
    Sample("injury_review", "injury", "review", injury_review,
           "Extensive bruising — routing red flag only."),
    Sample("injury_clean", "injury", "no_flag", injury_clean,
           "No external red flag. Does NOT exclude internal injury."),
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
