from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Grade = Literal["no_flag", "monitor", "review", "urgent"]
ModuleId = Literal["foot", "lab"]


# --- auth --------------------------------------------------------------------

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    email: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    role: str
    created_at: dt.datetime


# --- patients ----------------------------------------------------------------

class PatientCreate(BaseModel):
    external_ref: str = Field(
        min_length=1, max_length=64,
        description="Site-local pseudonymous code. Never a name or an MRN.",
    )
    dob_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: Literal["female", "male", "other", "unknown"] | None = None
    skin_tone_monk: int | None = Field(
        default=None, ge=1, le=10,
        description="Monk Skin Tone 1-10, patient-declared. Used only for "
                    "stratified fairness reporting, never as a model input.",
    )
    consent_flag: bool = Field(
        default=False,
        description="Patient consent to store and analyse images. Required "
                    "before any image is stored.",
    )

    @field_validator("external_ref")
    @classmethod
    def _no_obvious_identifier(cls, v: str) -> str:
        looks_like_email = "@" in v
        looks_like_full_name = len(v.split()) > 2
        if looks_like_email or looks_like_full_name:
            raise ValueError(
                "external_ref must be a pseudonymous code, not an email or name"
            )
        return v.strip()


class PatientUpdate(BaseModel):
    dob_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: Literal["female", "male", "other", "unknown"] | None = None
    skin_tone_monk: int | None = Field(default=None, ge=1, le=10)
    consent_flag: bool | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    external_ref: str
    dob_year: int | None
    sex: str | None
    skin_tone_monk: int | None
    consent_flag: bool
    created_at: dt.datetime


# --- cases -------------------------------------------------------------------

class CaseCreate(BaseModel):
    module: ModuleId
    patient_ref: str = Field(min_length=1, max_length=64)
    body_site: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class LesionOut(BaseModel):
    id: uuid.UUID
    kind: str
    area_pct: float
    severity: float
    bbox: dict[str, int]
    centroid: dict[str, int]
    description: str = ""


class TriageOut(BaseModel):
    grade: Grade
    label: str
    confidence: float
    rationale: list[str]
    next_investigation: str
    urgency: str
    routing_target: str
    color: str


class QualityOut(BaseModel):
    passed: bool
    width: int
    height: int
    subject_fraction: float
    focus_var: float
    exposure_mean: float
    confidence_factor: float
    checks: list[dict[str, Any]]
    hints: list[str]


class AnalysisOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    image_id: uuid.UUID
    module: ModuleId
    model_version: str
    backend: str
    created_at: dt.datetime
    triage: TriageOut
    lesions: list[LesionOut]
    quality: QualityOut
    features: dict[str, Any] = {}
    clinical: dict[str, Any] | None = None
    overlay_png_base64: str | None = None
    summary: str
    safety: dict[str, Any]


class CaseOut(BaseModel):
    id: uuid.UUID
    module: ModuleId
    patient_ref: str
    status: str
    body_site: str | None
    note: str | None
    created_at: dt.datetime
    created_by: uuid.UUID
    latest_analysis: AnalysisOut | None = None
    history: list[AnalysisOut] = []
    # THE decision for this case, from the examination and the answers. The
    # photograph is not an input — see app/routing.py. `latest_analysis` is
    # the record of what was photographed, not the routing.
    routing: dict[str, Any] = {}


class CaseListItem(BaseModel):
    id: uuid.UUID
    module: ModuleId
    patient_ref: str
    status: str
    created_at: dt.datetime
    triage_grade: Grade | None = None
    triage_label: str | None = None
    confidence: float | None = None
    analysis_count: int = 0


class CaseListOut(BaseModel):
    items: list[CaseListItem]
    total: int
    limit: int
    offset: int


# --- follow-up ---------------------------------------------------------------

class FollowUpCreate(BaseModel):
    """Answers to the module's follow-up questions, plus a free-text note.

    `analysis_id` ties the answers to the analysis they refine. Omitted, they
    attach to the most recent analysis on the case.
    """

    answers: dict[str, Any] = Field(
        default_factory=dict,
        description="question id -> answer. Unknown ids are rejected rather "
                    "than ignored: a silently dropped answer means the record "
                    "does not say what the clinician reported.",
    )
    note: str | None = Field(
        default=None, max_length=4000,
        description="Free clinical text. Stored and displayed verbatim; never "
                    "parsed, scored, or used as a model input.",
    )
    analysis_id: uuid.UUID | None = None


class FollowUpOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    analysis_id: uuid.UUID | None
    module: ModuleId
    # Recorded, never routed on. See app/routing.py.
    image_grade: Grade
    answer_grade: Grade
    answer_label: str
    answer_color: str
    triggered: bool
    answers: dict[str, Any]
    outcome: dict[str, Any]
    note: str | None
    created_at: dt.datetime
    created_by: uuid.UUID
    safety: dict[str, Any]


class FollowUpListOut(BaseModel):
    case_id: uuid.UUID
    module: ModuleId
    questions: list[dict[str, Any]]
    entries: list[FollowUpOut]
    total: int


class CaseDeleteOut(BaseModel):
    """What a deletion actually removed, itemised.

    Returned rather than a bare 204 so the clinician sees the scope of what
    they just destroyed, and so the count can be checked against expectation.
    """

    case_id: uuid.UUID
    deleted: dict[str, int]
    images_removed: int
    audit_retained: bool = True
    note: str


# --- feedback ----------------------------------------------------------------

class FeedbackCreate(BaseModel):
    """What the clinician saw, against what was reported."""

    analysis_id: uuid.UUID
    verdict: str = Field(
        description="agree | too_high | too_low | unusable_image",
    )
    ground_truth: str | None = Field(
        default=None,
        description="What was actually there: intact_skin | callus | "
                    "open_ulcer | eschar | other | not_sure.",
    )
    note: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    analysis_id: uuid.UUID
    reported_grade: Grade
    model_version: str
    # NULL on rows written before the evidence layer existed. Nullable rather
    # than defaulted: "nothing was capped because nothing could be" and "the
    # grade was not capped" are different facts, and a default would erase the
    # difference.
    evidence_ceiling: Grade | None = None
    grade_capped: bool | None = None
    verdict: str
    verdict_label: str
    ground_truth: str | None
    ground_truth_label: str | None
    note: str | None
    created_at: dt.datetime
    created_by: uuid.UUID


class FeedbackListOut(BaseModel):
    case_id: uuid.UUID
    verdicts: dict[str, str]
    ground_truth_options: dict[str, str]
    entries: list[FeedbackOut]
    total: int
    note: str


# --- misc --------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str
    clinical_use: bool
    version: str
    environment: str
    # Tells the client whether to offer one-click access. The server is
    # the authority on this; the UI must not decide it locally.
    demo_mode: bool = False
    disclaimer: str
    device_notice: str


class ModelRegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: uuid.UUID
    module: str
    name: str
    version: str
    backend: str
    active: bool
    artifact_uri: str | None
    metrics_json: dict[str, Any]
    created_at: dt.datetime
