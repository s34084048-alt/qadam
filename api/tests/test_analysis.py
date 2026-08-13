from __future__ import annotations

import base64

import pytest

from app.analysis.modules_config import routing_for
from app.sample_data import SAMPLES, png_bytes
from tests.conftest import API, make_case, make_patient

ANALYSABLE = [s for s in SAMPLES if s.expected_grade is not None]
QUALITY_NEGATIVE = [s for s in SAMPLES if s.expected_grade is None]


async def _analyze(client, auth, module: str, sample_name: str, ref: str):
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, module)
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze",
        headers=auth,
        files={"file": (f"{sample_name}.png", png_bytes(sample_name), "image/png")},
    )
    return case_id, resp


@pytest.mark.parametrize("sample", ANALYSABLE, ids=[s.name for s in ANALYSABLE])
async def test_sample_produces_expected_grade_and_routing(
    client, auth, ref_factory, sample
):
    _case_id, resp = await _analyze(
        client, auth, sample.module, sample.name, ref_factory(sample.name)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["module"] == sample.module
    assert body["triage"]["grade"] == sample.expected_grade

    expected = routing_for(sample.module, sample.expected_grade)
    assert body["triage"]["next_investigation"] == expected["next_investigation"]
    assert body["triage"]["routing_target"] == expected["routing_target"]
    assert body["triage"]["urgency"] == expected["urgency"]

    assert 0.0 < body["triage"]["confidence"] <= 0.85
    assert body["triage"]["rationale"]
    assert body["quality"]["passed"] is True
    assert body["overlay_png_base64"]
    assert base64.b64decode(body["overlay_png_base64"])[:4] == b"\x89PNG"
    assert body["backend"] == "classical_cv"
    assert body["model_version"].startswith("classical-cv")


@pytest.mark.parametrize(
    "sample", QUALITY_NEGATIVE, ids=[s.name for s in QUALITY_NEGATIVE]
)
async def test_quality_gate_rejects_and_stores_nothing(
    client, auth, ref_factory, sample
):
    ref = ref_factory("q")
    case_id, resp = await _analyze(client, auth, sample.module, sample.name, ref)
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "image_quality_rejected"
    assert error["hint"]

    failed = [c["name"] for c in error["details"]["quality"]["checks"]
              if not c["passed"]]
    assert failed

    # The rejected image is neither analysed nor stored.
    case = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert case["status"] == "quality_failed"
    assert case["latest_analysis"] is None
    assert case["history"] == []


def test_quality_gate_is_resolution_invariant():
    """The same sharp scene must get the same verdict at every capture size.

    Laplacian variance scales with resolution, so before normalisation a sharp
    4000 px phone photo measured ~32 and was rejected as blurred while the same
    scene at 800 px measured ~2500 and passed.
    """
    import cv2

    from app.analysis.pipeline import AnalysisJob, execute
    from app.sample_data import foot_urgent

    base = foot_urgent()
    grades = {}
    for label, size in (("native", None), ("phone", (3024, 2268)), ("small", (480, 360))):
        img = base if size is None else cv2.resize(base, size, interpolation=cv2.INTER_CUBIC)
        ok, buf = cv2.imencode(".png", img)
        assert ok
        out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                                  render_overlay=False))
        assert out.result is not None, f"sharp image rejected at {label} resolution"
        assert out.quality.passed, f"quality gate failed at {label} resolution"
        grades[label] = str(out.result.triage.grade)

    assert len(set(grades.values())) == 1, f"grade changed with resolution: {grades}"

    # A genuinely blurred capture is still rejected at phone resolution.
    blurred = cv2.GaussianBlur(cv2.resize(base, (3024, 2268)), (0, 0), 30.0)
    ok, buf = cv2.imencode(".png", blurred)
    out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                              render_overlay=False))
    assert out.result is None
    assert "focus" in [c.name for c in out.quality.failures]


def test_burned_in_disclaimer_stays_legible_at_high_resolution():
    """The overlay is the artefact most likely to be forwarded on its own, so
    the notice must keep its relative size on a full-resolution capture."""
    import cv2
    import numpy as np

    from app.analysis.pipeline import AnalysisJob, execute
    from app.sample_data import foot_urgent

    for size in ((800, 600), (3024, 2268)):
        img = cv2.resize(foot_urgent(), size, interpolation=cv2.INTER_CUBIC)
        ok, buf = cv2.imencode(".png", img)
        assert ok
        out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot"))
        assert out.overlay_png
        overlay = cv2.imdecode(np.frombuffer(out.overlay_png, np.uint8), cv2.IMREAD_COLOR)
        h = overlay.shape[0]

        # The band is whatever the renderer changed along the bottom edge.
        diff = np.abs(overlay.astype(np.int16) - img.astype(np.int16)).mean(axis=(1, 2))
        band_rows = 0
        for value in reversed(diff):
            if value < 12:
                break
            band_rows += 1
        assert band_rows / h >= 0.035, (
            f"disclaimer band is only {band_rows / h:.1%} of image height at "
            f"{size[0]}x{size[1]} — too small to read"
        )


