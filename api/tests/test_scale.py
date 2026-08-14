"""Real-world size from a card of known dimensions in the frame.

Everything measured before this was a PERCENTAGE OF THE IMAGED REGION. That
number changes when the camera moves and the wound does not, so comparing two
visits with it compares camera positions. Since serial measurement is the whole
reason to keep measuring at all -- percentage area reduction over four weeks is
the established prognostic indicator in wound care, and "is this necrotic" is
not obtainable from a photograph at all -- the size reference is the thing the
rest depends on.

The failure that matters here is a confident cm² that is wrong. A tilted card
is foreshortened, and area scales with the SQUARE of that error, so the tests
below spend most of their attention on refusing rather than on measuring.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analysis import scale as scale_mod
from app.analysis.pipeline import AnalysisJob, execute


def _card(long_px: float, short_px: float) -> dict:
    return {"bbox": (0, 0, long_px, short_px)}


# --- measuring ---------------------------------------------------------------

@pytest.mark.parametrize("long_px", [120, 260, 520, 1040])
def test_millimetres_per_pixel_tracks_the_card(long_px):
    short_px = long_px / scale_mod.ID1_ASPECT
    s = scale_mod.from_card(_card(long_px, short_px))
    assert s.available, s.reason
    assert s.mm_per_px == pytest.approx(scale_mod.ID1_LONG_MM / long_px, rel=1e-6)


def test_area_converts_to_square_centimetres():
    # 200 px across the long edge of an 85.6 mm card -> 0.428 mm/px.
    s = scale_mod.from_card(_card(200, 200 / scale_mod.ID1_ASPECT))
    # A 100 x 100 px square is 42.8 x 42.8 mm = 18.3 cm².
    assert s.area_cm2(100 * 100) == pytest.approx(18.32, rel=0.01)


def test_orientation_does_not_matter():
    """A card photographed portrait measures the same as one landscape."""
    landscape = scale_mod.from_card(_card(300, 300 / scale_mod.ID1_ASPECT))
    portrait = scale_mod.from_card(_card(300 / scale_mod.ID1_ASPECT, 300))
    assert landscape.mm_per_px == pytest.approx(portrait.mm_per_px, rel=1e-9)


# --- refusing ----------------------------------------------------------------

def test_no_card_means_no_size_and_says_so():
    s = scale_mod.from_card(None)
    assert not s.available
    assert s.area_cm2(1000) is None
    body = s.to_json()
    assert "CANNOT be compared" in body["reason"]


@pytest.mark.parametrize("shortening", [0.20, 0.35, 0.50])
def test_a_tilted_card_is_refused_rather_than_measured(shortening):
    """Foreshortening inflates every area by the SQUARE of the length error, so
    a confident cm² from a tilted card is worse than no cm² at all."""
    long_px = 300 * (1 - shortening)
    s = scale_mod.from_card(_card(long_px, 300 / scale_mod.ID1_ASPECT))
    assert not s.available
    assert "square to the camera" in s.reason


def test_a_tiny_card_is_refused():
    s = scale_mod.from_card(_card(40, 40 / scale_mod.ID1_ASPECT))
    assert not s.available
    assert "too small" in s.reason


def test_a_slight_tilt_measures_but_warns():
    long_px = 300 * (1 - scale_mod.MAX_ASPECT_ERROR * 0.75)
    s = scale_mod.from_card(_card(long_px, 300 / scale_mod.ID1_ASPECT))
    assert s.available
    assert s.notes and "overstated" in s.notes[0]


def test_a_non_card_rectangle_is_refused():
    """A square sticky note is not an ID-1 card and must not be used as one."""
    assert not scale_mod.from_card(_card(200, 200)).available


# --- end to end --------------------------------------------------------------

def _scene(with_card: bool, card_px=(260, 164)):
    W, H = 1400, 1000
    rng = np.random.default_rng(4)
    img = np.full((H, W, 3), (105, 108, 112), np.uint8)
    cv2.ellipse(img, (820, 500), (300, 340), 0, 0, 360, (150, 175, 205), -1)
    cv2.circle(img, (820, 500), 90, (45, 50, 66), -1)
    if with_card:
        w, h = card_px
        img[420:420 + h, 90:90 + w] = 200
    img = np.clip(img + rng.normal(0, 5, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                               render_overlay=False))


def test_areas_are_reported_in_cm2_when_a_card_is_present():
    out = _scene(True)
    assert out.result is not None
    m = out.result.features["measurement"]
    assert m["scale"]["available"] is True
    assert m["comparable_between_visits"] is True
    dark = m["areas"]["dark_area_pct"]
    # A 90 px radius disc at ~0.33 mm/px is roughly 27 cm².
    assert dark["cm2"] == pytest.approx(27.5, rel=0.15)
    assert dark["percent_of_region"] > 0


def test_without_a_card_percentages_are_marked_not_comparable():
    """The dangerous version of this feature reports a percentage that looks
    like a measurement and silently is not one."""
    out = _scene(False)
    assert out.result is not None
    m = out.result.features["measurement"]
    assert m["scale"]["available"] is False
    assert m["comparable_between_visits"] is False
    assert "Do NOT compare them with another visit" in m["caveat"]
    assert "cm2" not in m["areas"]["dark_area_pct"]


def test_size_is_a_surface_measurement_and_says_so():
    out = _scene(True)
    caveat = out.result.features["measurement"]["caveat"]
    assert "not of depth or volume" in caveat
