# Session log

A running record of what changed and, more importantly, WHY. Commit messages
carry the full reasoning; this file exists so a future session — or a reviewer
at a partner institution — can see the shape of the work without reading every
diff.

Entries are newest first. Each names the commit, what moved, and the evidence
that motivated it.

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
- **The findings table and the "observed" text report different quantities**
  under the same label — the text totals the whole mask, the table lists the
  largest three blobs above 0.15%. Not a bug; nothing on the page says which
  is which. Observed as 5.1% vs 2.5%+1.9% on a field run.

Tasks 6 (answer form) and 7 (skin tone) are untouched and belong to a future
session.