async def test_unreadable_upload_is_rejected(client, auth, ref_factory):
    ref = ref_factory("bad")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "skin")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze",
        headers=auth,
        files={"file": ("x.png", b"this is not an image", "image/png")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unreadable_image"


async def test_unsupported_media_type_is_rejected(client, auth, ref_factory):
    ref = ref_factory("pdf")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "skin")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze",
        headers=auth,
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_media_type"


async def test_consent_is_required_before_any_image_is_stored(
    client, auth, ref_factory
):
    ref = ref_factory("noconsent")
    await make_patient(client, auth, ref, consent=False)
    case_id = await make_case(client, auth, ref, "foot")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze",
        headers=auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "consent_required"

    # Recording consent unblocks it.
    await client.patch(f"{API}/patients/{ref}", headers=auth,
                       json={"consent_flag": True})
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze",
        headers=auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert resp.status_code == 200


async def test_case_history_and_overlay_endpoint(client, auth, ref_factory):
    ref = ref_factory("hist")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    for name in ("foot_clean", "foot_urgent"):
        resp = await client.post(
            f"{API}/cases/{case_id}/analyze", headers=auth,
            files={"file": (f"{name}.png", png_bytes(name), "image/png")},
        )
        assert resp.status_code == 200

    case = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert case["latest_analysis"]["triage"]["grade"] == "urgent"
    assert len(case["history"]) == 1
    assert case["history"][0]["triage"]["grade"] == "no_flag"

    analysis_id = case["latest_analysis"]["id"]
    overlay = await client.get(
        f"{API}/cases/{case_id}/analyses/{analysis_id}/overlay.png", headers=auth
    )
    assert overlay.status_code == 200
    assert overlay.headers["content-type"] == "image/png"
    assert overlay.content[:4] == b"\x89PNG"


async def test_case_list_filters(client, auth, ref_factory):
    ref = ref_factory("list")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "eye")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("e.png", png_bytes("eye_urgent"), "image/png")},
    )

    listing = (await client.get(
        f"{API}/cases", headers=auth, params={"patient_ref": ref}
    )).json()
    assert listing["total"] == 1
    assert listing["items"][0]["triage_grade"] == "urgent"
    assert listing["items"][0]["module"] == "eye"

    filtered = (await client.get(
        f"{API}/cases", headers=auth,
        params={"patient_ref": ref, "grade": "no_flag"},
    )).json()
    assert filtered["total"] == 0

    bad = await client.get(f"{API}/cases", headers=auth, params={"module": "lungs"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "unknown_module"


async def test_pdf_summary(client, auth, ref_factory):
    ref = ref_factory("pdf")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "injury")

    empty = await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)
    assert empty.status_code == 409
    # A case with nothing in it at all — no analysis, no examination, no
    # bloods, no filed result. Any one of those is now enough to export.
    assert empty.json()["error"]["code"] == "nothing_to_summarise"

    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("i.png", png_bytes("injury_urgent"), "image/png")},
    )
    pdf = await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-"
    assert len(pdf.content) > 2000


