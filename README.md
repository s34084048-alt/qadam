# QADAM — visual triage platform

> **NOT A MEDICAL DEVICE — not for clinical use.**
> Research/decision-support tool — not a diagnosis. Not a substitute for
> clinical assessment. A qualified clinician must confirm every clinically
> significant output.

A trained health worker picks a module, captures or uploads a photo, and QADAM
returns an **image-quality check → a graded triage flag → an honest
recommended next investigation → a clinician summary**. Every case is stored,
exportable and auditable.

---

## 1. The safety boundary

This is the product definition, not a footnote. Everything below is enforced in
code (`api/app/safety.py`) and asserted in tests
(`api/tests/test_safety_boundary.py`).

QADAM performs **surface screening and triage routing only**. It is an aid to a
clinician, never a replacement.

It **never** claims to diagnose internal pathology from a photograph — no
fracture, dislocation, tendon rupture, muscle tear, internal bleeding, or any
sub-surface condition. A visible-light camera does not capture that information.

* **Injury is routing-only.** It detects external red flags (bruising,
  asymmetric swelling, visible deformity) and tells you which imaging or
  clinician to go to. It states that it cannot confirm or exclude internal
  injury, and a **no-flag** result states in capitals that it **does not exclude
  internal injury**.
* **Eye is anterior surface only.** Retinal disease — including diabetic
  retinopathy — is not assessable without a fundus camera and is out of scope.
  Pupil **size** is measured by scaling against the iris (taken as 11.7 mm);
  pupil **reaction to light** is not, and cannot be, from a still image —
  reaction matters more than size, and so does whether unequal pupils diverge
  in bright or in dim light. Both need a clinician with a torch.
* **Skin is not dermoscopy.** Only dermoscopy and histopathology can
  characterise a lesion.
* **Foot** cannot see depth, bone, infection, perfusion or neuropathy.
* **Face is relative colour only, and is not a pulse oximeter.** Camera white
  balance shifts apparent colour more than illness does, so only differences
  BETWEEN facial regions are used, with the sclera as an in-frame white
  reference. Confidence is capped at 0.55 — below every other module. A normal
  photograph does not exclude hypoxaemia, anaemia or stroke.
* **No treatment or medication is ever recommended.** The only output is a
  suggested next investigation.
* **The lab module takes typed numbers, never an image.** Units are required
  and validated, never inferred — creatinine 2.4 mg/dL is 212 µmol/L, and
  reading one as the other calls a patient in kidney failure normal. Reference
  ranges are common adult values, not authoritative: the reporting
  laboratory's range always wins, and a value inside a range is reported as
  "did not trigger a flag", not as normal. Radiology and MRI interpretation are
  **not** implemented and will not be — see §7.
* **Investigation results are filed, never read.** QADAM routes a patient to an
  X-ray; `/cases/{id}/investigations` is where the report comes back, so the
  referral stops trailing off into nothing. No model touches those documents,
  `app/routers/investigations.py` imports nothing from the analysis package
  (asserted by test), and a filed report naming a fracture changes no QADAM
  grade. DICOM is refused: its headers carry the patient's name, date of birth
  and accession number, and accepting one would silently break the pseudonymity
  the platform guarantees. Uploaded filenames are discarded for the same
  reason.
* **Offline capture never produces a grade.** Analysis runs on the server, so a
  queued capture has no triage grade — and the interface says so in those
  words, because "no grade" read as "no flag" is how a queued urgent foot gets
  left overnight. The offline bar repeats it on every screen while anything is
  waiting.
* **No patient data is cached for offline reading.** The service worker caches
  the app shell and the patient-free reference data only (module catalogue,
  safety boundary, analyte catalogue, foot risk model, emergency reference).
  Cases, images and reports are network-only: a cached patient record would sit
  on a shared clinic device outside the erasure path the API guarantees.
* **One clinic never sees another's data.** Users, patients and cases belong to
  an organisation, and every case- or patient-scoped route loads through a
  single scoped helper rather than each router remembering its own filter —
  one forgotten `where` clause would be a cross-clinic leak. Another
  organisation's record answers **404, not 403**: a 403 confirms the id exists
  and lets one clinic enumerate another's cases. Patient codes are unique
  *within* an organisation for the same reason. `test_organisation_isolation.py`
  enumerates every `{case_id}` route from the app itself, so a newly added
  endpoint cannot quietly skip the check.
