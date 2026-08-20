"""Per-analysis state must not live on the shared backend singleton.

`get_backend` returns a module-level `ClassicalCVBackend()` (backends/__init__),
and analyses run concurrently in a worker thread pool (runner.InlineRunner uses
`anyio.to_thread.run_sync`). Anything written to `self` during one analysis is
therefore visible to every other analysis running at the same time.

The failure this guards against is not a crash. It is a framing warning --
"the foot could not be separated from the background, so every percentage below
is UNDERSTATED" -- silently detaching from the result it belongs to, under
load, with no error anywhere. Understated areas are the direction that hides
things, which is why that warning exists at all.
"""

from __future__ import annotations

import threading

import numpy as np

from app.analysis.backends import classical_backend
from app.analysis.backends.classical import ClassicalCVBackend
from app.analysis.quality import run_quality_gate

_SKIN_BGR = (140, 170, 205)
_CONTRASTING_BGR = (200, 90, 40)


def _jittered(img: np.ndarray, seed: int) -> np.ndarray:
    """A little noise so the frame is not perfectly flat, which the quality
    gate reads as out of focus."""
    rng = np.random.default_rng(seed)
    return np.clip(
        img.astype(int) + rng.integers(-6, 7, img.shape), 0, 255
    ).astype(np.uint8)


def _unsegmentable_skin_frame() -> np.ndarray:
    """Skin filling the whole frame, so subject and background are the same
    colour and the segmentation cannot separate them."""
    return _jittered(np.full((400, 400, 3), _SKIN_BGR, dtype=np.uint8), 0)


def _foot_on_a_contrasting_background() -> np.ndarray:
    img = np.full((400, 400, 3), _CONTRASTING_BGR, dtype=np.uint8)
    img[100:300, 120:280] = _SKIN_BGR
    return _jittered(img, 1)


def _fragment_mask() -> np.ndarray:
    """The arbitrary fragment a border-model segmentation returns when the
    background is skin-coloured: well under the 0.55 frame share, well over
    the 100 px floor."""
    mask = np.zeros((400, 400), np.uint8)
    mask[150:250, 150:250] = 255
    return mask


def test_the_framing_warning_belongs_to_one_analysis_not_the_backend():
    """Two overlapping analyses, one triggering the framing warning and one
    not. Each result must carry its own, and neither may take the other's.

    The interleaving is forced rather than raced for, so this is a real
    assertion and not a flake: analysis A is held inside the measurement step,
    after the widen step has raised its warning and before the warning is read
    back, while analysis B runs start to finish through the same backend
    object.

    Against the pre-fix code B's entry into `analyze` executes
    `self._background_warning = None`, wiping A's warning while A is parked
    two lines away from reading it. A then reports no framing warning at all
    -- its understated percentages presented as if they were sound.
    """
    backend = classical_backend()

    a_is_inside_the_measurement = threading.Event()
    b_has_finished = threading.Event()
    original_foot = ClassicalCVBackend._foot

    def _foot_holding_a_open_across_b(self, bgr, mask, quality):
        # Only A pauses. B must run start to finish inside this window.
        if threading.current_thread().name == "analysis-a":
            a_is_inside_the_measurement.set()
            assert b_has_finished.wait(timeout=30), "B never completed"
        return original_foot(self, bgr, mask, quality)

    ClassicalCVBackend._foot = _foot_holding_a_open_across_b
    try:
        results: dict[str, object] = {}
        failures: dict[str, BaseException] = {}

        def run_a() -> None:
            try:
                image = _unsegmentable_skin_frame()
                quality = run_quality_gate(image)
                quality.mask = _fragment_mask()
                results["a"] = backend.analyze(image, "foot", quality)
            except BaseException as exc:       # noqa: BLE001 - re-raised below
                failures["a"] = exc
            finally:
                # So a failure in A cannot hang the main thread on the event.
                a_is_inside_the_measurement.set()

        a = threading.Thread(target=run_a, name="analysis-a")
        a.start()
        assert a_is_inside_the_measurement.wait(timeout=30), "A never started"

        image_b = _foot_on_a_contrasting_background()
        results["b"] = backend.analyze(image_b, "foot", run_quality_gate(image_b))

        b_has_finished.set()
        a.join(timeout=30)
        assert not a.is_alive(), "A did not finish"
    finally:
        ClassicalCVBackend._foot = original_foot

    if failures:
        raise failures["a"]

    a_features = results["a"].features
    b_features = results["b"].features

    assert "framing_warning" in a_features, (
        "A's framing warning was lost -- B's analysis reset it while A was "
        "still mid-measurement. A's percentages are understated and nothing "
        "in its result says so."
    )
    assert (a_features["framing_warning"]["issue"]
            == "background_same_colour_as_skin")
    assert any("UNDERSTATED" in line for line in results["a"].triage.rationale)

    assert "framing_warning" not in b_features, (
        "B took A's framing warning. B's foot was cleanly segmented against a "
        "contrasting background; it must not report otherwise."
    )
    assert not any("UNDERSTATED" in line for line in results["b"].triage.rationale)


def test_the_backend_keeps_no_per_analysis_state_between_calls():
    """The narrow assertion behind the concurrency one: after an analysis that
    raises the framing warning, nothing about that analysis is left on the
    shared object for the next one to find.

    Checked by attribute rather than by behaviour so that reintroducing
    per-analysis state under a different name fails here too.
    """
    backend = classical_backend()

    image = _unsegmentable_skin_frame()
    quality = run_quality_gate(image)
    quality.mask = _fragment_mask()
    result = backend.analyze(image, "foot", quality)
    assert "framing_warning" in result.features       # the warning did fire

    leaked = {
        name: value for name, value in vars(backend).items()
        if not callable(value) and name not in {"name", "version", "backend_id"}
    }
    assert leaked == {}, (
        f"per-analysis state left on the shared backend singleton: {leaked}"
    )
