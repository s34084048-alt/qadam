# Session log

A running record of what changed and, more importantly, WHY. Commit messages
carry the full reasoning; this file exists so a future session — or a reviewer
at a partner institution — can see the shape of the work without reading every
diff.

Entries are newest first. Each names the commit, what moved, and the evidence
that motivated it.

---

## 2026-08 — CORRECTIONS to the three entries below

No code change. Recorded because this file is the reviewer-facing record and
its standing rule is that nothing is claimed as verified that was not run. Two
claims below do not meet that bar, and a third is a limitation found after the
commit that stated the opposite optimism.

### 1. "A photograph that was not a foot" — NOT ESTABLISHED

Commit `7991f81` and the entry *"Three defects one photograph exposed"* both
describe the run they were built from as a photograph that was **not a foot**.
That was an inference from two things: the page's own message *"the photographed
area does not read as skin"*, and this author's reading of a phone screenshot.

A later run on the deployed build produced an identical result — `dark area
41.3% / 1.00`, `tissue breakdown 31.3% / 1.00`, `erythema 1.3%`, evidence
`0.20`, REVIEW, and the same three overlay labels — on what was reported as a
photograph of the ulcerated foot. Two different photographs cannot agree to one
decimal place across three features, so the earlier image was most likely the
same foot photograph in a close frame.

**What is actually established is only the weaker statement: the measured
region did not read as skin.** That is the system's own claim about its own
measurement, not ground truth about the subject.

**The fix in `7991f81` stands unchanged and needs nothing stronger.** It
withholds a clinical instruction when the measurements it would be chosen from
have been declared unreliable — which is exactly the weaker statement. Only the
description of the evidence was wrong.

It also means the skin check may FALSE-POSITIVE on a real foot in a close
frame. That is not investigated here and is listed below as outstanding.

### 2. The red-bed test does not fire on the one real ulcer available

Commit `5db8aee` demonstrated `red_region_character` on two synthetic images
and recorded its constants as guesses. It did not say what it does on real
data, because at that point there was none. There is now — one photograph of an
open plantar ulcer — and on it the test returns **`diffuse_like`**. It misses.

Diagnosed, and **the constants are not the cause**:

| region measured | edge | specular | verdict |
|---|---|---|---|
| ulcer alone, hand-marked r=40 | **48.8** | **0.041** | `bed_like` |
| ulcer + surrounding pink skin, r=62 | 11.2 | 0.009 | `diffuse_like` |
| whole erythema mask | 18.5 | 0.009 | `diffuse_like` |
| largest erythema blob | 18.9 | 0.010 | `diffuse_like` |

Thresholds are `edge ≥ 25.0` and `specular ≥ 0.012`. On the ulcer itself both
clear comfortably. The a\* threshold merges the bed with the pink skin around
it, and the soft outer boundary of that merged region is what gets measured.

The synthetic fixtures were far more extreme than reality — edge **149** where
a real ulcer gives **48.8** — which is why they passed and hid this.

**Attempted and reverted:** measuring over the region `wound_localization`
isolated instead of the raw colour mask. Localisation is not on the ulcer
either — its box is at `x=302` where the ulcer is at `x≈255`, and the overlap
with the erythema mask is **0 px**. The change was a no-op that added a branch,
so it was not committed.

**The next step is region delineation, not constant tuning.** Nothing in the
pipeline currently isolates the wound tightly enough for a boundary test to
mean anything.

### 3. What the pipeline does on that photograph, for the record

Run locally on the file as supplied, 600×398:

    grade urgent | evidence 0.85 | not-skin=no
    dark 0.7%  breakdown 6.9%  erythema 13.7%
    localisation = confirmed_possible_wound
    ULCER BOXED: YES