* **No autonomous action** is ever taken on a patient.
* **The emergency reference is image-independent by construction.** A casualty's
  spinal status cannot be read from a photograph, so `GET
  /api/v1/reference/emergency` is a fixed reference card: it takes no input,
  reads no case, and `app/reference.py` imports nothing from the analysis
  package. A test asserts both the identical-response property and the absence
  of those imports, because the moment this became image-driven it would be the
  most dangerous thing in the platform.

The disclaimer and the `NOT A MEDICAL DEVICE` notice appear on every screen,
in every API payload (`safety` block), burned into every annotated overlay, and
on every page of every exported PDF. `GET /api/v1/health` reports
`clinical_use: false`; there is no configuration that changes it.

### What "confidence" means here

The number is a distance-from-threshold measure discounted by measured image
quality. It is **capped at 0.85** — an unvalidated placeholder model has no
business reporting near-certainty. It is not a calibrated probability, and no
sensitivity or specificity has been measured for anything in this repository.

---

## 2. Run it

### One command (Postgres + MinIO + API + web)

```bash
cp .env.example .env && docker compose up --build
```

| Service | URL | Notes |
| --- | --- | --- |
| Web app | http://localhost:8080 | nginx serving the built SPA, proxying `/api` |
| API docs | http://localhost:8000/docs | OpenAPI |
| MinIO console | http://localhost:9001 | `qadam` / `qadam-secret` |

The API container applies Alembic migrations and seeds demo data on first
start (`SEED_ON_START=true`). Sign in as:

* clinician — `clinician@qadam.local` / `qadam-clinician`
* admin — `admin@qadam.local` / `qadam-admin`

When the API reports `environment=local`, the sign-in page also lists these two
seeded accounts as one-click buttons. They disappear in any other environment.

Those passwords are printed here, which is exactly why the process **refuses to
start** on them when `ENVIRONMENT` is `staging` or `prod` — see
[DEPLOY.md](DEPLOY.md) for deploying to a permanent URL.

To use `/docs`: click **Authorize**, type the email into `username` and the
password into `password`, and leave `client_id` / `client_secret` empty.

### Without Docker (SQLite + local filesystem storage)

Same code, no services. This is also how the test suite runs.

```bash
cd api && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m app.seed --reset
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd web && npm install && npm run dev     # http://localhost:5173, proxies /api
```

### Testing on a phone (and why the camera needs this)

`getUserMedia` exists only in a **secure context**: HTTPS, or localhost. A phone
opening `http://192.168.x.x:5173` is neither, so the browser removes the camera
API altogether — the app is not broken, the platform has withdrawn the
capability. The same rule blocks the service worker, so offline mode needs this
too.

The dev server therefore runs over TLS with a locally generated certificate:

```bash
cd web
openssl req -x509 -nodes -newkey rsa:2048 -days 365   -keyout certs/dev-key.pem -out certs/dev-cert.pem -config certs/openssl.cnf
npm run dev
```

Put your machine's LAN address in `certs/openssl.cnf` under `[alt]` before
generating — a certificate without that address as a SAN will be rejected
outright rather than merely warned about. `vite.config.ts` picks the pair up
automatically and falls back to plain HTTP if `certs/` is absent.

On the phone, open `https://<your-lan-ip>:5173`, and on the certificate warning
choose **Advanced → Proceed**. Accepting it is what makes the origin secure, and
the camera and offline mode both appear. Only that one address is needed: the
API is proxied through the same origin.

The certificate is self-signed and gitignored along with its key. It is for
development only and must never be shipped.

### Clinician follow-up, and why answers only escalate

The clinical layer has always printed what to ask and examine — pulses,
monofilament, probe-to-bone, how long the lesion has been there. Those answers
can now be recorded against the case, and they re-run the routing decision:

```
final grade = max(image grade, answer grade)
```

Answers **raise** urgency and never lower it. The asymmetry is deliberate. The
image grade comes from a measurement; the answers are unverified self-report,
entered by whoever is holding the phone, with no evidence the monofilament test
was performed correctly or at all. Letting reassurance overwrite a measured flag
would create a one-click path to dismissing it. A false escalation costs an
unnecessary referral; a false de-escalation costs a foot. Reassuring answers are
still stored, still displayed, still exported — they just do not withdraw a
flag. `test_no_answer_set_can_lower_a_grade` asserts this exhaustively over
every answer of every question in every module.

The free-text note is stored and shown verbatim and appears in the PDF. It is
never parsed, scored, or used as a model input. The audit log records the grade
change and never the prose.

### Colour reference card