async def test_case_requires_existing_patient(client, auth):
    resp = await client.post(
        f"{API}/cases", headers=auth,
        json={"module": "skin", "patient_ref": "does-not-exist"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "patient_not_found"
    assert "POST /api/v1/patients" in resp.json()["error"]["hint"]

# --- false-positive regression -----------------------------------------------

def test_shadow_is_not_reported_as_dead_tissue():
    """A user photographed a healthy finger and the foot module answered
    "urgent - necrotic tissue". The rule was `L <= min(L_med - 45, 70)`, whose
    absolute floor collapsed it to a plain shadow detector at any normal skin
    tone, with an urgent threshold of 0.5% - a 67x67 px patch."""
    import cv2
    import numpy as np

    from app.analysis.pipeline import AnalysisJob, execute

    W, H = 1200, 900
    rng = np.random.default_rng(3)

    def healthy_finger(with_shadow: bool):
        img = np.full((H, W, 3), (118, 118, 120), np.uint8)
        img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
        cv2.ellipse(img, (600, 470), (150, 330), 0, 0, 360, (150, 175, 205), -1)
        img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
        if with_shadow:
            cv2.line(img, (505, 190), (495, 760), (52, 58, 68), 22)
        return img

    for with_shadow in (False, True):
        ok, buf = cv2.imencode(".png", healthy_finger(with_shadow))
        assert ok
        out = execute(AnalysisJob(image_bytes=buf.tobytes(), module="foot",
                                  render_overlay=False))
        assert out.result is not None
        assert str(out.result.triage.grade) == "no_flag", (
            f"healthy skin (shadow={with_shadow}) was graded "
            f"{out.result.triage.grade}"
        )
        assert not out.result.lesions


def test_darkness_threshold_is_purely_relative_to_the_patients_own_skin():
    """The old absolute floor was also a fairness defect: it made the rule
    STRICTER on dark skin and more trigger-happy on light skin."""
    from app.analysis.backends.classical import T

    assert "necrosis_abs_L" not in T["foot"], (
        "an absolute darkness floor re-introduces the shadow detector"
    )
    assert T["foot"]["dark_rel_L"] > 0
    assert T["foot"]["urgent_dark_pct"] >= 5.0


async def test_a_dark_area_is_never_called_necrotic(client, auth, ref_factory):
    ref = ref_factory("dark")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("d.png", png_bytes("foot_dark_area"), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Routed for a look, not declared dead tissue.
    assert body["triage"]["grade"] == "review"
    assert {les["kind"] for les in body["lesions"]} <= {"dark_area", "erythema"}
    assert body["features"]["tissue_viability_assessed"] is False

    blob = " ".join(body["triage"]["rationale"]).lower()
    assert "not a diagnosis of necrosis" in blob
    assert "shadow" in blob

    # Shadow leads the differential, because it leads the reality.
    dark = next(c for c in body["clinical"]["considerations"]
                if "darker" in c["pattern"].lower())
    assert dark["overlaps_with"][0].startswith("SHADOW")
    assert "RE-IMAGE IN EVEN" in dark["distinguished_by"]

# --- wrong subject ------------------------------------------------------------

@pytest.mark.parametrize("image,module", [
    ("foot_clean", "eye"), ("foot_urgent", "eye"), ("skin_clean", "eye"),
    ("face_normal", "eye"), ("eye_clean", "foot"), ("eye_anisocoria", "skin"),
])
def test_a_module_refuses_input_it_cannot_interpret(image, module):
    """The eye module scored the warm tone of a photograph of a FOOT as
    scleral yellowing and answered "urgent - same-day medical review" at 0.85
    confidence. Colour statistics can be computed from anything; a confident
    answer from an uninterpretable input is the worst output this can produce.
    """
    from app.analysis.pipeline import AnalysisJob, execute

    out = execute(AnalysisJob(image_bytes=png_bytes(image), module=module,
                              render_overlay=False))
    assert out.subject_error is not None, (
        f"{image} was analysed by the {module} module instead of refused"
    )
    assert out.result is None
    assert out.subject_error.hint


@pytest.mark.parametrize("sample", ANALYSABLE, ids=[s.name for s in ANALYSABLE])
def test_the_right_subject_is_never_refused(sample):
    """The gate must not become so strict that it rejects real work."""
    from app.analysis.pipeline import AnalysisJob, execute

    out = execute(AnalysisJob(image_bytes=png_bytes(sample.name),
                              module=sample.module, render_overlay=False))
    assert out.subject_error is None, (
        f"{sample.name} was refused by its own module: "
        f"{out.subject_error.reason if out.subject_error else ''}"
    )


def test_a_jaundiced_sclera_is_not_mistaken_for_a_non_eye():
    """A yellow sclera fails a neutrality test — and jaundice is exactly what
    the eye module exists to catch, so the gate must not exclude it."""
    from app.analysis.pipeline import AnalysisJob, execute

    out = execute(AnalysisJob(image_bytes=png_bytes("eye_urgent"), module="eye",
                              render_overlay=False))
    assert out.subject_error is None
    assert out.result is not None
    assert str(out.result.triage.grade) == "urgent"


async def test_wrong_subject_is_a_distinct_api_error(client, auth, ref_factory):
    ref = ref_factory("subj")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "eye")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("f.png", png_bytes("foot_clean"), "image/png")},
    )
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "subject_not_recognised"
    assert "eye" in error["hint"].lower()

    # Nothing analysed, nothing stored.
    case = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert case["latest_analysis"] is None
