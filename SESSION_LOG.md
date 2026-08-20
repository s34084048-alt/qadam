# Session log

A running record of what changed and, more importantly, WHY. Commit messages
carry the full reasoning; this file exists so a future session — or a reviewer
at a partner institution — can see the shape of the work without reading every
diff.

Entries are newest first. Each names the commit, what moved, and the evidence
that motivated it.

---

## 2026-08 — The reference-card false positive

One commit on `claude/input-gate-rebuild-fxhqqn`. Test suite: **522 passing, 0
failing** (516 before, 6 added). Frontend typecheck clean.

### The contradiction

The gate shipped in `0b1db75` rejected a reference card's printed markings as
a watermark. The capture instructions *ask* for a card in the frame, and real
cards carry printing — a size, a grey value, a maker's name. A gate that
refuses the workflow the product recommends is a gate that gets switched off,
and then nothing is gated at all.

Measured before the fix, on a card that calibration accepts (`applied=True`,
`L_std` 10.1 against a limit of 14):

```
AssertionError: a capture made the way the instructions describe was REFUSED:
reason=overlay lines=[6]
```

### The fix is spatial, not a switch

Text lying **wholly inside** a detected card is exempt; anything outside still
rejects. Straddling the edge is not printing on a card — a mark placed half-on
a card would otherwise be ignored, which is a bypass anyone could use on
purpose.

The gate locates the card with exactly the calls `pipeline.execute` makes
later — `estimate_subject_mask`, then `find_reference_card` with that mask —
so the region it exempts is the region calibration will use. Both are
deterministic on the same input, so they cannot disagree, and a test asserts
the two agree rather than trusting it. The lookup only runs when a text line
was actually found, so an ordinary capture never pays for card detection twice.

The card descriptor also carries a `mask`, and it is the **wrong** handle: that
mask is the eroded *neutral* region, and ink is not neutral, so the printing is
exactly what it leaves out. Containment is tested against the bounding box.