Colour in a phone photograph is set more by the room than by the patient, which
is why every threshold here is stated relative to the patient's own skin. That
makes a single image internally consistent but says nothing about whether this
week's wound is redder than last week's. A neutral grey or white card laid
beside the area of interest fixes exactly that: the correction that maps the
card back to neutral is applied to the whole frame, and the illuminant shift is
reported with the result.

Detection is deliberately strict, because a wrongly identified "card" applies a
wrong correction to everything. It is refused when over-exposed, unevenly lit,
too dark, strongly coloured, the wrong shape, across the room, or **overlapping
the subject** — that last one after a flat expanse of skin was detected as a
grey card, neutralised, and then rejected by the module as "not skin".
Whatever is identified as the card is removed from the measured region with a
margin, so a rectangle of cardboard is never scored as tissue. No card found is
not an error: analysis proceeds exactly as before and the result says so.

### Deleting a case

`DELETE /cases/{id}?confirm=true`, and in the UI a typed confirmation rather
than a second button — one mis-tap away from the first on a phone held over a
patient's foot. It is a HARD delete: the image bytes leave storage, along with
the analyses, lesions, laboratory panels, foot assessments, filed reports and
follow-up answers derived from them. A soft delete would leave the photographs
— the only genuinely identifying material held — sitting behind a flag.

The pseudonymous patient record is **not** deleted; that is a different request
(`DELETE /patients/{ref}`), and other cases may still reference them. The audit
trail survives, because a system that can erase the record of its own erasures
is not auditable — and it holds no patient identifier and no clinical content.

### Offline

After one successful online visit the interface opens with no connection.
Captures, patient records, foot examinations and follow-up answers are queued
in IndexedDB and
drained **strictly in order** when connectivity returns — a case needs its
patient to exist and an analysis needs its case, so a dependency is written as
a `{$ref:localId}` placeholder that is rewritten *in the database* when its
owner syncs. On the first rejection the drain stops rather than skipping ahead.
Queued items are never discarded automatically; the count is always on screen
and discarding is an explicit, confirmed action.

### Tests

```bash
cd api && .venv/Scripts/python -m pytest -q
```

328 tests: every module's expected grade and routing on its synthetic sample,
quality-gate rejection, resolution invariance, auth, consent, audit, erasure,
organisational isolation, colour calibration (and every way it must refuse),
case deletion, the clinical layer (no single-item differentials, no treatment
instructions), the follow-up rule that answers may never lower a grade, and the
safety boundary.

---

## 3. Architecture

```
                         ┌───────────────────────────────────────────┐
  camera / upload        │  web  (React + TS + Vite, EN/AR RTL)      │
  ────────────────────▶  │  capture guidance · triage card · overlay │
                         │  next-step block · PDF · case history     │
                         └────────────────────┬──────────────────────┘
                                              │  same-origin /api/v1, JWT bearer
                         ┌────────────────────▼──────────────────────┐
                         │  api  (FastAPI, async, Pydantic v2)       │
                         │  auth · patients · cases · admin          │
                         └──┬──────────────┬───────────────┬─────────┘
                            │              │               │
             ┌──────────────▼──┐   ┌───────▼────────┐   ┌──▼──────────────┐
             │ AnalysisRunner  │   │  SQLAlchemy    │   │ StorageBackend  │
             │ inline │ queue  │   │  + Alembic     │   │  s3 │ local     │
             └────────┬────────┘   └───────┬────────┘   └──┬──────────────┘
                      │                    │               │
        ┌─────────────▼──────────┐   ┌─────▼─────┐   ┌─────▼──────────────┐
        │ pipeline.execute()     │   │ Postgres  │   │ MinIO / S3         │
        │  1 quality gate        │   │ 8 tables  │   │ images + overlays  │
        │  2 ModelBackend.analyze│   └───────────┘   └────────────────────┘
        │  3 overlay render      │
        └─────────────┬──────────┘
                      │
        ┌─────────────▼──────────────────────────────┐
        │ ModelBackend (Protocol)                    │
        │   ClassicalCVBackend  ← active default     │
        │   OnnxBackend         ← trained model slot │
        └────────────────────────────────────────────┘
```

Request path for `POST /cases/{id}/analyze`:

```
upload → consent check → size/type check → model_registry lookup
       → runner.run(job)              (CPU work off the event loop)
           → quality gate ──fail──▶ 422 + re-capture hints, NOTHING STORED
           → module analysis
           → annotated overlay
       → store image + overlay in object storage (keys only in the DB)
       → persist analysis + lesions → audit row → response
```