So the misses reported from the phone were not reproduced on the image itself.
The deployed build is several commits behind and its offline queue was jammed
throughout ("an item was rejected by the server and everything after it is held
back"), so what it analysed is not known to be what was uploaded. **No
conclusion about detection should be drawn from those runs**, including the
favourable ones.

### Outstanding after these corrections

- The skin check may fire on a real foot in a close frame. Suspected from the
  identical-results finding above; not reproduced under controlled conditions,
  because an arbitrary crop of the same photograph fails the exposure check
  before reaching it.
- `red_region_character` is unvalidated against real data and currently misses
  the only real case available. It changes no grade, so the cost of the miss is
  a weaker description, not a weaker safety property.

---

## 2026-08 — A red wound bed was being reported as "surface redness"

One commit on `claude/product-progress-simple-laptop-j5r127`. Test suite:
**523 passing, 0 failing** (518 before).

### The question this answers

Asked directly, of a field photograph of an open plantar ulcer: *why did it not
recognise the wound?* It had. The page said `erythema — uncertain — 10.7%`,
inside a bounding box far larger than the ulcer, and nothing distinguished it
from a flush.

The cause is structural, not a threshold. This module measures three things:

| feature | rule | i.e. |
|---|---|---|
| `erythema` | `a* ≥ a_med + 8` | RED things |
| `tissue_breakdown` | `b* ≥ b_med + 12` | YELLOW things |
| `dark_area` | `L ≤ L_med − 55` | DARK things |

A granulating bed is red. `tissue_breakdown` measures **yellowness** — that is
slough — so it could never have caught it. There is no wound model anywhere in
the classical backend: three colour buckets, no shape and no texture.

A hypothesis that was checked and is NOT the cause: the backdrop poisoning the
skin reference. Measured on the reproduction — whole frame `L_med 194.0,
b_med 10.0` versus foot only `196.0, 12.0`. The median is robust; the reference
was fine.

### What was added

`cv_utils.red_region_character` — the same two measurements that separate
slough from callus, one colour axis over: a **margin** (boundary gradient) and
**moisture** (specular fraction). Verdicts `bed_like` / `diffuse_like` /
`indeterminate`, mirroring the two character tests that already existed.

Separation on the two synthetic cases it exists for: edge **149.1** and
specular **0.133** for a bounded wet bed, against **9.1** and **0.0** for a dry
flush.

### What it deliberately does not do

**It cannot raise the grade.** `evidence._erythema` still returns
`ceiling=Grade.REVIEW, sufficient_for_urgent=False` for every verdict including
the strongest, for the reason recorded there: redness in a photograph is a
colour, and a *bounded* red area is still a colour. None of these measurements
establishes warmth, infection or depth. `test_erythema_can_never_reach_urgent_
whatever_the_character_says` asserts it across all four verdict values, and is
marked in that file as the test that must not be deleted.

The one place the claim moves at all is `lesion_role`: erythema can now read
`possible_wound` instead of `uncertain` — but only when `bed_like` AND
localisation independently drew a `confirmed_possible_wound` boundary. Two
mechanisms must agree before the word "wound" appears next to a red region, and
the grade is unaffected either way. On `foot_urgent` the character is
`bed_like` but localisation is only `uncertain_surface_abnormality`, so the
role stays `uncertain` — the guard holds on the fixture most likely to trip it.

**Notes for a future reader.**
- `diffuse_like` carries its own limit line, because "no margin" could be read
  as the all-clear and spreading erythema is itself a red flag a single
  photograph cannot rule out. Tested.
- Interior holes are filled before measuring, for the reason
  `yellow_region_character` documents: a specular highlight is near-white and
  therefore not red, so the a\* threshold punches every wet spot out of the
  region — and moisture is the thing being measured. A wetter bed would score
  as drier.
- The two constants are copied from the slough test rather than newly fitted.
  They are guesses, as those are.
- Fixtures unmoved: `foot_urgent` still `urgent` at `erythema 9.44%` /
  `breakdown 6.05%`, asserted numerically.

**This is a new detection capability**, which the standing constraints below
otherwise rule out. It was added at the explicit request of the maintainer,
after the limitation was demonstrated on a real photograph. It describes; it
does not grade.

---

## 2026-08 — The recommended backdrop was being scored as a finding

One commit on `claude/product-progress-simple-laptop-j5r127`. Test suite:
**518 passing, 0 failing** (512 before). Frontend typecheck clean.

### The failure

A field close-up of a real ulcerated foot on a blue cloth graded URGENT, and
the grade was substantially right. The annotated image was not: a red
**POSSIBLE WOUND** box was drawn on the cloth, two `tissue breakdown` boxes sat
on the fabric, and the real ulcer was boxed as *erythema* rather than tissue
breakdown. The `6.0%` behind the urgent bullet was largely backdrop pixels.

Reproduced synthetically. On a close-up where the foot **runs off the frame
edges** — which is what a good close-up looks like — the border band that
`estimate_subject_mask` models the background from is itself mostly skin.
Everything then inverts: the reproduction's mask came back **99.9%
background**, and the cloth was measured as a `dark_area` covering 33.1% of
the imaged region.

### Why the fix is not in the mask

The wideners are not broken and were not changed. `_widen_if_the_lesion_became_
the_subject` detected this correctly and fell back to the whole frame, which is
right — a stable, interpretable denominator beats an arbitrary fragment. The
defect is downstream: with the whole frame as the subject, the backdrop is
inside it, and the feature masks scored it.

So the exclusion is per feature region, in `_foot`, via
`cv_utils.drop_backdrop_regions`.

### The two guards, and why neither is optional

A wound bed, an eschar and a bruise are not skin-coloured either, so "not
skin" alone would delete the finding this module exists to report.

1. **The region touches the frame edge.** A backdrop reaches the edge; a
   lesion on a foot that is fully in frame does not. This is the same
   protection `estimate_subject_mask` already gives by filling interior holes.
2. **The rest of the subject reads as skin.** Light skin under a cool
   fluorescent tube measures a\* and b\* NEGATIVE — the exact failure
   `looks_like_skin` was rewritten to avoid. Under that lamp a real foot's own
   regions could satisfy guard 1 and fail the skin test both. But under that
   lamp *nothing* in frame reads as skin, so the rule disables itself entirely.

Both guards have their own test, in the direction that hides things.

### What it moved

**Nothing, on every real fixture.** `foot_clean`, `foot_shadow_only`,
`foot_dark_area` and `foot_urgent` come back with the identical grade,
confidence and all three percentages — the values recorded above for
`92bda3b`, asserted numerically by `test_backdrop_exclusion.py` so a future
change cannot move them quietly. The concern that "every percentage on every
image will change" was wrong: the rule fires only on the failure case.

**Notes for a future reader.**
- No new constant was introduced. The rule reuses `looks_like_skin`, whose
  thresholds already carry their own justification, rather than adding a
  "blueness" cut that would need defending on its own.
- The reference for guard 2 is the subject MINUS the feature. Including the
  feature would let a large backdrop region drag the very test meant to
  exclude it.
- Every excluded region is recorded on `features.backdrop_excluded` and stated
  on the page. A measurement that silently shrank is worse than one that is
  wrong — the reader has to see that something was removed, and how much.
- The exclusion note is lifted above the basis list rather than placed in it,
  for the reason the not-skin warning was: it explains why the numbers below
  are smaller than the pixels, so it cannot be one of them.
- **Not addressed:** in the field image the real ulcer was labelled `erythema`
  rather than `tissue_breakdown`. That is a detection question, not a masking
  one, and it is untouched here.

---

## 2026-08 — Three defects one photograph exposed

One commit on `claude/product-progress-simple-laptop-j5r127`. Test suite:
**512 passing, 0 failing** (499 before). Frontend typecheck clean.

### `7991f81` — What the mechanisms found did not reach the reader

**Where this came from.** Three field runs on a phone, against the deployed
build: a healthy foot, a real ulcerated diabetic foot, and a photograph that
was not a foot at all. The third exposed all three defects at once, and it is
worth stating plainly what it did NOT expose: every safety mechanism fired
correctly. The skin check caught a non-foot image. The prerequisites gate
dropped evidence strength to 0.20. Wound localisation classified the regions
as artifacts. Not one of those findings reached the part of the page a reader
reads.

**1. A non-foot image issued a clinical instruction.** The page recommended a
podiatry assessment within one week with three named investigations, three
cards above its own sentence saying every measurement on it was meaningless.

The narrow refusal in `aea514c` covers the reassuring direction only —
`NO_FLAG` from a non-skin region is refused outright, review/urgent are
surfaced. That asymmetry is right and is unchanged. Its recorded justification
was that a photograph of a desk becomes *"visible nonsense rather than a
clinical decision"*; a one-week referral with named tests is a clinical
decision. So the grade is kept and the instruction is withheld, `urgency` and
`routing_target` with it — a timeframe and a destination **are** the
instruction. `summary.py` and `pdf.py` now skip an empty label rather than
printing `Timeframe:` with nothing after it.

**2. The role was dropped by every surface except the picture.** The overlay
read `tissue breakdown [artifact] 31.3%`; the findings table read
`tissue breakdown | 31.3% | 1.00`. The rule lived in a private helper inside
the renderer, so only the renderer could apply it. It is now
`analysis/lesion_role.py`, and the overlay colour, `LesionOut.role`, the PDF
table and the summary text all ask it — the agreement is what the tests
assert, not one copy of the rule. Derived at serialisation from `features`,
not stored: no migration, and an older analysis re-read today gets today's
rule instead of a stale copy.

**3. The not-skin warning was a peer bullet.** "Basis for this grade" listed
*"every measurement below is meaningless"*, *"the measured areas reach the
urgent threshold"* and *"visible tissue breakdown meets the urgent threshold"*
as three items of one list. The first governs the other two. It is lifted
above the list and no longer repeated inside it.

**Notes for a future reader.**
- `UNCERTAIN` is the default for every kind with no positive verdict,
  including kinds this pipeline does not characterise. Defaulting to
  `ARTIFACT` would dismiss a finding on no evidence; `POSSIBLE_WOUND` would
  assert one. Neither is a reading of the image.
- The over-claim guard (a box may never claim more than localisation
  confirmed) moved into `lesion_role` with the rest of the rule. The wound
  boundary box in `render_overlay` computes its own `confirmed` locally and
  was not touched.
- Six of the thirteen new tests fail against the unfixed code. The rest are
  narrowness guards and pass either way by design — a test that the grade is
  not quietly downgraded has nothing to fail against.

**Not fixed, deliberately.** `severity` is `area_pct / severity_ref` clipped
to `[0.05, 1.00]`, with `severity_ref` of 12.0 / 8.0 / 30.0 chosen the same
way the old `severity_index` weights were. On this run both regions saturated
at **1.00** and every value on the earlier ulcer run was the **0.05 floor** —
in neither case a measurement. It is not independent information: it is area
divided by a guess. This is the same defect `19fe436` removed `severity_index`
for, and like that one it is a decision about what to publish rather than a
bug to patch. Left standing and recorded here so the next session does not
rediscover it.

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

- **`severity` is area divided by a guessed constant** (`7991f81`). Saturates
  at 1.00 and floors at 0.05; both were observed on real runs. Removing or
  redesigning it is the same call that was made for `severity_index`, and it
  needs data rather than better constants.
- **The skin check may false-positive on a real foot in a close frame.** See
  the corrections entry at the top of this file. Not reproduced under
  controlled conditions yet.
- **`red_region_character` misses the one real ulcer available** — a region
  problem, not a threshold problem. Measurements in the corrections entry.
- **The findings table and the "observed" text report different quantities**
  under the same label — the text totals the whole mask, the table lists the
  largest three blobs above 0.15%. Not a bug; nothing on the page says which
  is which. Observed as 5.1% vs 2.5%+1.9% on a field run.

Tasks 6 (answer form) and 7 (skin tone) are untouched and belong to a future
session.