| | before | after |
|---|---|---|
| `carded_foot` | REJECTED `overlay` | urgent 0.85, calibration applied, cm² available |
| `carded_and_watermarked_foot` | rejected (for the card's own print) | REJECTED `overlay`, card print exempted, watermark caught |
| `watermarked_foot` | REJECTED `overlay` | REJECTED `overlay` |
| everything else | unchanged | unchanged |

### The fixture had to be made legible before it proved anything

The first version of `carded_foot` printed three lines at ~10 px glyph height,
and it **passed the gate even before the exemption existed** — its measured
fill-ratio CV was 0.143 against a 0.15 threshold. At that size the statistics
sit on the boundary and sensor noise decides the verdict: the same card built
with a different noise seed rejected. A test written against it would have
passed on both trees and proved nothing.

The committed fixture prints at a size the detector reads as text on every
seed tried — fill-ratio CV 0.26–0.28 against 0.15, minimum solidity 0.17–0.18
against 0.50 — while the card still calibrates. That window is narrower than
it looks, and finding it turned up something new, recorded below.

---

## 2026-08 — The input gate, rebuilt

Three commits on `claude/input-gate-rebuild-fxhqqn`. Test suite: **516
passing, 0 failing** (499 before, 17 added). Frontend typecheck clean.

Session 2 built this and the work was lost before it was committed. This is a
rebuild from the failure, not a recovery of that code.

### The failure

A live run processed a stock image carrying a clinic watermark — a domain, a
phone number and a line of Persian text — and produced a full URGENT report at
0.78 confidence, routed "Same day". Every layer below behaved correctly. The
quality gate found it sharp and well exposed, because it was. The segmentation
found a foot, because there was one. The clinical layer graded what it was
handed. Nothing had asked the first question: **is this a photograph of this
patient's foot, taken now, by the person holding the phone?**

### `44a24b7` — Fixtures that reproduce it

Five synthetic frames drawn from OpenCV primitives in the same idiom as
`app.sample_data`: a watermarked wound, a re-photographed display, a wet ulcer
under fourteen specular highlights, a clean foot, and a foot at arm's length.
Measured against the pipeline as it then stood, the watermarked frame came
back `urgent` at 0.78 and the screen photograph at 0.80.

Two properties of the fixtures are load-bearing. Sensor noise is applied to
the whole frame **last**, after the watermark is composited — an overlay drawn
on a noiseless canvas is perfectly flat, and a detector could separate it from
a photograph on that alone, passing the test without detecting any text. And
the specular highlights have bright cores with soft rims, at the size range
display text occupies, scattered rather than set on a baseline: that is how a
glint actually falls off, and the difference from a glyph is the only thing
the gate is allowed to rely on.

The domain and phone number are invented. Putting a real clinic's mark in a
committed fixture would be putting someone else's identity in this repository.

### `0b1db75` — `analysis/input_gate.py`

Three questions, asked before any backend runs. A frame that fails is
REJECTED with a reason — not graded low, not flagged, not discounted — and
cannot reach a grade, an overlay or a stored image, because `execute` returns
before a backend exists.

| | before | after |
|---|---|---|
| `watermarked_foot` | urgent 0.78 | REJECTED `overlay` |
| `screen_photo` | urgent 0.80 | REJECTED `rephotograph` |
| `distant_foot` | refused, wrong reason | REJECTED `subject_absent` |
| `wet_ulcer` | urgent 0.80 | urgent 0.80 |
| `clean_foot` | no_flag | no_flag |

Every existing sample keeps its exact verdict, the three quality-rejected ones
down to the same failing checks.

**The hard half is the false positive.** Wet tissue throws specular
highlights: small, bright, high-contrast blobs at exactly the size display
text occupies, and a row of them can share a baseline by chance. Rejecting a
real ulcer for glistening would be worse than the watermark, because the wound
that glistens is the wound that needs seeing. Brightness, contrast, stroke
width and edge sharpness were each measured and each failed to separate them.
Two things did, and both are about what the objects *are*:

- **Letterforms differ from one another.** A row of glyphs holds an O, an I
  and a full stop, which fill their bounding boxes very differently. A row of
  specular blobs is a row of convex ellipses, and every convex ellipse fills
  about π/4 of its box whatever its size.
- **Letterforms have counters and concavities.** Writing puts holes in glyphs
  and bends in strokes. A specular highlight is convex, because it is the
  image of a light source in a curved wet surface.

| | fill-ratio CV | min solidity |
|---|---|---|
| watermark wordmark | 0.351 | 0.122 |
| watermark phone number | 0.230 | 0.186 |
| watermark logo + script | 0.668 | 0.098 |
| glints, evenly sized in a row | 0.021 | 0.953 |
| glints, hard-edged in a row | 0.022 | 0.957 |
| glints, varied sizes in a row | 0.073 | 0.811 |
| glints, varied and jittered | 0.042 | 0.881 |

Both gaps are wide and the two measures are independent, so **both** are
required. That costs sensitivity to overlays of very few, very uniform glyphs
— the right side to err on, because a missed watermark is caught by a human
reading the report and a rejected ulcer is caught by nobody.

**Photographs of a screen** use two signals, because they fail in opposite
conditions: panel geometry needs the bezel in shot, the lattice peak needs the
display's pixel grid to have survived to the file. The lattice measure is
ring-normalised so a 1/f falloff cannot pose as a peak, then has linear
structure removed by line-opening over eight orientations — a straight shadow
crease puts a *ridge* through the spectrum, and a ridge is not a lattice.
Before that suppression the hardest negative scored 6.55 against the
positive's 8.42; after it, 3.46 against 8.63. A bright rectangle never rejects
on its own, because a sheet of paper or a phone on the couch is also a bright
rectangle.

**The subject-presence check was not weak. It was inverted.**
`estimate_subject_mask` has two escape hatches — a close-up branch and a
degenerate-mask fallback — and both return 1.0. It reports *maximum* subject
presence exactly when it has failed to find a subject. The same foot at
falling scales:

| presence | old measure | outcome |
|---|---|---|
| 0.109 | 0.109 | urgent, 6.1% breakdown — correct |
| 0.076 | 0.076 | rejected, `subject_present` |
| 0.049 | 0.049 | rejected, `subject_present` |
| 0.000 | **1.000** | **review grade, 0.5% breakdown — 98% wrong, reported** |
| 0.000 | 1.000 | refused later by the not-skin check |

A frame *further* past the boundary than the ones being rejected came back
with a grade. The threshold moved 0.08 → **0.10**, and the small raise is the
honest number rather than a flattering one: 0.15 was tried first and broke
four existing tests that deliberately require a verdict at presence 0.121 to
0.149 — the project has already decided that a tightly cropped lesion must be
seen. The usable window is 0.09–0.12. What made the check safe is the
measurement underneath it, not the constant on top.

**Ordering is load-bearing.** Overlay and rephotograph run *before* the
quality gate: both are answerable on a frame the quality gate would condemn,
and a stock image should be refused for being one rather than sent back for a
re-take it can never pass. Subject presence runs *after* it — an underexposed
frame reads as having no subject in it (`quality_dark` measures 0.000), and
told "move closer" a user re-takes the same dark photograph from closer up.

### `8ac855a` — Tests, and a heading that does not say "re-capture"

The watermark regression, stated so it runs on both trees. Against `44a24b7`:

```
AssertionError: a clinic watermark was ANALYSED instead of refused:
grade=urgent urgency='Same day' confidence=0.78
```

Against `0b1db75`: passes. The paired assertion — that the glistening ulcer
still comes back urgent — passes on **both**, so the rejection was not bought
with a true positive.

Half the tests exist to stop the gate over-reaching. Every rejection is paired
with something that must still get through, and
`test_specular_highlights_in_a_row_are_not_read_as_text` draws twelve glints
on a shared baseline in both an evenly-sized and an unevenly-sized variant, so
that baseline alignment alone can never become what the gate decides on.

The error panel had one rejection heading, "Image rejected — please
re-capture". Telling someone whose upload was a watermarked stock photograph
to re-capture sends them back to take the same picture again, so
`input_rejected` got its own heading in English and Arabic. No disclaimer text
was changed and no clinical claim was added.

### Thresholds

Every constant was measured against `tests/fixtures`, and **those are
drawings**. What they establish is an ordering with a wide gap; each constant
is placed in its gap rather than fitted to a distribution. Which are
boundaries the data drew and which are choices inside a range is marked per
constant in `config.py` and `input_gate.py`. None of it is validated against
real clinical capture.

---

## 2026-08 — Scoring integrity and two latent defects

Four commits on `claude/recover-session-2-remove-burden-fezrok`. Test suite:
**499 passing, 0 failing.** Frontend typecheck clean.

### `92bda3b` — Evidence strength is coupled to its own prerequisites

**What.** New `api/app/analysis/prerequisites.py`. Evidence strength now passes
through a gate that can only reduce it: a hard cap at **0.30** when any of three
segmentation failures fired, **−0.10** when a reference card was seen but
unusable, **−0.05** when there is no size reference in frame. Every adjustment
is itemised onto `Triage.confidence_adjustments` and rendered under "About this
score" (English and Arabic).

**Why.** `_conf` scored how far a measurement sat from its decision boundary and
read nothing about whether that measurement was possible. It returned **0.85 on
a run where the segmentation had explicitly failed**, and **0.53 on a healthy
foot whose "dark area" was background pixels**. Both numbers were arithmetically
correct and neither meant anything. A score that cannot fall when its own
preconditions fail is not a confidence signal.

**Notes for a future reader.**
- All three segmentation failure modes trigger the cap: background the same
  colour as skin, a degenerate subject mask replaced by the whole frame, and no
  wound region isolated. The middle one was previously *silent* — `analyze()`
  substituted the whole frame and nothing downstream said so.
- The `frame_share >= 0.55` early return is deliberately **not** a failure. It
  means the subject already fills over half the frame — a well-framed close-up.
  Flagging it would cap almost every good photograph.
- The two card penalties are mutually exclusive; a card is either absent or
  present-and-rejected. Card-unusable is the larger penalty because a rejected
  card means the frame holds a known object the pipeline could not interpret,
  so the capture geometry bears on everything measured from it.
- **The constants are guesses and say so in their own comments.** There is no
  labelled clinical data to fit them to. The defensible part is the ordering and
  the direction, not the values.
- Effect on the fixtures: `foot_urgent` 0.85 → 0.80 and `foot_dark_area`
  0.66 → 0.61 (size-reference penalty only); `foot_clean` and `foot_shadow_only`
  capped to 0.25. The cap lands on the reassuring `no_flag` results where no
  wound region was isolated — the direction that hides things — and leaves real
  detections with what the evidence earned.
- `no_flag` results do not display the itemisation, because they do not display
  a confidence number at all. Explaining a reduction to a hidden number would be
  worse than not showing it. Revisit if a clinician asks.
- `OnnxBackend` applies the size-reference penalties (a property of the capture,
  not of whichever model read it) but deliberately **not** the segmentation
  prerequisites — it does not run the steps those are read from, and inventing
  an equivalent would fabricate a check that never happened.

### `860bd2e` — Per-analysis state removed from the shared backend singleton

**What.** `_widen_if_the_segmentation_split_skin` returns `(mask, warning)`
instead of writing `self._background_warning`; `analyze()` holds it as a local.

**Why.** `get_backend` returns a module-level `ClassicalCVBackend()`, and
analyses run concurrently in a worker thread pool (`anyio.to_thread.run_sync`).
The framing warning was mutable state on that shared object: reset at the top of
`analyze()`, written during the widen step, read back after measurement. A
second analysis entering `analyze()` reset it while the first was still
measuring, two lines from reading it.

The lost warning reads *"the foot could not be separated from the background, so
every percentage below is UNDERSTATED"*. Understated areas are the direction that
hides things. The loss produced no error and no missing field — just a result
that looked sound.

**Notes.** `_background_warning` was the only per-analysis attribute on the
class; `name`/`version`/`backend_id` are immutable config, and `OnnxBackend`'s
attributes are set once in `__init__` and never written during analyze, so it
was never affected. The test forces the interleaving rather than racing for it,
so it asserts rather than flakes.

### `19fe436` — Surface burden index removed

**What.** The `_foot()` producer of `severity_index` is gone; it now returns
`None`, which is already the idiom in `_clinical_incomplete`.

**Why.** The formula was `min(100, nec*12 + brk*6 + ery*1.2)`, banded
minimal/mild/moderate/extensive, with weights chosen because they felt
proportionate rather than derived from anything. Across three runs:

| input | score |
|---|---|
| healthy foot, light background | 100% |
| lesion image, ~17% detected surface | 80.8%, then 89.2% on re-run |
| multi-region fixture, ~20% surface | 72.1% |

A 12× weight on `dark_area_pct` hits the cap at 8.3% dark pixels, and dark
pixels are also what a shadow, a callus, pigmentation and henna produce. The
band it printed most often was "extensive", and nothing a user could photograph
would have contradicted it.

**Removed, not reweighted.** A summary figure here would have to be designed
against validated data, and there is none; better constants would only move the
saturation point. If a summary number is wanted later it gets designed from
data, not from weights.

**Scope.** `severity_index`, its TypeScript type, and its UI card all stay —
`labs/interpret.py` counts results outside their reference range and
`foot_risk.py` reports an IWGDF category set from clinical findings. Both are
countable or externally defined. `ClinicalPanel` renders the card only when the
field is non-null, so no frontend change was needed; the PDF and text outputs
never rendered it.

### `9dc1d25` — Path traversal fallback no longer 500s

**What.** `resolve_web_asset()` checks containment before touching the
filesystem, and the `is_file()` probe moved inside the `try`.

**Why.** The guard read `if candidate.is_file() and
candidate.is_relative_to(web_root)`. `is_file()` stats the path, so a component
over `NAME_MAX` raised `OSError(ENAMETOOLONG)` before the containment half of
the `and` was evaluated — and the `except` sat around `resolve()` alone, which
does not raise for that input. An over-long path escaped as an unhandled
`OSError`: a 500 with a traceback, on a path an attacker chooses freely, in
front of the single-origin mount that also serves patient images.

**Notes.** Real assets, client-side routes and all eight `..` traversal cases
were untouched. The new test covers the class rather than the two literals
(over-long by component, by depth, by `NAME_MAX` per segment; null bytes; paths
both escaping and over-long) and five of its seven cases fail against the
unfixed function.

---

## Standing constraints these sessions worked under

Recorded because they shaped what was *not* done as much as what was:

- No new clinical claim, label or timeframe.
- No new detection capability.
- No existing disclaimer weakened or removed.
- Every change ships with a test, and a test for a bug fix must fail against the
  unfixed code.
- Nothing is claimed as verified that was not actually run.

## Known and deliberately not fixed

Found while building the input gate (`8ac855a`), each verified by running it
rather than reasoned about:

1. ~~A reference card with printed text is rejected as an overlay.~~ **Fixed**
   — see the entry above. What replaced it: a watermark that falls *wholly
   inside* a detected card region is now exempted along with the card's own
   printing. The exemption is bounded by the card detector's own limits (at
   most `REFERENCE_MAX_AREA_FRAC`, 25% of the frame, neutral, flat and beside
   the subject rather than on it), and it is the price of not refusing every
   carded capture.