### Layout

```
api/
  app/
    safety.py            the boundary; every disclaimer has one source
    config.py            12-factor settings
    models.py            14 tables (organisations, users, patients, cases,
                         images, analyses, lesions, lab_panels, lab_results,
                         foot_risk_assessments, case_follow_ups,
                         investigation_results, model_registry, audit_log)
    schemas.py           Pydantic v2 request/response contracts
    security.py          argon2 hashing, JWT
    storage.py           StorageBackend: S3Storage | LocalStorage
    audit.py             append-only trail, PHI scrubbing
    summary.py           structured clinician summary
    pdf.py               reportlab export
    sample_data.py       deterministic synthetic images
    seed.py              demo users, registry, cases
    analysis/
      types.py           Lesion, Triage, ModuleResult, QualityReport
      modules_config.py  module catalogue + grade→routing map (CONFIG)
      quality.py         shared quality gate
      calibration.py     colour correction from a reference card in frame
      followup.py        the questions a camera cannot answer, and their rules
      cv_utils.py        subject segmentation and shared measurements
      overlay.py         annotated overlay with burned-in disclaimer
      pipeline.py        pure sync pipeline (queue-portable)
      runner.py          InlineRunner | QueueRunner seam
      backends/
        base.py          ModelBackend Protocol
        classical.py     OpenCV placeholder, all four modules
        onnx.py          ONNX Runtime slot
  alembic/               migrations (incl. Postgres append-only audit trigger)
  tests/                 328 tests
web/src/                 React app, i18n EN/AR with RTL
```

---

## 4. API

All under `/api/v1`. Errors are structured: `{"error": {code, message, hint,
details}}`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/login` | OAuth2 password flow → JWT |
| `GET` | `/auth/me` | current user |
| `GET` | `/health` | `{status, clinical_use:false, …}` |
| `GET` | `/safety` | the boundary, machine-readable |
| `GET` | `/modules` | catalogue + full routing map + limitations |
| `POST` | `/patients` | create pseudonymous record + consent |
| `PATCH` | `/patients/{ref}` | update consent / skin tone |
| `GET` | `/patients/{ref}/export` | portability: everything held |
| `DELETE` | `/patients/{ref}` | right to erasure (audit retained) |
| `POST` | `/cases` | create case (`module`, `patient_ref`) |
| `POST` | `/cases/{id}/analyze` | multipart image → full result + base64 overlay |
| `GET` | `/labs/catalogue` | analyte definitions and accepted units |
| `POST` | `/labs/interpret` | stateless interpretation of typed values |
| `POST` | `/cases/{id}/labs` | attach a panel to any case and store it |
| `GET` | `/cases/{id}/labs` | panels stored against the case |
| `POST` | `/cases/{id}/investigations` | file a report/scan against a case — never interpreted |
| `GET` | `/cases/{id}/investigations` | results filed against the case |
| `GET` | `/cases/{id}/investigations/{rid}/file` | the stored document |
| `GET` | `/follow-up/questions/{module}` | the question set, published |
| `POST` | `/cases/{id}/follow-up` | clinician answers + free note → re-assessed grade |
| `GET` | `/cases/{id}/follow-up` | answers recorded against the case |
| `GET` | `/cases/{id}` | case + latest analysis + history |
| `DELETE` | `/cases/{id}?confirm=true` | permanent deletion (audit retained) |
| `GET` | `/cases` | filter by `module`, `patient_ref`, `grade`; paginated |
| `GET` | `/cases/{id}/analyses/{aid}/overlay.png` | annotated image |
| `GET` | `/cases/{id}/summary.pdf` | clinician summary PDF |
| `GET` | `/admin/fairness` | stratified reporting (admin, own organisation only) |
| `GET` | `/admin/models` · `POST /admin/models/{id}/activate` | model registry |
| `GET` | `/admin/audit` | audit trail (admin) |

Every mutating action writes an `audit_log` row. Overlays are fetched with the
bearer token and turned into object URLs in the browser, so no credential ever
appears in a URL.

---

## 5. How a trained model slots in

The seam is one method:

```python
class ModelBackend(Protocol):
    name: str
    version: str
    def supports(self, module: str) -> bool: ...
    def analyze(self, image_bgr, module: str, quality: QualityReport) -> ModuleResult: ...
