"""Deterministic SYNTHETIC fixtures for the pre-analysis input gate.

Drawn from OpenCV primitives, exactly like `app.sample_data`. No patient data,
no scraped images, nothing derived from a real person or a real clinic. They
exist so the gate has inputs whose correct verdict is known by construction.

They are NOT real clinical photographs, and a threshold fitted to them is
fitted to a drawing. Every constant the gate derives from these is marked as a
guess in its own comment. What they do establish is the *ordering* the gate has
to preserve: a watermarked frame and a re-photographed frame must land on the
far side of a boundary that a clean foot and a wet, glistening ulcer stay on
the near side of.

Regenerate the committed .jpg files with:

    python -m tests.fixture_images

The committed files, not these functions, are what the tests read. Fixtures are
saved as JPEG because the failure that motivated this gate arrived as a JPEG
stock photograph, and JPEG ringing around hard-edged overlay text is part of
what the detector has to survive.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

W, H = 800, 600
BACKDROP = (108, 104, 100)          # plain clinical backdrop (BGR)
SKIN = (150, 175, 205)              # mid-tone skin (BGR)
JPEG_QUALITY = 85                   # what a phone camera actually writes


# --- shared scaffolding ------------------------------------------------------

def _canvas(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), BACKDROP, dtype=np.uint8)
    noise = rng.normal(0, 3.0, (H, W, 3))
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _texture(img: np.ndarray, mask: np.ndarray, seed: int, amount: float = 5.0) -> None:
    rng = np.random.default_rng(seed + 991)
    noise = rng.normal(0, amount, img.shape).astype(np.float32)
    blended = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    img[mask > 0] = blended[mask > 0]


def _sensor_noise(img: np.ndarray, seed: int, amount: float = 2.5) -> np.ndarray:
    """A final noise pass over the WHOLE frame, applied last.

    Deliberately applied AFTER any overlay is composited. A watermark drawn on
    a noiseless canvas would be perfectly flat, and a detector could separate it
    from a photograph on that alone -- which would pass the test without
    detecting any text. Noising everything last removes that shortcut.
    """
    rng = np.random.default_rng(seed + 7717)
    noise = rng.normal(0, amount, img.shape)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _foot_base(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The same foot geometry `app.sample_data` draws, so the gate fixtures and
    the grading fixtures agree on what a well-framed foot looks like."""
    img = _canvas(seed)
    mask = np.zeros((H, W), dtype=np.uint8)
    cv2.ellipse(mask, (400, 320), (185, 250), 8, 0, 360, 255, -1)
    cv2.ellipse(img, (400, 320), (185, 250), 8, 0, 360, SKIN, -1)
    _texture(img, mask, seed)
    return img, mask


# --- the four fixtures -------------------------------------------------------

def clean_foot(seed: int = 12) -> np.ndarray:
    """Intact-looking skin, well framed, no overlay. MUST PASS the gate."""
    img, _mask = _foot_base(seed)
    return _sensor_noise(img, seed)


def wet_ulcer(seed: int = 31) -> np.ndarray:
    """A glistening ulcer: an open wound bed under specular highlights.

    The false-positive guard named in the task. Wet tissue throws small, bright,
    hard-cored glints, and a naive "bright high-contrast blob" text detector
    reads those as glyphs. This frame carries fourteen of them, at the size
    range display text occupies, and it MUST PASS the gate.

    The glints are drawn with a bright core and a soft rim, which is how a
    specular reflection actually falls off, and they are scattered rather than
    set on a baseline -- the two properties the gate is allowed to rely on.
    """
    img, mask = _foot_base(seed)
    cv2.ellipse(img, (410, 400), (128, 100), 0, 0, 360, (95, 115, 190), -1)   # erythema
    cv2.ellipse(img, (410, 404), (86, 66), 0, 0, 360, (105, 150, 205), -1)    # wound bed
    cv2.ellipse(img, (396, 396), (44, 32), 20, 0, 360, (110, 190, 215), -1)   # slough
    _texture(img, mask, seed + 3, amount=4.0)

    rng = np.random.default_rng(seed + 17)
    glare = np.zeros((H, W), dtype=np.float32)
    for _ in range(14):
        cx = int(rng.uniform(340, 480))
        cy = int(rng.uniform(345, 465))
        rx = int(rng.uniform(4, 12))
        ry = max(3, int(rx * rng.uniform(0.45, 1.0)))
        ang = float(rng.uniform(0, 180))
        cv2.ellipse(glare, (cx, cy), (rx, ry), ang, 0, 360, 255.0, -1)
    # The soft rim. A glint is not a glyph: its edge is a falloff, not a step.
    glare = cv2.GaussianBlur(glare, (0, 0), 2.2)
    glare = np.clip(glare / 255.0, 0, 1)[:, :, None]
    img = np.clip(img.astype(np.float32) * (1 - glare) + 246.0 * glare,
                  0, 255).astype(np.uint8)
    return _sensor_noise(img, seed)


