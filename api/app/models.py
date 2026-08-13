from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Organisation(Base):
    """A clinic, hospital or programme. The isolation boundary.

    Every user and every patient belongs to exactly one. Nothing crosses:
    a request for another organisation's case answers 404, not 403, because
    403 would confirm the case exists.
    """

    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="clinician")  # clinician|admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Patient(Base):
    """Pseudonymous. No name, no MRN, no contact details are stored -- the
    external_ref is a site-local code the clinic can resolve, we cannot."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), index=True
    )
    # Unique WITHIN an organisation, not globally. A global unique index would
    # let one clinic discover another's patient codes by collision.
    external_ref: Mapped[str] = mapped_column(String(64), index=True)
    dob_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Monk Skin Tone 1-10. Optional, patient-declared, used only for stratified
    # fairness reporting -- never as an analysis input.
    skin_tone_monk: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consent_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    cases: Mapped[list["Case"]] = relationship(back_populates="patient")

    __table_args__ = (
        UniqueConstraint("organisation_id", "external_ref",
                         name="uq_patient_org_ref"),
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # created | analyzed | quality_failed
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    body_site: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped[Patient] = relationship(back_populates="cases")
    images: Mapped[list["Image"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class Image(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict)

    case: Mapped[Case] = relationship(back_populates="images")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("images.id"), index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    backend: Mapped[str] = mapped_column(String(32), default="classical_cv")
    triage_grade: Mapped[str] = mapped_column(String(16), index=True)
    triage_label: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float)
    next_investigation: Mapped[str] = mapped_column(Text)
    rationale_json: Mapped[dict] = mapped_column(JSON, default=dict)
    overlay_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    case: Mapped[Case] = relationship(back_populates="analyses")
    lesions: Mapped[list["Lesion"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class Lesion(Base):
    __tablename__ = "lesions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    area_pct: Mapped[float] = mapped_column(Float)
    severity: Mapped[float] = mapped_column(Float)
    bbox_json: Mapped[dict] = mapped_column(JSON, default=dict)
    centroid_json: Mapped[dict] = mapped_column(JSON, default=dict)

    analysis: Mapped[Analysis] = relationship(back_populates="lesions")


class LabPanel(Base):
    """A set of numeric results interpreted together, attached to a case.

    Deliberately separate from `analyses`: a lab panel has no image, no quality
    gate and no model, and forcing it through a table built around those would
    mean nullable columns that lie about what happened.
    """

    __tablename__ = "lab_panels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    panel_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    collected_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    age_at_collection: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex_used: Mapped[str | None] = mapped_column(String(16), nullable=True)
    triage_grade: Mapped[str] = mapped_column(String(16), index=True)
    triage_label: Mapped[str] = mapped_column(String(128))
    next_investigation: Mapped[str] = mapped_column(Text)
    # derived indices, differentials, actions, rationale
    interpretation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    results: Mapped[list["LabResult"]] = relationship(
        back_populates="panel", cascade="all, delete-orphan"
    )


class LabResult(Base):
    """One analyte. Stored in the CANONICAL unit with the submitted value kept
    alongside, so a later reader can see exactly what was typed in."""

    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    panel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lab_panels.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    submitted_value: Mapped[float] = mapped_column(Float)
    submitted_unit: Mapped[str] = mapped_column(String(24))
    flag: Mapped[str] = mapped_column(String(16), index=True)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)

    panel: Mapped[LabPanel] = relationship(back_populates="results")


class FootRiskAssessment(Base):
    """A structured diabetic foot examination and its IWGDF risk category.

    The findings are what a clinician measured with a monofilament and their
    fingers, not what a camera saw. `category` is null when a required test was
    not performed -- the assessment refuses to stratify rather than assuming a
    missing test was negative.
    """

    __tablename__ = "foot_risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    foot: Mapped[str] = mapped_column(String(16))          # left | right | both
    # present | absent | not_tested
    lops: Mapped[str] = mapped_column(String(16))
    pad: Mapped[str] = mapped_column(String(16))
    deformity: Mapped[str] = mapped_column(String(16))
    previous_ulcer: Mapped[str] = mapped_column(String(16))
    previous_amputation: Mapped[str] = mapped_column(String(16))
    end_stage_renal_disease: Mapped[str] = mapped_column(String(16))
    category: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    complete: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    screening_interval: Mapped[str] = mapped_column(String(128))
    grade: Mapped[str] = mapped_column(String(16), index=True)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CaseFollowUp(Base):
    """Clinician answers to the questions the camera cannot answer.

    Stored against the analysis they refine, so the record shows what was known
    at the time rather than a moving present-tense view. `combined_grade` is
    always at least as urgent as `image_grade`: answers escalate, never
    de-escalate. See analysis/followup.py for why that asymmetry is deliberate.

    `note` is free text written by the clinician. It is displayed and exported
    verbatim and is never parsed, scored, or fed to any model.
    """

    __tablename__ = "case_follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id"), nullable=True, index=True
    )
    module: Mapped[str] = mapped_column(String(32), index=True)
    image_grade: Mapped[str] = mapped_column(String(16), index=True)
    answer_grade: Mapped[str] = mapped_column(String(16), index=True)
    combined_grade: Mapped[str] = mapped_column(String(16), index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    answers_json: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome_json: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InvestigationResult(Base):
    """The result of an investigation QADAM routed the patient to.

    STORED, NEVER INTERPRETED. No model reads these files and no grade is
    produced from them. QADAM says "obtain an X-ray"; this is where the X-ray
    report comes back, so the referral stops trailing off into nothing. Reading
    a radiology study needs the whole study, the clinical context, priors, and
    a trained reporter — none of which a triage app has.
    """

    __tablename__ = "investigation_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    # radiology | endoscopy | histopathology | other
    category: Mapped[str] = mapped_column(String(32), index=True)
    # x-ray | ultrasound | ct | mri | other
    modality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body_site: Mapped[str | None] = mapped_column(String(64), nullable=True)
    performed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The reporting SERVICE, never a named individual.
    reporting_service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional file. The original filename is deliberately discarded -- it
    # routinely carries the patient's name.
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The uploader's explicit confirmation that identifiers were removed from
    # the document before it entered a pseudonymous record.
    identifiers_removed_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    module: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64))
    backend: Mapped[str] = mapped_column(String(32))  # classical_cv | onnx
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_model_registry_module_active", "module", "active"),)


class AuditLog(Base):
    """Append-only. Nothing in the application updates or deletes these rows;
    patient erasure removes images and clinical rows but keeps the audit trail,
    which holds no identifiers."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