2. **A card printed boldly enough is refused by CALIBRATION, not by the gate.**
   Found while sizing the fixture. `REFERENCE_MAX_L_STD` is 14, and larger,
   darker or heavier print covers enough of the card to push its `L_std` past
   that — at print scale 0.75 with a 2 px stroke it reached 19.1 and the card
   came back `applied=False`; bigger still and it is not detected at all. So a
   heavily printed card remains unusable as a colour reference no matter what
   the gate does. Not fixed: the flatness check is doing its job — a card whose
   surface is half ink is not a neutral patch — and the real answer is capture
   guidance about which face of the card to show, not a looser constant.
3. **Small overlay text is missed.** A burned-in camera date stamp at ~15 px
   glyph height measured `fill_cv` 0.143 against the 0.15 threshold and
   `min_solidity` 0.673 against 0.50 — it failed both, narrowly on one. The
   same stamp at 2.3× is detected. At that size JPEG and resampling degrade
   glyph shapes until their fill ratios and solidities converge, so the gate's
   sensitivity is size-dependent. Lowering the thresholds to catch it would
   walk into the glint numbers above.
4. **A wordless pictorial logo is not detected.** A filled, hard-edged,
   non-skin polygon mark over a wound is still graded `urgent`. The gate
   detects overlays that carry *text*; a purely graphic mark has no glyph row
   to find. Most watermarks carry text, which is why this was the priority,
   but "text or logo" is only half answered.
5. **Fewer than four glyphs is below the floor.** A three-character mark
   ("IMG") passes. Deliberate — three uniform shapes cannot be told from three
   glints — but it is a hole and someone should know it is there.
6. **`AnalysisOutput.quality_rejected` is True when `subject_error` is set**,
   with an empty failure list. Pre-existing, and `cases.py` is safe because it
   checks `subject_error` first, but any new caller reading that property gets
   "the quality gate rejected this" with nothing to show for it. The same
   conflation for input-gate rejections *was* fixed in `0b1db75`; this one was
   left alone because changing it touches a property this session did not
   otherwise own.
7. **The rephotograph thresholds rest on one positive fixture.** Overlay
   detection was calibrated against seven measured rows including four
   adversarial negatives; the lattice thresholds have one synthetic positive
   and eleven negatives. The corroborating threshold (4.5) and the panel
   contrast (45 levels) are guesses inside a gap drawn by a single drawn
   example, and they say so in their comments. A cropped, bezel-less version
   of the fixture is still caught (z 7.85), but that is the same drawn
   lattice, not independent evidence.

Tasks 6 (answer form) and 7 (skin tone) are untouched and belong to a future
session.