def _cursive_line(img: np.ndarray, x: int, y: int, width: int, seed: int,
                  colour: tuple[int, int, int], thickness: int = 2) -> None:
    """A right-to-left cursive script line, drawn as connected strokes.

    The clinic watermark that got through carried a line of Persian text. This
    is a STROKE RENDERING of a cursive line, not shaped Persian -- OpenCV has no
    Arabic-script font and the project has no text-rendering dependency. It
    reproduces what the detector actually sees: a run of ink of consistent
    height sitting on a common baseline, with ascenders and detached dots.
    """
    rng = np.random.default_rng(seed)
    x_cursor = x
    while x_cursor < x + width:
        seg = int(rng.uniform(9, 20))
        bump = int(rng.uniform(4, 11))
        pts = np.array([
            [x_cursor, y],
            [x_cursor + seg // 3, y - bump],
            [x_cursor + 2 * seg // 3, y - bump],
            [x_cursor + seg, y],
        ], dtype=np.int32)
        cv2.polylines(img, [pts], False, colour, thickness, cv2.LINE_AA)
        if rng.random() < 0.4:                      # a dot above or below
            cv2.circle(img, (x_cursor + seg // 2, y - bump - 6), 1, colour, -1)
        if rng.random() < 0.25:                     # an ascender
            cv2.line(img, (x_cursor + seg, y), (x_cursor + seg, y - 20),
                     colour, thickness, cv2.LINE_AA)
        x_cursor += seg + int(rng.uniform(1, 4))


def watermarked_foot(seed: int = 41) -> np.ndarray:
    """The live failure, reconstructed: a clinic watermark over a wound photo.

    A real stock image carrying a clinic domain, a phone number and a line of
    Persian text was processed end to end and produced a full URGENT report.
    The domain and number here are invented placeholders -- reproducing a real
    clinic's mark in a committed test fixture would be putting someone else's
    identity in this repository.

    MUST BE REJECTED, reason `overlay`.
    """
    img, mask = _foot_base(seed)
    cv2.ellipse(img, (410, 420), (96, 74), 0, 0, 360, (95, 115, 190), -1)
    cv2.ellipse(img, (410, 424), (60, 46), 0, 0, 360, (110, 190, 215), -1)
    _texture(img, mask, seed + 3, amount=4.0)

    white = (245, 245, 245)
    # Watermarks are drawn with a drop shadow so they read over any background.
    for dx, dy, col in ((2, 2, (40, 40, 40)), (0, 0, white)):
        cv2.putText(img, "WOUNDI.COM", (232 + dx, 86 + dy),
                    cv2.FONT_HERSHEY_DUPLEX, 1.5, col, 3, cv2.LINE_AA)
        cv2.putText(img, "0912 000 0000", (286 + dx, 132 + dy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.78, col, 2, cv2.LINE_AA)
    _cursive_line(img, 250, 176, 300, seed + 5, white, thickness=2)

    # A small mark beside the wordmark: flat fill, hard edge, non-skin hue.
    cv2.circle(img, (188, 74), 26, (66, 172, 232), -1)
    cv2.circle(img, (188, 74), 26, white, 3)
    cv2.line(img, (188, 60), (188, 88), white, 5)
    cv2.line(img, (174, 74), (202, 74), white, 5)

    return _sensor_noise(img, seed)


def screen_photo(seed: int = 51) -> np.ndarray:
    """A foot photograph re-photographed off a display.

    Three things arrive together when someone points a camera at a screen, and
    all three are drawn here:
      * the display's pixel grid, aliased against the sensor grid -- a periodic
        pattern at a few pixels' period;
      * the low-frequency beat between those two grids, the visible moire
        banding;
      * the bezel: a dark frame around a brighter, slightly rotated panel, with
        a diagonal glare wash across it.

    MUST BE REJECTED, reason `rephotograph`.
    """
    panel, mask = _foot_base(seed)
    cv2.ellipse(panel, (410, 420), (96, 74), 0, 0, 360, (95, 115, 190), -1)
    cv2.ellipse(panel, (410, 424), (60, 46), 0, 0, 360, (110, 190, 215), -1)
    _texture(panel, mask, seed + 3, amount=4.0)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    # Display pixel grid: a 4 px period in each axis, plus the RGB subpixel
    # stripe at a 3 px period which only shows in the colour channels.
    grid = (np.cos(2 * np.pi * xx / 4.0) + np.cos(2 * np.pi * yy / 4.0)) * 5.0
    stripe = np.stack([np.cos(2 * np.pi * (xx + c) / 3.0) * 4.0
                       for c in (0, 1, 2)], axis=2)
    # Moire beat: two close spatial frequencies at a small relative angle.
    beat = np.cos(2 * np.pi * (xx * 0.019 + yy * 0.004)) * \
        np.cos(2 * np.pi * (xx * 0.021 - yy * 0.002)) * 9.0

    lit = panel.astype(np.float32) + grid[:, :, None] + stripe + beat[:, :, None]
    # A screen is emissive and lower-contrast than the scene it shows.
    lit = 26.0 + lit * 0.86
    lit = np.clip(lit, 0, 255).astype(np.uint8)

    # The panel, rotated a few degrees, inside a dark bezel.
    out = np.full((H, W, 3), 22, dtype=np.uint8)
    inner_w, inner_h = int(W * 0.80), int(H * 0.76)
    inner = cv2.resize(lit, (inner_w, inner_h), interpolation=cv2.INTER_LINEAR)
    x0, y0 = (W - inner_w) // 2, (H - inner_h) // 2
    out[y0:y0 + inner_h, x0:x0 + inner_w] = inner
    rot = cv2.getRotationMatrix2D((W / 2, H / 2), 3.0, 1.0)
    out = cv2.warpAffine(out, rot, (W, H), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(22, 22, 22))

    # Glare: a broad diagonal wash off the glass.
    wash = np.clip((xx * 0.55 + yy * 0.45) / float(W) * 1.6 - 0.35, 0, 1)
    out = np.clip(out.astype(np.float32) + wash[:, :, None] * 26.0,
                  0, 255).astype(np.uint8)
    return _sensor_noise(out, seed, amount=2.0)


def distant_foot(seed: int = 61) -> np.ndarray:
    """The foot at arm's length: correctly exposed, sharp, and too far away.

    Passes focus, exposure and resolution; the subject covers roughly a
    twentieth of the frame. MUST BE REJECTED, reason `subject_absent`.
    """
    img = _canvas(seed)
    mask = np.zeros((H, W), dtype=np.uint8)
    cv2.ellipse(mask, (400, 300), (58, 78), 8, 0, 360, 255, -1)
    cv2.ellipse(img, (400, 300), (58, 78), 8, 0, 360, SKIN, -1)
    _texture(img, mask, seed, amount=5.0)
    cv2.ellipse(img, (403, 330), (28, 22), 0, 0, 360, (95, 115, 190), -1)
    return _sensor_noise(img, seed)


FIXTURES = {
    "clean_foot": clean_foot,
    "wet_ulcer": wet_ulcer,
    "watermarked_foot": watermarked_foot,
    "screen_photo": screen_photo,
    "distant_foot": distant_foot,
}


def jpeg_bytes(name: str) -> bytes:
    """The committed fixture's bytes. Tests read this, not the generator."""
    return (FIXTURE_DIR / f"{name}.jpg").read_bytes()


def write_all() -> list[Path]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fn in FIXTURES.items():
        path = FIXTURE_DIR / f"{name}.jpg"
        ok, buf = cv2.imencode(
            ".jpg", fn(), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            raise RuntimeError(f"failed to encode {name}")
        path.write_bytes(buf.tobytes())
        written.append(path)
    return written


if __name__ == "__main__":
    for p in write_all():
        print(p)
