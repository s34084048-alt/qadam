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


# Horizontal visible iris diameter ("white-to-white") in adults. Tight around
# 11.7 mm with roughly ±0.5 mm spread, and largely independent of ethnicity,
# sex and refractive error -- which is why contact-lens fitting relies on it.
# It makes the iris a ruler that is already inside every eye photograph, so
# pupil size can be estimated without asking anyone to hold up a coin.
IRIS_DIAMETER_MM = 11.7
IRIS_DIAMETER_SD_MM = 0.5


def measure_pupils(bgr: np.ndarray, max_eyes: int = 2) -> list[dict]:
    """Locate iris/pupil pairs and measure the pupil against the iris.

    Returns one entry per eye found, ordered left-to-right in the image, each
    with pixel radii, the scale-free pupil/iris ratio, and an estimated pupil
    diameter in mm. Returns [] when nothing meets the criteria -- reporting
    "not measurable" is correct, inventing a number is not.
    """
    h, w = bgr.shape[:2]
    scale = work_scale(bgr)
    small = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) \
        if scale < 1.0 else bgr
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    lab_a = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)[:, :, 1].astype(np.float32) - 128.0
    frame_area = float(gray.size)

    # How much of the frame the iris occupies depends entirely on how the photo
    # was taken -- a close-up of one eye versus both eyes in a face shot differ
    # by an order of magnitude -- so a single brightness cut cannot work for
    # both. Sweep several and keep whatever comes out round.
    contours: list[np.ndarray] = []
    for percentile in (4, 7, 11, 16, 22, 30):
        cut = float(np.percentile(gray, percentile))
        _, dark = cv2.threshold(gray, cut, 255, cv2.THRESH_BINARY_INV)
        dark = cv2.morphologyEx(
            dark, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
        found, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours.extend(found)

    candidates: list[dict] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area / frame_area < 0.002 or area / frame_area > 0.30:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0:
            continue
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        if circularity < 0.55:          # an iris is round; an eyebrow is not
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if radius <= 4:
            continue

        # An iris is a dark disc ringed by SCLERA: bright and near-neutral in
        # colour. Requiring that ring rejects the two things that otherwise
        # masquerade as an iris -- the pupil itself (ringed by iris, which is
        # far less bright) and any round dark lesion on skin (ringed by skin,
        # which is warm-toned rather than neutral).
        ring = np.zeros_like(gray)
        cv2.circle(ring, (int(cx), int(cy)), int(radius * 1.35), 255, cv2.FILLED)
        cv2.circle(ring, (int(cx), int(cy)), int(radius * 1.05), 0, cv2.FILLED)
        ring_px = ring > 0
        if ring_px.sum() < 40:
            continue
        disc_px = np.zeros_like(gray)
        cv2.circle(disc_px, (int(cx), int(cy)), int(radius * 0.9), 255, cv2.FILLED)
        iris_mean = float(gray[disc_px > 0].mean())
        ring_mean = float(gray[ring_px].mean())
        if ring_mean - iris_mean < 40.0:
            continue
        ring_a = float(lab_a[ring_px].mean())
        if abs(ring_a) > 12.0:          # warm ring = skin, not sclera
            continue

        # The pupil is the darkest core inside the iris disc.
        disc = np.zeros_like(gray)
        cv2.circle(disc, (int(cx), int(cy)), int(radius * 0.95), 255, cv2.FILLED)
        # Every real eye photograph has a corneal reflection -- the catchlight
        # from whatever lit the shot -- sitting as a bright spot inside the
        # iris. Left in, it drags the Otsu split upwards and the pupil is
        # measured as the whole iris. Exclude specular pixels from both the
        # histogram and the mask.
        specular = gray > (iris_mean + 90.0)
        usable = (disc_px > 0) & ~specular
        inside = gray[usable]
        if inside.size < 60:
            continue
        # Pupil versus iris inside the disc is a two-class split, and what
        # fraction of the disc the pupil occupies is exactly what we are trying
        # to measure -- so a fixed percentile begs the question and lands in
        # the iris whenever the pupil is small. Otsu finds the split from the
        # histogram instead.
        pupil_cut, _ = cv2.threshold(
            inside.reshape(-1, 1).astype(np.uint8), 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        core = ((gray <= pupil_cut) & usable).astype(np.uint8) * 255
        # Close first: a catchlight punches a hole in the pupil, and the hole
        # must be filled before the pupil is measured.
        core = cv2.morphologyEx(
            core, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        core = cv2.morphologyEx(
            core, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        core_contours, _ = cv2.findContours(
            core, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not core_contours:
            continue
        core_contour = max(core_contours, key=cv2.contourArea)
        (px, py), pupil_radius = cv2.minEnclosingCircle(core_contour)
        if pupil_radius <= 2:
            continue

        ratio = float(pupil_radius / radius)
        # Outside this band the segmentation has found something that is not an
        # iris/pupil pair -- a shadow, a nostril, a dark frame edge.
        if not 0.15 <= ratio <= 0.85:
            continue

        inv = 1.0 / scale if scale < 1.0 else 1.0
        candidates.append({
            "centre": (int(cx * inv), int(cy * inv)),
            "iris_radius_px": round(radius * inv, 1),
            "pupil_radius_px": round(pupil_radius * inv, 1),
            "pupil_centre": (int(px * inv), int(py * inv)),
            "pupil_iris_ratio": round(ratio, 3),
            "pupil_diameter_mm": round(ratio * IRIS_DIAMETER_MM, 2),
            "circularity": round(float(circularity), 3),
        })

    # The sweep finds the same iris at several cuts. Collapse overlapping
    # detections, keeping the roundest at each location.
    # Largest first: the sweep detects the pupil and the iris at the same
    # centre, and the outer disc is the iris.
    candidates.sort(key=lambda c: (c["iris_radius_px"], c["circularity"]),
                    reverse=True)
    distinct: list[dict] = []
    for candidate in candidates:
        cx, cy = candidate["centre"]
        if any((cx - k["centre"][0]) ** 2 + (cy - k["centre"][1]) ** 2
               < (max(k["iris_radius_px"], candidate["iris_radius_px"])) ** 2
               for k in distinct):
            continue
        distinct.append(candidate)

    distinct.sort(key=lambda c: c["iris_radius_px"], reverse=True)
    kept = distinct[:max_eyes]
    # Two irises in one photograph should be a similar size. A wild mismatch
    # means one of them is not an iris.
    if len(kept) == 2:
        big, small_ = (max(kept, key=lambda c: c["iris_radius_px"]),
                       min(kept, key=lambda c: c["iris_radius_px"]))
        if big["iris_radius_px"] > small_["iris_radius_px"] * 1.6:
            kept = [big]
    kept.sort(key=lambda c: c["centre"][0])
    return kept


_face_cascade: "cv2.CascadeClassifier | None" = None


def locate_face(bgr: np.ndarray, mask: np.ndarray) -> tuple[tuple[int, int, int, int], str]:
    """Return (x, y, w, h) of the face box and how it was obtained.

    Tries a Haar cascade, then falls back to the bounding box of the segmented
    subject. The fallback is not just convenience: Haar frontal-face cascades
    are documented to detect faces less reliably on darker skin tones and in
    uneven light, and a module that simply refuses to run on some patients is a
    worse failure than one that uses the framed region. The capture guidance
    already asks for the face to fill the frame, so the fallback box is close
    to the detection in practice. Which path was used is reported in the
    result, so it can be audited per skin-tone group.
    """
    global _face_cascade
    h, w = bgr.shape[:2]

    try:
        if _face_cascade is None:
            _face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        if not _face_cascade.empty():
            gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
            faces = _face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5,
                minSize=(int(min(h, w) * 0.2), int(min(h, w) * 0.2)),
            )
            if len(faces):
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                return (int(x), int(y), int(fw), int(fh)), "Haar cascade"
    except Exception:
        pass

    points = cv2.findNonZero(mask)
    if points is None:
        return (0, 0, w, h), "full frame (no subject segmented)"
    x, y, fw, fh = cv2.boundingRect(points)
    return (int(x), int(y), int(fw), int(fh)), "framed subject region (fallback)"


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


def looks_like_skin(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> tuple[bool, dict]:
    """Is the segmented subject plausibly skin?

    Skin of EVERY tone sits in the warm quadrant of LAB: a* positive (toward
    red) and b* positive (toward yellow). Melanin changes L dramatically and
    the hue only mildly, so a hue test is safe across skin tones in a way a
    brightness test would not be -- deliberately, because a brightness-based
    check here would refuse to work on dark skin.
    """
    sel = mask > 0
    if sel.sum() < 100:
        return False, {"reason": "no subject segmented"}
    a_med = float(np.median(a[sel]))
    b_med = float(np.median(b[sel]))
    stats = {"a_median": round(a_med, 2), "b_median": round(b_med, 2)}
    warm_enough = a_med >= 2.0 and b_med >= 4.0
    not_absurd = a_med <= 45.0 and b_med <= 60.0
    return bool(warm_enough and not_absurd), stats


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

    neutral = bright_sel.astype(np.uint8) * 255
    neutral = clean_binary(neutral, min(h, w))

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(neutral, 8)
    if n <= 1:
        return None

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

        if best is None or area > best["area_px"]:
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
