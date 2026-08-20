"""Pre-analysis input gate. Decides whether a frame is a clinical photograph
at all, BEFORE anything measures it.

A live run put a stock image carrying a clinic watermark -- a domain, a phone
number and a line of Persian text -- through the whole pipeline and got back a
full URGENT report at 0.78 confidence. Every downstream layer behaved
correctly. Nothing had asked the first question: is this a photograph of this
patient's foot, taken now, by the person holding the phone?

Three questions are asked here, and a frame that fails any of them is REJECTED
-- not graded low, not flagged, not discounted. A rejection carries a reason
and never reaches a backend, an overlay renderer or a triage grade.

  overlay          text or a graphic mark composited onto the frame. A frame
                   carrying a watermark is somebody's stock photograph, and a
                   report about it is a report about a stranger.
  rephotograph     a photograph of a screen. What is measured then is the
                   display's rendering of an image, at the display's colour,
                   contrast and resolution -- and every measurement in this
                   pipeline is a colour or an area measurement.
  subject_absent   the subject does not occupy enough of the frame for what is
                   measured from it to mean anything.

WHERE THE NUMBERS COME FROM. Every threshold here was measured against the
fixtures in tests/fixtures, and those are DRAWINGS -- synthetic frames built
from OpenCV primitives, not clinical photographs. What the fixtures establish
is an ordering with a wide gap in the middle, and each constant is placed in
its gap rather than fitted to a distribution. Where a constant is a choice
inside a range rather than a boundary the data drew, its comment says so.
None of this is validated against real clinical capture, and none of it should
be described as if it were.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import cv2
import numpy as np

from ..config import settings
from . import cv_utils

# Everything geometric is measured at this working size, so a threshold in
# pixels means the same thing for a 900 px phone capture and a 4000 px one.
_WORK_DIM = 720


class RejectionReason(StrEnum):
    OVERLAY = "overlay"
    REPHOTOGRAPH = "rephotograph"
    SUBJECT_ABSENT = "subject_absent"


@dataclass(slots=True)
class InputRejection:
    """A refusal to analyse, with the reason and the measurement behind it.

    Deliberately not a grade and not a quality score. There is no number on it
    that a caller could mistake for a clinical finding, and no path from it to
    a triage label.
    """

    reason: RejectionReason
    detail: str                              # what was found, for the clinician
    hint: str                                # what to do about it
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "rejected": True,
            "reason": str(self.reason),
            "detail": self.detail,
            "hint": self.hint,
            "evidence": self.evidence,
        }


def _work_image(bgr: np.ndarray) -> np.ndarray:
    scale = min(1.0, _WORK_DIM / float(max(bgr.shape[:2])))
    if scale >= 1.0:
        return bgr
    return cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


# --- 1. text and graphic overlays -------------------------------------------
#
# THE PRIORITY. This is where the live failure was.
#
# The hard part is not finding bright marks on skin -- it is not rejecting a
# glistening ulcer. Wet tissue throws specular highlights: small, bright,
# high-contrast blobs, at exactly the size range display text occupies, and a
# row of them can sit on a common baseline by chance. Rejecting a real wound
# because it is wet would be a worse failure than the one this gate exists to
# fix, because the wound that glistens is the wound that needs seeing.
#
# Two properties separate writing from reflections, and both are properties of
# what the things ARE rather than of how bright they happen to be:
#
#   letterforms differ from each other      A row of glyphs contains an O, an I
#                                           and a full stop, which fill their
#                                           bounding boxes very differently. A
#                                           row of specular blobs is a row of
#                                           convex ellipses, and every convex
#                                           ellipse fills about pi/4 of its box
#                                           whatever its size. Measured as the
#                                           coefficient of variation of the
#                                           ink-to-box ratio along the line.
#
#   letterforms have counters and concavities   Writing systems put holes in
#                                           their glyphs and bends in their
#                                           strokes. A specular highlight is
#                                           convex, because it is the image of
#                                           a light source in a curved wet
#                                           surface. Measured as the lowest
#                                           region-to-convex-hull ratio on the
#                                           line: at least one glyph must be
#                                           genuinely non-convex.
#
# Measured on the fixtures (tests/fixtures, and the adversarial rows of glints
# used to calibrate this and described in the commit):
#
#                                fill-ratio CV      min solidity
#   watermark wordmark line          0.351             0.122
#   watermark phone-number line      0.230             0.186
#   watermark logo + script line     0.668             0.098
#   glints, evenly sized in a row    0.021             0.953
#   glints, hard-edged in a row      0.022             0.957
#   glints, varied sizes in a row    0.073             0.811
#   glints, varied + jittered        0.042             0.881
#
# Both gaps are wide -- 0.073 to 0.230, and 0.186 to 0.811 -- and the two
# measurements are independent of each other, so BOTH are required. Requiring
# both costs sensitivity to overlays made of very few, very uniform glyphs,
# which is the trade this gate should be making: a missed watermark is caught
# by a human reading the report, a rejected ulcer is not caught by anyone.

_MIN_GLYPHS_PER_LINE = 4          # "WWW" is not enough to call a frame stock
_MIN_FILL_CV = 0.15               # in the gap 0.073 .. 0.230
_MAX_MIN_SOLIDITY = 0.50          # in the gap 0.186 .. 0.811


def _glyph_candidates(gray: np.ndarray) -> list[dict]:
    """Mark-shaped regions: MSER, filtered to things the size and shape of
    glyphs. Deliberately permissive -- the decision is made per LINE, not per
    candidate, and a filter tight enough to admit only letters would also
    exclude whichever script this frame happens to carry."""
    h, w = gray.shape[:2]
    area = float(h * w)
    mser = cv2.MSER_create(
        delta=5,
        min_area=max(20, int(area * 0.00004)),
        max_area=int(area * 0.02),
    )
    regions, boxes = mser.detectRegions(gray)

    cands: list[dict] = []
    for pts, (bx, by, bw, bh) in zip(regions, boxes):
        if bh < 7 or bh > h * 0.30:
            continue
        if not 0.06 <= bw / float(bh) <= 3.5:
            continue
        fill = len(pts) / float(bw * bh)
        if not 0.10 <= fill <= 0.92:
            continue

        local = pts - np.array([bx, by])
        stamp = np.zeros((bh + 4, bw + 4), np.uint8)
        stamp[local[:, 1] + 2, local[:, 0] + 2] = 255
        contours, _ = cv2.findContours(
            stamp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        filled = sum(cv2.contourArea(c) for c in contours)
        hull = cv2.contourArea(cv2.convexHull(np.vstack(contours)))
        solidity = (filled / hull) if hull > 0 else 1.0

        cands.append({"x": int(bx), "y": int(by), "w": int(bw), "h": int(bh),
                      "fill": float(fill), "solidity": float(solidity)})

    # MSER returns nested versions of the same blob; keep the largest of each.
    cands.sort(key=lambda c: -c["w"] * c["h"])
    kept: list[dict] = []
    for c in cands:
        if not any(_iou(c, k) > 0.3 for k in kept):
            kept.append(c)
    return kept


def _iou(a: dict, b: dict) -> float:
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union else 0.0


def _text_lines(cands: list[dict]) -> list[dict]:
    """Group candidates into runs that share a baseline, a height and a spacing.

    Grouping first and deciding second is what lets the decision use properties
    of the LINE -- how much its members differ from one another -- which is
    where writing and reflections actually part company.
    """
    ordered = sorted(cands, key=lambda c: c["x"])
    used = [False] * len(ordered)
    lines: list[dict] = []

    for i, first in enumerate(ordered):
        if used[i]:
            continue
        run = [first]
        used[i] = True
        for j in range(i + 1, len(ordered)):
            if used[j]:
                continue
            nxt, last = ordered[j], run[-1]
            tallest = max(last["h"], nxt["h"])
            if min(last["h"], nxt["h"]) / tallest < 0.45:
                continue                                  # heights disagree
            centre_a = last["y"] + last["h"] / 2
            centre_b = nxt["y"] + nxt["h"] / 2
            if abs(centre_a - centre_b) > 0.45 * tallest:
                continue                                  # off the baseline
            gap = nxt["x"] - (last["x"] + last["w"])
            if gap < -0.4 * tallest or gap > 1.3 * tallest:
                continue                                  # not the same word
            run.append(nxt)
            used[j] = True

        if len(run) < _MIN_GLYPHS_PER_LINE:
            continue
        fills = np.array([g["fill"] for g in run], dtype=float)
        sols = np.array([g["solidity"] for g in run], dtype=float)
        x0 = min(g["x"] for g in run)
        y0 = min(g["y"] for g in run)
        x1 = max(g["x"] + g["w"] for g in run)
        y1 = max(g["y"] + g["h"] for g in run)
        lines.append({
            "glyphs": len(run),
            "fill_cv": float(fills.std() / fills.mean()) if fills.mean() else 0.0,
            "min_solidity": float(sols.min()),
            "height_px": float(np.mean([g["h"] for g in run])),
            "at": [int(x0), int(y0)],
            "bbox": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
        })
    return lines


def _reference_card_region(bgr: np.ndarray,
                           work_shape: tuple[int, int]) -> list[int] | None:
    """The reference card's bounding box, in WORK-image coordinates.

    Found with exactly the calls `pipeline.execute` will make later --
    `estimate_subject_mask` on this image, then `find_reference_card` with that
    mask -- so the card the gate exempts is the same card calibration will use.
    Both are deterministic on the same input, so the two cannot disagree.

    The card descriptor also carries a `mask`, and it is the WRONG handle here.
    That mask is the eroded NEUTRAL region, and printed text is not neutral --
    the ink is precisely what the mask leaves out, so testing containment
    against it would exempt nothing. The bounding box is what encloses a card
    and everything printed on it.
    """
    try:
        subject_mask, _fraction = cv_utils.estimate_subject_mask(bgr)
        card = cv_utils.find_reference_card(bgr, subject_mask)
    except Exception:                  # pragma: no cover - never block on this
        return None
    if card is None:
        return None

    x, y, w, h = card["bbox"]
    scale = work_shape[1] / float(bgr.shape[1]) if bgr.shape[1] else 1.0
    return [int(x * scale), int(y * scale),
            int(w * scale), int(h * scale)]


def _inside(line: dict, region: list[int]) -> bool:
    """Wholly within, not merely overlapping.

    A watermark that straddles the card's edge is not printing on the card, and
    treating it as such would hand anyone a way to place a mark half-on a card
    and have it ignored.
    """
    lx, ly, lw, lh = line["bbox"]
    rx, ry, rw, rh = region
    return (lx >= rx and ly >= ry
            and lx + lw <= rx + rw and ly + lh <= ry + rh)


def detect_overlay(bgr: np.ndarray) -> InputRejection | None:
    work = _work_image(bgr)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    lines = _text_lines(_glyph_candidates(gray))

    written = [
        ln for ln in lines
        if ln["fill_cv"] >= settings.gate_overlay_min_fill_cv
        and ln["min_solidity"] <= settings.gate_overlay_max_min_solidity
    ]
    if not written:
        return None

    # -- printing on the reference card is not a watermark --------------------
    # The capture instructions ASK for a card in the frame, and real cards
    # carry printed markings: a size, a grey value, a manufacturer's name. A
    # gate that refuses the workflow the product recommends is a gate that gets
    # switched off, so text lying wholly within a detected card is exempt.
    #
    # The exemption is bounded by the card detector's own limits rather than by
    # anything decided here: a card may cover at most
    # cv_utils.REFERENCE_MAX_AREA_FRAC of the frame, must be neutral, flat and
    # beside the subject rather than on it. A watermark that happens to fall
    # entirely inside that region WOULD be exempted, and that is the price of
    # not refusing every carded capture. Anything outside it still rejects.
    #
    # Only paid for when there is something to exempt, so an ordinary capture
    # never runs the card detector twice.
    exempted = 0
    card_region = _reference_card_region(bgr, work.shape[:2])
    if card_region is not None:
        kept = [ln for ln in written if not _inside(ln, card_region)]
        exempted = len(written) - len(kept)
        written = kept
        if not written:
            return None

    written.sort(key=lambda ln: -ln["glyphs"])
    return InputRejection(
        reason=RejectionReason.OVERLAY,
        detail=(
            "This image carries text or a graphic mark printed over the "
            f"photograph ({len(written)} line(s) of lettering, the longest "
            f"{written[0]['glyphs']} characters). An image with a watermark, "
            "a logo or a caption on it is not a capture of this patient, and "
            "QADAM will not report on it."
        ),
        hint=(
            "Photograph the foot directly with the device camera. Do not "
            "upload a picture taken from a website, a messaging app, a "
            "textbook or a previous report."
        ),
        evidence={"text_lines": written[:4], "lines_found": len(lines),
                  "reference_card": card_region,
                  "lines_on_the_card": exempted},
    )


# --- 2. photographs of a screen ---------------------------------------------
#
# Two independent signals, because they fail in opposite conditions: the panel
# geometry needs the bezel to be in shot, and the lattice signal needs the
# display's own pixel grid to have survived to the file.
#
#   panel geometry   A display in shot is a bright, straight-sided quadrilateral
#                    inset in a much darker surround, because the panel is
#                    emissive and the bezel and the room are not.
#
#   lattice peak     A display has a physical pixel grid. Photograph it and that
#                    grid beats against the sensor's, and both the grid and the
#                    beat are periodic. Periodic means an ISOLATED spike in the
#                    spatial-frequency spectrum, which a natural scene -- broadly
#                    1/f, smooth -- does not have. Ring-normalised so a 1/f
#                    falloff cannot pose as a peak, then required to stand above
#                    its own neighbourhood too: a straight shadow crease puts a
#                    RIDGE through the spectrum, and a ridge is not a lattice.
#
# Measured on the fixtures, as a MAD z-score:
#
#   screen_photo                         8.63   panel: 61% of frame, +98 levels
#   foot_shadow_only (two hard creases)  3.46   no panel
#   every other fixture and sample       2.5 .. 2.9   no panel
#
# The strong threshold sits in the gap at 6.0. The panel test alone does not
# reject, because a sheet of paper, a drape or a phone lying on the couch is
# also a bright rectangle; it must be corroborated by a weaker lattice reading,
# which is set at 4.5 -- above the 3.46 the hardest negative reached, below the
# 8.63 the positive reached. Both of those are CHOICES inside their gaps, not
# boundaries the data drew.

_SPECTRUM_CROP = 512


def _lattice_peak(bgr: np.ndarray) -> float:
    """MAD z-score of the most isolated off-axis peak in the spectrum.

    Computed at NATIVE resolution on a centre crop. Downsampling is precisely
    what destroys a pixel lattice, so the usual work-size normalisation would
    remove the thing being measured.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    n = int(min(_SPECTRUM_CROP, h, w))
    if n < 64:
        return 0.0
    gray = gray[(h - n) // 2:(h - n) // 2 + n, (w - n) // 2:(w - n) // 2 + n]

    window = np.outer(np.hanning(n), np.hanning(n))
    spectrum = np.log1p(
        np.fft.fftshift(np.abs(np.fft.fft2((gray - gray.mean()) * window))))

    centre = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    radius = np.sqrt((yy - centre) ** 2 + (xx - centre) ** 2) / float(centre)
    band = (radius > 0.06) & (radius < 0.95)

    # Ring normalisation: compare each bin with the median of its own radius.
    ring = np.zeros_like(spectrum)
    bucket = np.clip((radius * 60).astype(int), 0, 60)
    for k in range(61):
        sel = bucket == k
        if sel.sum() > 8:
            ring[sel] = np.median(spectrum[sel])
    resid = np.where(band, spectrum - ring, 0.0).astype(np.float32)

    # Ridge suppression. A spike survives no opening; a ridge survives an
    # opening by a line aligned with it. Subtract the strongest line-opening
    # over eight orientations and linear structure cancels.
    ridges = np.zeros_like(resid)
    for angle in range(0, 180, 22):
        element = np.zeros((11, 11), np.uint8)
        cv2.line(element, (0, 5), (10, 5), 1, 1)
        rot = cv2.getRotationMatrix2D((5, 5), float(angle), 1.0)
        element = (cv2.warpAffine(element.astype(np.float32), rot, (11, 11))
                   > 0.3).astype(np.uint8)
        if element.sum() < 3:
            continue
        ridges = np.maximum(
            ridges, cv2.morphologyEx(resid, cv2.MORPH_OPEN, element))
    isolated = resid - ridges

    # The axis cross carries JPEG blocking and the frame's own edges.
    axis = (np.abs(yy - centre) < 3) | (np.abs(xx - centre) < 3)
    sel = band & ~axis
    if sel.sum() < 100:
        return 0.0
    spread = float(np.median(np.abs(isolated[sel]))) or 1e-6
    return float(isolated[sel].max() / (1.4826 * spread))


def _screen_panel(bgr: np.ndarray) -> dict | None:
    """A bright, four-cornered, straight-sided region on a much darker ground."""
    h, w = bgr.shape[:2]
    frame_area = float(h * w)
    gray = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    best: dict | None = None
    for lo, hi in ((40, 120), (30, 90), (60, 160)):
        edges = cv2.dilate(cv2.Canny(gray, lo, hi), np.ones((3, 3), np.uint8), 1)
        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 0.20 * frame_area or area > 0.95 * frame_area:
                continue
            approx = cv2.approxPolyDP(
                contour, 0.02 * cv2.arcLength(contour, True), True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            rect = cv2.minAreaRect(approx)
            rect_area = rect[1][0] * rect[1][1]
            if rect_area <= 0 or area / rect_area < 0.88:
                continue

            filled = np.zeros((h, w), np.uint8)
            cv2.drawContours(filled, [approx], -1, 255, -1)
            inner = cv2.erode(filled, np.ones((9, 9), np.uint8), 1)
            outer = cv2.bitwise_not(
                cv2.dilate(filled, np.ones((9, 9), np.uint8), 1))
            if inner.sum() == 0 or outer.sum() == 0:
                continue
            contrast = float(np.median(gray[inner > 0])) - \
                float(np.median(gray[outer > 0]))
            if contrast < settings.gate_screen_panel_contrast:
                continue
            found = {"share_of_frame": round(area / frame_area, 3),
                     "rectangularity": round(area / rect_area, 3),
                     "panel_minus_surround": round(contrast, 1)}
            if best is None or contrast > best["panel_minus_surround"]:
                best = found
    return best


def detect_rephotograph(bgr: np.ndarray) -> InputRejection | None:
    peak = _lattice_peak(bgr)
    panel = _screen_panel(bgr)

    strong = peak >= settings.gate_lattice_peak_z
    corroborated = panel is not None and peak >= settings.gate_lattice_weak_z
    if not (strong or corroborated):
        return None

    seen = ("the display's pixel grid is visible in the frame" if strong
            else "a lit screen is visible in the frame")
    return InputRejection(
        reason=RejectionReason.REPHOTOGRAPH,
        detail=(
            f"This looks like a photograph of a screen — {seen}. What such an "
            "image records is a display's rendering of a picture, at that "
            "display's colour, contrast and resolution. Every measurement "
            "QADAM makes is a colour or an area, so it would be measuring the "
            "screen rather than the foot."
        ),
        hint=(
            "Photograph the foot itself with the device camera, rather than "
            "photographing another screen showing it."
        ),
        evidence={"lattice_peak_z": round(peak, 2),
                  "threshold": settings.gate_lattice_peak_z,
                  "screen_panel": panel},
    )


# --- 3. subject presence -----------------------------------------------------
#
# The check that was there measured `cv_utils.estimate_subject_mask` against
# 0.08 -- and that function has two escape hatches, a close-up branch and a
# degenerate-mask fallback, which BOTH return 1.0. It reports maximum subject
# presence exactly when it has failed to find a subject, so the old check was
# not a weak filter. Below a certain distance it INVERTED. Measured, on the
# same foot rendered at falling scales:
#
#   presence   old measure   outcome
#     0.109       0.109      urgent, 6.1% breakdown -- correct
#     0.076       0.076      rejected, subject_present
#     0.049       0.049      rejected, subject_present
#     0.000       1.000      REVIEW GRADE, 0.5% breakdown -- 98% wrong, reported
#     0.000       1.000      refused later by the not-skin check
#
# A frame FURTHER past the boundary than the ones being rejected came back with
# a grade, because the subject had become small enough that the border-colour
# model saw only backdrop, the close-up branch fired, and the whole frame was
# declared to be the foot.
#
# So this measures presence itself, without either escape hatch, and asks what
# a uniform frame is made of rather than assuming it is a close-up.

def measure_subject_presence(bgr: np.ndarray) -> tuple[float, str]:
    """Share of the frame the subject occupies, and how that was decided."""
    work = _work_image(bgr)
    h, w = work.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(work, (5, 5), 0),
                       cv2.COLOR_BGR2LAB).astype(np.float32)

    band_y, band_x = max(2, int(h * 0.08)), max(2, int(w * 0.08))
    border = np.concatenate([
        lab[:band_y].reshape(-1, 3), lab[-band_y:].reshape(-1, 3),
        lab[:, :band_x].reshape(-1, 3), lab[:, -band_x:].reshape(-1, 3),
    ])
    distance = np.linalg.norm(lab - np.median(border, axis=0), axis=2)

    if float(np.percentile(distance, 95)) < 14.0:
        # Nothing in frame stands out from its border. That is EITHER a true
        # close-up, where the border is itself the subject, OR a frame with no
        # subject in it. The old code assumed the first. Ask instead.
        _L, a, b = cv_utils.lab_planes(work)
        whole = np.full((h, w), 255, np.uint8)
        is_skin, _stats = cv_utils.looks_like_skin(a, b, whole)
        return (1.0 if is_skin else 0.0), "uniform-frame"

    dmax = float(distance.max()) or 1.0
    _t, binary = cv2.threshold(
        np.clip(distance / dmax * 255.0, 0, 255).astype(np.uint8),
        0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = max(3, (min(h, w) // 60) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    count, labels, stats, _c = cv2.connectedComponentsWithStats(
        binary, connectivity=8)
    if count <= 1:
        return 0.0, "no-region"
    largest = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
    return float((labels == largest).mean()), "largest-region"


def check_subject_presence(bgr: np.ndarray) -> InputRejection | None:
    presence, how = measure_subject_presence(bgr)
    if presence >= settings.gate_min_subject_presence:
        return None
    return InputRejection(
        reason=RejectionReason.SUBJECT_ABSENT,
        detail=(
            f"The area being assessed fills {presence * 100:.0f}% of this "
            "frame. Below the threshold the foot cannot be reliably separated "
            "from the background, and everything QADAM reports is a "
            "proportion OF that separated region — so the percentages would "
            "be percentages of the wrong area."
        ),
        hint=(
            "Move closer, or crop to the foot, so the area being assessed "
            "fills roughly half the frame on a plain background."
        ),
        evidence={"subject_presence": round(presence, 3),
                  "threshold": settings.gate_min_subject_presence,
                  "measured_by": how},
    )


# --- the gate ----------------------------------------------------------------

def check_provenance(bgr: np.ndarray) -> InputRejection | None:
    """Is this file a photograph taken here, of this patient?

    Runs BEFORE the quality gate. Both questions are answerable on a frame the
    quality gate would condemn -- a watermark is a watermark whether or not the
    exposure is good -- and a stock photograph should be refused for being a
    stock photograph, not sent back for a re-take it can never pass.
    """
    return detect_overlay(bgr) or detect_rephotograph(bgr)


def check_framing(bgr: np.ndarray) -> InputRejection | None:
    """Is enough of the subject in frame for a measurement to mean anything?

    Runs AFTER the quality gate, and the ordering is load-bearing. An
    underexposed frame reads as having no subject in it, because there is not
    enough light to separate anything from anything -- the `quality_dark`
    sample measures 0.000 presence. Told "move closer", a user re-takes the
    same dark photograph from closer up. Told "use more light", they fix it.
    The quality gate must get first refusal on the frames it can explain.
    """
    return check_subject_presence(bgr)