```

`ModuleResult = {lesions: [Lesion], triage: Triage, features: {...}}`.

To activate a trained model for a module:

1. Implement `OnnxBackend._postprocess` in `api/app/analysis/backends/onnx.py`
   for that model's output heads. Return **surface findings and a triage grade
   only**.
2. `pip install -r api/requirements-onnx.txt` and put the `.onnx` artifact
   somewhere the API can read.
3. Insert a `model_registry` row: `module`, `name`, `version`,
   `backend='onnx'`, `artifact_uri`, `metrics_json`.
4. `POST /api/v1/admin/models/{id}/activate`.

Nothing else changes — not the API contract, not the database schema, not the
UI. `test_model_backend_seam.py` asserts this, including that a missing
artifact degrades to the classical placeholder (with the fallback stated in the
response) rather than taking the module offline.

**The routing text always comes from `modules_config.py`, never from the
model.** A model may propose a grade; it may not invent what test to order.

### What the placeholder actually does

`ClassicalCVBackend` measures surface colour, area and outline statistics in
LAB space inside the segmented subject region: erythema / slough / dark tissue
for foot, pigment + border irregularity + asymmetry + colour count for skin,
scleral b\* (yellow) and a\* (red) for eye, bruise colour shift + outline
asymmetry + contour solidity for injury. Thresholds are **relative to the
subject's own colour statistics** with a small absolute floor, so a fixed cut
does not behave systematically differently across skin tones. That is a
mitigation, not a validation.

---

## 6. Fairness, privacy, compliance

**Skin tone.** Monk Skin Tone (1–10) is optional, patient-declared, and is
**never a model input** — it exists so results can be reported per group.
`GET /admin/fairness` returns counts, mean reported confidence and quality
pass rate stratified into MST bands, and says plainly that these are counts of
platform output, not measured accuracy: there is no ground truth in this
system. A single pooled number is never produced, because pooling hides exactly
the disparity that matters.

**Privacy.**

* Patients are pseudonymous: a site-local `external_ref`, optional birth year,
  sex and skin tone. No name, MRN or contact detail is stored, and the API
  rejects references that look like an email or a full name.
* Consent is required before any image is stored — without it `/analyze`
  returns `403 consent_required` and nothing is written.
* An image that fails the quality gate is **not stored at all**.
* Images live in object storage under content-addressed keys that carry no
  patient identifier; only the key is in the database.
* Right to erasure (`DELETE /patients/{ref}`) removes every image, overlay and
  clinical row. The audit trail is retained — it holds no identifiers.
* Logs are filtered for emails, id-like numbers and inline images; audit meta is
  scrubbed of anything that looks like PHI or image bytes.
* TLS in transit and encryption at rest are deployment concerns: terminate TLS
  at the ingress, enable bucket SSE and Postgres disk encryption. Data
  residency is configurable (`DATA_RESIDENCY`, `S3_REGION`, default UAE).

**Regulatory framing.** Treat as SaMD. Human-in-the-loop is structural: every
export carries a clinician confirmation line. The intended-use string is
surfaced in the UI footer, the API (`/safety`) and every PDF. Aligns to the
transparency, accountability and audit expectations of the UAE EDE
medical-device framework and DHA AI-in-healthcare guidance. **No regulatory
clearance is claimed, and none exists.**

---

## 7. Known gaps — read before demoing

* **The model is a placeholder.** Rule-based descriptors, tuned against
  synthetic drawings. No training data, no clinical validation, no measured
  sensitivity or specificity. It has never been tested on a real photograph of
  a real patient.
* **The synthetic samples are not evidence.** They exist to exercise the
  pipeline. Passing tests means the plumbing works, not that the screening
  works.
* **Clinical text is English only.** The UI chrome is bilingual EN/AR with full
  RTL, and module names and descriptions are translated — but routing text,
  rationale and limitations stay in English until a clinician reviews an Arabic
  translation. Mistranslated routing advice is worse than untranslated advice.
* **The queue runner is a stub.** `ANALYSIS_RUNNER=queue` raises
  `NotImplementedError`; inline is the working path.
* **Quality thresholds are engineering defaults, not clinical ones.** Focus is
  measured at a normalised 480 px short side so the threshold means the same
  thing on a phone and on a laptop, but the numbers themselves have not been
  set against clinician judgements of which photographs are usable.
* **The fairness dashboard is a placeholder** and says so — counts only.
* **`docker compose up` has not been executed in this environment** (no Docker
  installed on the build machine). The SQLite + local-storage path, the API,
  the web app and all 81 tests were run and verified; the compose file, both
  Dockerfiles and the nginx config are written but unexercised.
