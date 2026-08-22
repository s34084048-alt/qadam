"""Shared image primitives used by the quality gate and the classical backend.

All measurements are made INSIDE the detected subject region, so a busy or
badly lit background does not drive the result.
"""

from __future__ import annotations

import cv2
import numpy as np

MAX_WORK_DIM = 720


def decode_image(data: bytes) -> np.ndarray | None:
    """Decode to BGR. Returns None if the bytes are not a readable image."""
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    return img


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("failed to encode overlay")
    return buf.tobytes()


def work_scale(img: np.ndarray) -> float:
    h, w = img.shape[:2]
    longest = max(h, w)
    return min(1.0, MAX_WORK_DIM / float(longest)) if longest else 1.0


def lab_planes(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """L (0..255), a and b re-centred on 0 (negative = green/blue)."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0].astype(np.float32)
    a = lab[:, :, 1].astype(np.float32) - 128.0
    b = lab[:, :, 2].astype(np.float32) - 128.0
    return L, a, b


def estimate_subject_mask(bgr: np.ndarray) -> tuple[np.ndarray, float]:
    """Segment the photographed subject from the background.

    Models the background from the image border, measures LAB distance from
    that model, and keeps the largest coherent region. A true close-up (subject
    fills the frame, so border == subject) is detected and the whole frame is
    treated as the subject rather than producing noise.

    Returns (uint8 mask 0/255 at full resolution, fraction of frame covered).
    """
    h, w = bgr.shape[:2]
    scale = work_scale(bgr)
    small = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) \
        if scale < 1.0 else bgr
    sh, sw = small.shape[:2]

    blur = cv2.GaussianBlur(small, (5, 5), 0)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB).astype(np.float32)

    band_y = max(2, int(sh * 0.08))
    band_x = max(2, int(sw * 0.08))
    border = np.concatenate(
        [
            lab[:band_y, :, :].reshape(-1, 3),
            lab[-band_y:, :, :].reshape(-1, 3),
            lab[:, :band_x, :].reshape(-1, 3),
            lab[:, -band_x:, :].reshape(-1, 3),
        ]
    )
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(lab - bg, axis=2)

    # Close-up: nothing in frame is far from the border colour.
    if float(np.percentile(dist, 95)) < 14.0:
        mask_full = np.full((h, w), 255, dtype=np.uint8)
        return mask_full, 1.0

    dmax = float(dist.max()) or 1.0
    dist_u8 = np.clip(dist / dmax * 255.0, 0, 255).astype(np.uint8)
    _, th = cv2.threshold(dist_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    k = max(3, (min(sh, sw) // 60) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=1)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(th, connectivity=8)
    if n <= 1:
        mask_small = np.full((sh, sw), 255, dtype=np.uint8)
    else:
        areas = stats[1:, cv2.CC_STAT_AREA]
        largest = int(np.argmax(areas)) + 1
        mask_small = np.where(labels == largest, 255, 0).astype(np.uint8)
        # Fill interior holes so a dark wound bed stays part of the subject.
        contours, _ = cv2.findContours(
            mask_small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours:
            mask_small = np.zeros_like(mask_small)
            cv2.drawContours(mask_small, contours, -1, 255, thickness=cv2.FILLED)

    mask_full = cv2.resize(mask_small, (w, h), interpolation=cv2.INTER_NEAREST) \
        if scale < 1.0 else mask_small
    fraction = float((mask_full > 0).mean())

    # A degenerate segmentation is worse than none: fall back to the frame.
    if fraction < 0.02:
        return np.full((h, w), 255, dtype=np.uint8), 1.0
    return mask_full, fraction


def masked_stats(values: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    sel = values[mask > 0]
    if sel.size == 0:
        return {"mean": 0.0, "std": 0.0, "median": 0.0, "p90": 0.0}
    return {
        "mean": float(sel.mean()),
        "std": float(sel.std()),
        "median": float(np.median(sel)),
        "p90": float(np.percentile(sel, 90)),
    }


FOCUS_NORM_SHORT_SIDE = 480


def focus_variance(bgr: np.ndarray, mask: np.ndarray) -> float:
    """Variance of the Laplacian inside the subject, at a fixed working size.

    Laplacian variance is strongly scale-dependent: the SAME scene measured at
    4032 px and at 800 px differs by roughly two orders of magnitude. Applied to
    the native resolution, one fixed threshold therefore rejects sharp
    phone-camera photos as blurred while passing soft low-resolution ones.
    Normalising the short side first makes the threshold mean the same thing on
    every device. Genuinely blurred images stay far below it either way.
    """
    h, w = bgr.shape[:2]
    scale = min(1.0, FOCUS_NORM_SHORT_SIDE / max(1, min(h, w)))
    if scale < 1.0:
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, (bgr.shape[1], bgr.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    sel = lap[mask > 0]
    if sel.size < 100:
        sel = lap.reshape(-1)
    return float(sel.var())


def exposure_mean(bgr: np.ndarray, mask: np.ndarray) -> float:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sel = gray[mask > 0]
    if sel.size == 0:
        sel = gray.reshape(-1)
    return float(sel.mean())


def drop_thin_structures(mask: np.ndarray, min_radius: float) -> np.ndarray:
    """Keep only regions that have WIDTH, measured as the largest circle that
    fits inside them.

    A shadow in a skin crease, the dark line under a nail, and the gap between
    two fingers are all long and thin. A patch of non-viable tissue is a blob.
    Area alone cannot tell them apart -- a 2 px crease across a whole hand has
    the same area as a small round lesion -- but the inscribed radius can.
    """
    if min_radius <= 0 or not mask.any():
        return mask
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    n, labels, _stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros_like(mask)
    for label in range(1, n):
        component = labels == label
        if distance[component].max() >= min_radius:
            keep[component] = 255
    return keep


# --- a bounded bed, or diffuse colour -----------------------------------------
#
# The third axis, and the one a field capture asked for directly.
#
# This module measures three things: red, yellow, dark. A granulating ulcer bed
# is RED -- not yellow, not dark -- so by construction it lands in `erythema`
# and is reported as "surface redness", the same bucket as a flush, a stain of
# pressure hyperaemia, or the pink of a warm foot. On a real photograph of an
# open plantar ulcer the wound came back as `erythema 10.7%` inside a bounding
# box far larger than the wound, and nothing on the page distinguished it from
# scattered colour variation.
#
# What differs is the same thing that separates slough from callus, one axis
# over: a bed lies IN a defect, so it has a real margin and a moist surface.
# Diffuse redness fades into the skin around it and is dry.
#
# WHAT THIS DOES NOT DO. It does not raise the grade, and it cannot: erythema
# is capped at REVIEW in `evidence._erythema` because redness in a photograph
# is a colour, set as much by the lamp and the white balance as by the skin --
# a bounded red area is still a colour, and none of the tests below establishes
# warmth, infection or depth. "bed_like" is a statement about a BOUNDARY, not
# about tissue viability, and the ceiling is unchanged and asserted by test.

RED_BED_MIN_EDGE = 25.0         # a wound margin is a real step, as for slough
RED_BED_MIN_SPECULAR = 0.012    # a bed is moist; intact red skin is not


def red_region_character(bgr: np.ndarray, region: np.ndarray) -> dict:
    """A bounded, moist bed, or diffuse surface colour?

    Returns the measurements and a verdict of "bed_like", "diffuse_like" or
    "indeterminate". It never names a diagnosis: granulation tissue, a healing
    bed and an abraded surface are all "bed_like", and separating THOSE needs
    a clinician's eyes and hands.
    """
    # Fill interior holes first, for the reason `yellow_region_character`
    # documents: a specular highlight is near-white and therefore not red, so
    # the a* threshold punches every wet spot OUT of the region before it gets
    # here -- and moisture is exactly what is being measured. A wetter bed
    # would otherwise score as drier.
    region = region.copy()
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        filled = np.zeros_like(region)
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
        region = filled

    sel = region > 0
    if sel.sum() < 200:
        return {"verdict": "indeterminate",
                "reason": "region too small to characterise"}

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    band = (cv2.dilate(region, kernel, 2) > 0) & ~(cv2.erode(region, kernel, 2) > 0)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge = float(np.sqrt(gx * gx + gy * gy)[band].mean()) if band.sum() > 50 else 0.0

    values = gray[sel]
    ceiling = float(np.percentile(values, 50)) + 45.0
    specular = float((values >= ceiling).mean())

    defined_edge = edge >= RED_BED_MIN_EDGE
    wet = specular >= RED_BED_MIN_SPECULAR
    if defined_edge and wet:
        verdict = "bed_like"
    elif not defined_edge and not wet:
        verdict = "diffuse_like"
    else:
        verdict = "indeterminate"

    return {
        "verdict": verdict,
        "edge_gradient": round(edge, 2),
        "specular_fraction": round(specular, 4),
        "thresholds": {"edge_min_for_bed": RED_BED_MIN_EDGE,
                       "specular_min_for_bed": RED_BED_MIN_SPECULAR},
        "meaning": {
            "bed_like": "A defined margin and a moist surface — the redness "
                        "is a BOUNDED AREA rather than scattered colour. It "
                        "says nothing about depth, viability or infection, "
                        "and it does not raise the grade.",
            "diffuse_like": "No margin at skin level and a dry surface — "
                            "colour spread across the skin rather than a "
                            "bounded area. This is NOT reassurance: "
                            "spreading erythema is itself a red flag the "
                            "clinician asks about, and a photograph cannot "
                            "tell whether it is spreading.",
            "indeterminate": "The two measurements disagree.",
        }[verdict],
    }


def drop_backdrop_regions(
    feature: np.ndarray, a: np.ndarray, b: np.ndarray, subject: np.ndarray,
) -> tuple[np.ndarray, list[dict]]:
    """Drop feature regions that are the BACKDROP, not the patient.

    THE FIELD FAILURE THIS PINS
    ---------------------------
    QADAM tells the user to photograph the foot on a blue or green cloth --
    that advice is in `_widen_if_the_segmentation_split_skin` and in the
    capture guidance, and it is good advice. Then, on a close-up where the
    foot ran off the frame edges, the border-colour model in
    `estimate_subject_mask` had a border made mostly of SKIN, the wideners
    correctly fell back to the whole frame, and the recommended blue cloth was
    scored as 33% "dark area" and as "tissue breakdown". A red POSSIBLE WOUND
    box was drawn on the cloth.

    THE TWO GUARDS, AND WHY EACH IS NEEDED
    --------------------------------------
    A wound bed, an eschar and a bruise are not skin-coloured either, so "not
    skin" ALONE would delete the finding this module exists to report. Two
    conditions narrow it to the backdrop:

    1. THE REGION TOUCHES THE IMAGE BORDER. A backdrop reaches the frame edge;
       a lesion on a foot that is fully in frame does not. This is what keeps
       an interior eschar safe -- it is the same protection
       `estimate_subject_mask` gives by filling interior holes.

    2. THE REST OF THE SUBJECT READS AS SKIN. This is the fluorescent-light
       guard, and it matters more than it looks. Light skin under a cool tube
       measures a* and b* NEGATIVE (see `looks_like_skin`), so under that lamp
       a real foot's own regions could satisfy guard 1 and the skin test both.
       But under that lamp NOTHING in frame reads as skin -- so this function
       disables itself entirely rather than trimming a real foot. It only acts
       where the image demonstrably contains skin AND something that is not.

    Nothing is deleted silently: every dropped region is returned so the caller
    can report it. Returns `(mask, dropped)`.
    """
    dropped: list[dict] = []
    if not feature.any():
        return feature, dropped

    # GUARD 2, evaluated once. The reference is the subject MINUS the feature:
    # including the feature would let a large backdrop region drag the very
    # test that is meant to exclude it.
    rest = (subject & (feature == 0)).astype(np.uint8) * 255
    if (rest > 0).sum() < 500:
        return feature, dropped
    rest_is_skin, _ = looks_like_skin(a, b, rest)
    if not rest_is_skin:
        return feature, dropped

    h, w = feature.shape[:2]
    n, labels, stats, _c = cv2.connectedComponentsWithStats(feature, connectivity=8)
    keep = feature.copy()
    for label in range(1, n):
        x, y = stats[label, cv2.CC_STAT_LEFT], stats[label, cv2.CC_STAT_TOP]
        cw, ch = stats[label, cv2.CC_STAT_WIDTH], stats[label, cv2.CC_STAT_HEIGHT]
        # GUARD 1.
        if not (x == 0 or y == 0 or x + cw >= w or y + ch >= h):
            continue
        component = (labels == label).astype(np.uint8) * 255
        if (component > 0).sum() < 100:
            continue
        is_skin, stat = looks_like_skin(a, b, component)
        if is_skin:
            continue
        keep[labels == label] = 0
        dropped.append({
            "area_px": int((component > 0).sum()),
            "a_median": stat.get("a_median"),
            "b_median": stat.get("b_median"),
        })
    return keep, dropped


def looks_like_skin(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> tuple[bool, dict]:
    """Is the segmented subject plausibly skin?

    Skin of EVERY tone sits in the warm quadrant of LAB: a* positive (toward
    red) and b* positive (toward yellow). Melanin changes L dramatically and
    the hue only mildly, so a hue test is safe across skin tones in a way a
    brightness test would not be -- deliberately, because a brightness-based
    check here would refuse to work on dark skin.

    THE ABSOLUTE TEST IS NOT ENOUGH ON ITS OWN. Under fluorescent or otherwise
    cool light -- which is most clinics -- real skin measures a* and b* NEGATIVE,
    and an absolute warmth test then answers "this is not skin" and refuses to
    analyse the image at all. That is the same mistake as the old dark-area
    floor: an absolute cut on a quantity the lighting dominates.

    So warmth is also tested RELATIVE to the background, which is lit by the
    same lamp. Whatever the illuminant does to the skin it does to the backdrop
    too, and skin stays warmer than a plain backdrop under any of them. Either
    test passing is enough: this gate exists to catch a foot sent to the eye
    module, not to be a precise skin classifier, and being wrongly restrictive
    breaks the product for every clinic with a fluorescent tube.
    """
    sel = mask > 0
    if sel.sum() < 100:
        return False, {"reason": "no subject segmented"}

    a_med = float(np.median(a[sel]))
    b_med = float(np.median(b[sel]))
    stats: dict = {"a_median": round(a_med, 2), "b_median": round(b_med, 2)}

    warm_absolute = (a_med >= 2.0 and b_med >= 4.0
                     and a_med <= 45.0 and b_med <= 60.0)

    warm_relative = False
    background = ~sel
    if background.sum() > 500:
        a_bg = float(np.median(a[background]))
        b_bg = float(np.median(b[background]))
        stats["a_vs_background"] = round(a_med - a_bg, 2)
        stats["b_vs_background"] = round(b_med - b_bg, 2)
        warm_relative = (a_med - a_bg) >= 2.0 and (b_med - b_bg) >= 3.0

    stats["warm_absolute"] = warm_absolute
    stats["warm_relative"] = warm_relative
    return bool(warm_absolute or warm_relative), stats


def chroma(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from the neutral axis in LAB. Colourfulness, independent of
    how light or dark the pixel is."""
    return np.sqrt(a * a + b * b)


# --- colour reference card ---------------------------------------------------
#
# Every threshold this platform applies to colour is stated RELATIVE to the
# patient's own skin, precisely because absolute colour in a phone photograph is
# not a measurement -- auto white balance, tungsten versus daylight, and the
# screen the clinician is standing under all move it further than illness does.
# Relative thresholds survive that, but two images of the same wound taken on
# different days still cannot be compared numerically.
#
# A neutral grey or white card held in the frame fixes that, and only that. It
# gives the illuminant a known answer, so the correction that maps the card back
# to neutral can be applied to the whole frame. It does NOT make the camera a
# colorimeter, and it does not make any of the findings diagnostic.

REFERENCE_MIN_AREA_FRAC = 0.004     # smaller than this and it is a highlight
REFERENCE_MAX_AREA_FRAC = 0.25      # larger and it is probably the background
# A card under a coloured light is NOT neutral in the captured pixels -- that
# cast is exactly what it is there to measure. So this bound is loose enough to
# admit a card under a strong indoor cast, and the genuinely coloured objects it
# lets through are caught afterwards by the gain-spread refusal, which asks a
# sharper question: are these gains plausible for any real illuminant?
REFERENCE_MAX_CHROMA = 30.0         # LAB units from the neutral axis
REFERENCE_MIN_L = 70.0              # a card in deep shadow corrects nothing
# Deliberately admits blown-out cards. A card detected and then refused with
# "move out of direct light" is far more useful to the clinician than a card
# that was never mentioned at all.
REFERENCE_MAX_L = 255.0
REFERENCE_MAX_L_STD = 14.0          # a card is flat; a wall with a shadow is not
REFERENCE_MAX_CLIPPED_FRAC = 0.02   # blown highlights carry no colour
REFERENCE_MAX_GAIN = 1.60           # beyond this the "card" was probably not grey
# A card must stand clearly apart in brightness from whatever else in the frame
# is neutral. Without this, a plain grey backdrop with no card in it splits
# arbitrarily into a "bright half" that then gets used as a reference.
REFERENCE_MIN_SEPARATION_L = 25.0


def find_reference_card(
    bgr: np.ndarray, subject_mask: np.ndarray | None = None
) -> dict | None:
    """Locate a neutral grey/white reference card in the frame.

    Returns a descriptor including a `mask` of the card, or None when no
    candidate survives. Detection is deliberately strict: a wrongly identified
    "card" would apply a wrong colour correction to the whole image, which is
    worse than applying none at all.

    Neutrality alone is not enough to find a card, because clinical backdrops
    are themselves neutral -- a grey card on a grey table is one contiguous
    neutral region. The card is therefore separated from the rest of the
    neutral area by brightness (Otsu), and only accepted when the two
    populations are genuinely distinct.
    """
    h, w = bgr.shape[:2]
    frame_area = float(h * w)
    if frame_area <= 0:
        return None

    L, a, b = lab_planes(bgr)
    neutral_sel = (
        (chroma(a, b) < REFERENCE_MAX_CHROMA)
        & (L >= REFERENCE_MIN_L)
        & (L <= REFERENCE_MAX_L)
    )
    if neutral_sel.sum() < frame_area * REFERENCE_MIN_AREA_FRAC:
        return None

    values = L[neutral_sel].astype(np.uint8)
    level, _ = cv2.threshold(values.reshape(-1, 1), 0, 255,
                             cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright_sel = neutral_sel & (L >= float(level))
    dim_sel = neutral_sel & (L < float(level))
    if not bright_sel.any() or not dim_sel.any():
        return None
    # Two distinct populations, or one population that Otsu cut in half?
    if (float(L[bright_sel].mean()) - float(L[dim_sel].mean())
            < REFERENCE_MIN_SEPARATION_L):
        return None

    # BOTH populations are candidates, not just the brighter one. The obvious
    # assumption -- the card is the brightest neutral thing -- inverts in the
    # case that matters most: an UNDERexposed white card next to well-lit skin
    # renders DARKER than the skin, and skin is neutral enough to be in this
    # set. The card being invisible exactly when the light is bad would defeat
    # using it to detect bad light.
    # The region a card may legitimately occupy: the subject's own bounding box
    # grown by 60%. Measuring centre-to-centre distance instead penalises a
    # card laid neatly beside a LARGE subject, which is precisely how the
    # instructions say to place it.
    near_box = None
    subject_sel = None
    if subject_mask is not None and (subject_mask > 0).sum() > 100:
        ys, xs = np.nonzero(subject_mask)
        x0, x1 = float(xs.min()), float(xs.max())
        y0, y1 = float(ys.min()), float(ys.max())
        mx, my = (x1 - x0) * 0.6, (y1 - y0) * 0.6
        near_box = (x0 - mx, y0 - my, x1 + mx, y1 + my)
        # A mask covering nearly the whole frame is the close-up fallback and
        # carries no information about WHERE the subject is, so it cannot be
        # used to tell card from subject.
        if (subject_mask > 0).mean() < 0.90:
            subject_sel = subject_mask > 0

    candidates: list[dict] = []
    for population in (bright_sel, dim_sel):
        found = _card_from_population(
            population, bgr, L, a, b, frame_area, h, w, near_box, subject_sel)
        if found:
            candidates.append(found)
    if not candidates:
        return None
    # The most neutral one. A card is the least colourful thing in frame.
    return min(candidates, key=lambda c: c["chroma_mean"])


def _card_from_population(population, bgr, L, a, b, frame_area, h, w,
                          near_box, subject_sel) -> dict | None:
    neutral = population.astype(np.uint8) * 255
    neutral = clean_binary(neutral, min(h, w))

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(neutral, 8)
    if n <= 1:
        return None

    best: dict | None = None
    for label in range(1, n):
        area = float(stats[label, cv2.CC_STAT_AREA])
        frac = area / frame_area
        if frac < REFERENCE_MIN_AREA_FRAC or frac > REFERENCE_MAX_AREA_FRAC:
            continue

        x, y = int(stats[label, cv2.CC_STAT_LEFT]), int(stats[label, cv2.CC_STAT_TOP])
        bw = int(stats[label, cv2.CC_STAT_WIDTH])
        bh = int(stats[label, cv2.CC_STAT_HEIGHT])
        if bw < 8 or bh < 8:
            continue
        aspect = bw / float(bh)
        if aspect < 0.25 or aspect > 4.0:
            continue
        # A card is a solid rectangle. A neutral-looking sliver of background
        # threading between objects is not.
        if area / float(bw * bh) < 0.62:
            continue

        # Held next to the region being photographed, not across the room --
        # a distant surface is under a different light and would mislead.
        if near_box is not None:
            cx, cy = float(centroids[label][0]), float(centroids[label][1])
            if not (near_box[0] <= cx <= near_box[2]
                    and near_box[1] <= cy <= near_box[3]):
                continue

        component = (labels == label)

        # THE CARD IS NOT THE PATIENT. Held beside the area of interest, it
        # falls outside the segmented subject; a candidate lying inside the
        # subject is the subject. Without this, a smooth expanse of skin was
        # detected as a grey card, the correction neutralised the skin, and the
        # module then rejected the image as "not skin" -- a healthy finger made
        # unanalysable by the very step meant to make it comparable.
        if subject_sel is not None:
            inside = float(subject_sel[component].mean())
            if inside > 0.25:
                continue

        # Erode before sampling so the card's edge, its shadow and any bleed
        # from the neighbouring surface stay out of the measurement.
        patch = cv2.erode(
            component.astype(np.uint8) * 255,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
            iterations=2,
        )
        sel = patch > 0
        if sel.sum() < 200:
            sel = component
            patch = component.astype(np.uint8) * 255

        # The LEAST COLOURFUL valid candidate, not the largest. Skin is
        # neutral enough to enter this set and is usually the biggest thing in
        # frame, so picking by area hands back the foot instead of the card
        # whenever the card is brighter than the skin -- which is the normal
        # case for a white card.
        if best is None or best["chroma_mean"] > float(chroma(a, b)[sel].mean()):
            best = {
                "area_px": area,
                "area_frac": frac,
                "bbox": (x, y, bw, bh),
                "mask": patch,
                "sel": sel,
                "L_mean": float(L[sel].mean()),
                "L_std": float(L[sel].std()),
                "chroma_mean": float(chroma(a, b)[sel].mean()),
            }

    if best is None:
        return None

    sel = best.pop("sel")
    channels = bgr[sel].astype(np.float32)          # N x 3, BGR
    means = channels.mean(axis=0)
    clipped = float((channels >= 250.0).any(axis=1).mean())

    best.update({
        "bgr_mean": [round(float(v), 2) for v in means],
        "clipped_frac": round(clipped, 4),
        "L_mean": round(best["L_mean"], 2),
        "L_std": round(best["L_std"], 2),
        "chroma_mean": round(best["chroma_mean"], 2),
        "area_frac": round(best["area_frac"], 4),
    })
    return best


def white_balance_gain(card: dict) -> tuple[np.ndarray | None, str | None]:
    """Per-channel gain that maps the card back to neutral.

    Returns (gains, None) or (None, refusal reason). Gains are normalised so the
    largest is 1.0: scaling channels DOWN can never clip, scaling them up can,
    and a clipped correction silently destroys the highlights the measurement
    depends on.
    """
    if card["clipped_frac"] > REFERENCE_MAX_CLIPPED_FRAC:
        return None, (
            "The reference card is over-exposed, so it carries no colour "
            "information. Move out of direct light or flash and re-capture."
        )
    if card["L_std"] > REFERENCE_MAX_L_STD:
        return None, (
            "The reference card is unevenly lit — part of it is in shadow. "
            "Light the card and the area of interest the same way."
        )
    means = np.asarray(card["bgr_mean"], dtype=np.float32)
    if float(means.min()) < 20.0:
        return None, (
            "The reference card is too dark to correct from. Add even, "
            "indirect light and re-capture."
        )
    gains = float(means.max()) / np.maximum(means, 1.0)
    gains = gains / float(gains.max())            # largest gain becomes 1.0
    spread = float(gains.max() / max(gains.min(), 1e-6))
    if spread > REFERENCE_MAX_GAIN:
        return None, (
            "The detected card is strongly coloured, so it is probably not a "
            "neutral grey reference. No colour correction was applied."
        )
    return gains.astype(np.float32), None


def apply_gain(bgr: np.ndarray, gains: np.ndarray) -> np.ndarray:
    out = bgr.astype(np.float32) * gains.reshape(1, 1, 3)
    return np.clip(out, 0, 255).astype(np.uint8)


def clean_binary(mask: np.ndarray, min_dim: int, open_iter: int = 1) -> np.ndarray:
    k = max(3, (min_dim // 100) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    out = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=open_iter)
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel, iterations=1)
    return out


def blobs_from_mask(
    mask: np.ndarray, subject_area: float, min_area_pct: float = 0.15, top_n: int = 4
) -> list[tuple[np.ndarray, float, tuple[int, int, int, int], tuple[int, int]]]:
    """Contours of a feature mask, largest first.

    Returns (contour, area_pct_of_subject, bbox, centroid) tuples.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        area = float(cv2.contourArea(c))
        if area <= 0 or subject_area <= 0:
            continue
        pct = area / subject_area * 100.0
        if pct < min_area_pct:
            continue
        x, y, w, h = cv2.boundingRect(c)
        m = cv2.moments(c)
        if m["m00"] == 0:
            cx, cy = x + w // 2, y + h // 2
        else:
            cx, cy = int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])
        out.append((c, pct, (x, y, w, h), (cx, cy)))
    out.sort(key=lambda t: t[1], reverse=True)
    return out[:top_n]


def area_pct(mask: np.ndarray, subject_mask: np.ndarray) -> float:
    subject = float((subject_mask > 0).sum())
    if subject <= 0:
        return 0.0
    return float((mask > 0).sum()) / subject * 100.0


def region_coherence(mask: np.ndarray) -> dict:
    """Is this ONE thing, or a scatter of unrelated specks that happen to sum?

    Every area in this module is a total: `area_pct` counts pixels and does not
    care whether they touch. Twenty separated flecks of slightly yellower skin
    -- freckles, mottling, JPEG blocking, a sprinkle of talc -- sum to exactly
    the same percentage as one wound of that size, and the same threshold fires
    on both.

    A wound is a connected thing with a boundary. Scattered colour variation is
    not, and a percentage alone cannot tell them apart.

    `dominant_fraction` is the largest connected component's share of the mask.
    Near 1.0 the region is one object; near 0 it is confetti. This measures
    SPATIAL ARRANGEMENT ONLY -- it says nothing about what the region is.
    """
    sel = (mask > 0).astype(np.uint8)
    total = float(sel.sum())
    if total <= 0:
        return {"components": 0, "dominant_fraction": 0.0, "dominant_px": 0.0,
                "total_px": 0.0}

    n, _labels, stats, _c = cv2.connectedComponentsWithStats(sel, connectivity=8)
    if n <= 1:
        return {"components": 0, "dominant_fraction": 0.0, "dominant_px": 0.0,
                "total_px": total}

    areas = stats[1:, cv2.CC_STAT_AREA].astype(np.float64)
    dominant = float(areas.max())
    return {
        "components": int(n - 1),
        "dominant_fraction": round(dominant / total, 4),
        "dominant_px": round(dominant, 1),
        "total_px": round(total, 1),
    }


def mask_asymmetry(mask: np.ndarray) -> float:
    """Reflect the region about its principal axis through the centroid and
    measure the mismatch. A proxy for asymmetric swelling -- 0 = symmetric."""
    pts = cv2.findNonZero(mask)
    if pts is None or len(pts) < 50:
        return 0.0
    data = pts.reshape(-1, 2).astype(np.float32)
    mean, eigvecs = cv2.PCACompute(data, mean=None, maxComponents=2)
    centre = mean[0]
    axis = eigvecs[0]
    normal = np.array([-axis[1], axis[0]], dtype=np.float32)

    rel = data - centre
    d = rel @ normal
    reflected = data - 2.0 * np.outer(d, normal)

    h, w = mask.shape[:2]
    ref_mask = np.zeros_like(mask)
    ri = np.rint(reflected).astype(np.int32)
    valid = (ri[:, 0] >= 0) & (ri[:, 0] < w) & (ri[:, 1] >= 0) & (ri[:, 1] < h)
    ri = ri[valid]
    if ri.size == 0:
        return 0.0
    ref_mask[ri[:, 1], ri[:, 0]] = 255
    ref_mask = cv2.morphologyEx(
        ref_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )

    inter = float(((mask > 0) & (ref_mask > 0)).sum())
    union = float(((mask > 0) | (ref_mask > 0)).sum())
    if union <= 0:
        return 0.0
    return float(1.0 - inter / union)


def contour_solidity(mask: np.ndarray) -> tuple[float, float]:
    """(solidity, deepest convexity defect normalised by region size).

    Low solidity / a deep defect means the outline bulges or steps -- a visible
    contour irregularity. It says nothing about what is under the skin.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 1.0, 0.0
    c = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(c))
    if area < 50:
        return 1.0, 0.0
    hull = cv2.convexHull(c)
    hull_area = float(cv2.contourArea(hull))
    solidity = area / hull_area if hull_area > 0 else 1.0

    depth = 0.0
    hull_idx = cv2.convexHull(c, returnPoints=False)
    if hull_idx is not None and len(hull_idx) > 3 and len(c) > 3:
        try:
            defects = cv2.convexityDefects(c, hull_idx)
        except cv2.error:
            defects = None
        if defects is not None and len(defects):
            depth = float(defects[:, 0, 3].max()) / 256.0
    norm_depth = depth / (np.sqrt(area) + 1e-6)
    return float(solidity), float(norm_depth)


def border_irregularity(contour: np.ndarray) -> float:
    """Perimeter^2 / (4*pi*area). 1.0 for a perfect circle."""
    area = float(cv2.contourArea(contour))
    per = float(cv2.arcLength(contour, True))
    if area <= 0:
        return 1.0
    return float(per * per / (4.0 * np.pi * area))


def colour_cluster_count(bgr: np.ndarray, mask: np.ndarray, k: int = 4) -> int:
    """How many distinct colours occupy a meaningful share of the region."""
    sel = bgr[mask > 0]
    if sel.shape[0] < 50:
        return 1
    if sel.shape[0] > 5000:
        idx = np.random.default_rng(7).choice(sel.shape[0], 5000, replace=False)
        sel = sel[idx]
    data = sel.astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    try:
        _, labels, centres = cv2.kmeans(
            data, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
        )
    except cv2.error:
        return 1
    counts = np.bincount(labels.flatten(), minlength=k) / float(len(labels))
    # A cluster counts only if it holds >=12% of the region and is visibly
    # distinct from the region mean.
    mean_c = centres.mean(axis=0)
    distinct = 0
    for i in range(k):
        if counts[i] < 0.12:
            continue
        if np.linalg.norm(centres[i] - mean_c) > 18.0:
            distinct += 1
    return max(1, distinct)


# --- shadow or eschar --------------------------------------------------------
#
# The single most important discrimination this module makes, and the one it
# got wrong in the field: a healthy toe was reported as necrotic tissue because
# the gap between two toes is dark. Area and darkness alone cannot separate
# them -- a shadow and an eschar are both "a dark patch".
#
# What separates them is the EDGE and the SURFACE.
#
#   A shadow is cast light. Its boundary is a gradient, because the penumbra
#   spreads over many pixels, and its interior is as smooth as the skin under
#   it -- there is nothing there but less light.
#
#   An eschar is a physical crust. Its boundary is an edge, because the tissue
#   itself changes at that line, and its interior is rough: dried, fissured,
#   wrinkled.
#
# So: measure the sharpness of the boundary, and the texture inside it.

# Measured across soft/crisp/faint/deep shadows on light and dark skin
# (13.6-30.0) and across smooth/typical/fissured crusts (271-283). Set with
# room on both sides; a real photograph is noisier than a synthetic one, and
# the fallback when the two measurements disagree is "indeterminate", which
# suppresses nothing.
SHADOW_MAX_EDGE = 60.0        # mean gradient across the boundary band
SHADOW_MAX_TEXTURE = 6.0      # std of the high-pass response inside the region


def dark_region_character(bgr: np.ndarray, region: np.ndarray) -> dict:
    """Is a dark region a cast shadow, or a change in the tissue itself?

    Returns the two measurements and a verdict of "shadow_like",
    "tissue_like" or "indeterminate". It never returns a diagnosis: an eschar,
    a bruise and dark pigmentation are all "tissue_like", and separating THOSE
    needs a clinician's eyes and hands.
    """
    sel = region > 0
    if sel.sum() < 200:
        return {"verdict": "indeterminate", "reason": "region too small to characterise"}

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Boundary sharpness: the gradient in a thin band straddling the outline.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    band = (cv2.dilate(region, kernel, 2) > 0) & ~(cv2.erode(region, kernel, 2) > 0)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient = np.sqrt(gx * gx + gy * gy)
    edge = float(gradient[band].mean()) if band.sum() > 50 else 0.0

    # Interior texture: high-pass energy inside the region. A shadow inherits
    # the smoothness of whatever it falls on; a crust has structure of its own.
    smooth = cv2.GaussianBlur(gray, (0, 0), 3)
    texture = float((gray - smooth)[sel].std())

    soft_edge = edge <= SHADOW_MAX_EDGE
    smooth_inside = texture <= SHADOW_MAX_TEXTURE
    if soft_edge and smooth_inside:
        verdict = "shadow_like"
    elif not soft_edge and not smooth_inside:
        verdict = "tissue_like"
    else:
        verdict = "indeterminate"

    return {
        "verdict": verdict,
        "edge_gradient": round(edge, 2),
        "interior_texture": round(texture, 2),
        "thresholds": {"edge_max_for_shadow": SHADOW_MAX_EDGE,
                       "texture_max_for_shadow": SHADOW_MAX_TEXTURE},
        "meaning": {
            "shadow_like": "Soft boundary and smooth interior — the signature "
                           "of cast light, not of a change in the tissue.",
            "tissue_like": "Defined boundary and textured interior — something "
                           "on the skin, not a shadow. It does NOT say what: "
                           "eschar, bruise and dark pigmentation look alike.",
            "indeterminate": "The two measurements disagree.",
        }[verdict],
    }


# --- callus or slough --------------------------------------------------------
#
# The same class of problem as shadow-versus-eschar, one axis over. Callus and
# slough are both yellow and both sit on the surface, so the b* threshold that
# finds one finds the other -- and a field capture showed exactly that: thick
# callus on a toe was measured as "tissue breakdown".
#
# What differs is the MATERIAL and where it sits.
#
#   Callus is dry thickened keratin, continuous with the skin around it. It
#   thickens gradually, so it has no edge at skin level, and being dry it
#   scatters light evenly with few specular highlights.
#
#   Slough is moist devitalised tissue lying IN a defect. The wound margin is
#   a real edge, and wet tissue throws specular highlights that dry keratin
#   does not.
#
# Neither measurement names a diagnosis. "Callus-like" is not "harmless" --
# an ulcer very often hides underneath callus, which is why the follow-up asks
# whether the skin is actually broken rather than trusting this.

SLOUGH_MIN_EDGE = 25.0          # wound margin gradient (callus ~15, slough ~35)
SLOUGH_MIN_SPECULAR = 0.012     # fraction of the region that is wet-bright


def yellow_region_character(bgr: np.ndarray, region: np.ndarray,
                            subject: np.ndarray | None = None) -> dict:
    """Dry keratin, or moist tissue in a defect?

    Returns the measurements and a verdict of "slough_like", "callus_like" or
    "indeterminate".
    """
    # Fill interior holes FIRST. The mask arrives from a b* (yellowness)
    # threshold, and a specular highlight is near-white — neutral, not yellow —
    # so every wet spot is punched OUT of the region before it gets here. That
    # is the exact signal this function measures moisture by, which meant a
    # wetter wound scored as DRIER: the more it glistened, the more holes were
    # cut and the fewer bright pixels remained inside to count.
    #
    # A highlight sits IN the wound. Filling puts it back before measuring.
    region = region.copy()
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        filled = np.zeros_like(region)
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
        region = filled

    sel = region > 0
    if sel.sum() < 200:
        return {"verdict": "indeterminate",
                "reason": "region too small to characterise"}

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    band = (cv2.dilate(region, kernel, 2) > 0) & ~(cv2.erode(region, kernel, 2) > 0)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge = float(np.sqrt(gx * gx + gy * gy)[band].mean()) if band.sum() > 50 else 0.0

    # Moisture, as specular highlights: pixels far brighter than the region's
    # own body. Dry keratin has very few.
    values = gray[sel]
    ceiling = float(np.percentile(values, 50)) + 45.0
    specular = float((values >= ceiling).mean())

    defined_edge = edge >= SLOUGH_MIN_EDGE
    wet = specular >= SLOUGH_MIN_SPECULAR
    if defined_edge and wet:
        verdict = "slough_like"
    elif not defined_edge and not wet:
        verdict = "callus_like"
    else:
        verdict = "indeterminate"

    return {
        "verdict": verdict,
        "edge_gradient": round(edge, 2),
        "specular_fraction": round(specular, 4),
        "thresholds": {"edge_min_for_slough": SLOUGH_MIN_EDGE,
                       "specular_min_for_slough": SLOUGH_MIN_SPECULAR},
        "meaning": {
            "slough_like": "A defined margin and a moist surface — consistent "
                           "with tissue in an open defect.",
            "callus_like": "No edge at skin level and a dry surface — "
                           "consistent with thickened keratin. This does NOT "
                           "mean harmless: an ulcer often lies underneath "
                           "callus and cannot be seen until it is pared back.",
            "indeterminate": "The two measurements disagree.",
        }[verdict],
    }
