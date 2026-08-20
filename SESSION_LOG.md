# Session log

A running record of what changed and, more importantly, WHY. Commit messages
carry the full reasoning; this file exists so a future session — or a reviewer
at a partner institution — can see the shape of the work without reading every
diff.

Entries are newest first. Each names the commit, what moved, and the evidence
that motivated it.

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

Nothing outstanding as of `92bda3b`. Tasks 6 (answer form) and 7 (skin tone) are
untouched and belong to a future session.
