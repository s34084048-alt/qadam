"""Clinician answers to the questions a photograph cannot answer.

The clinical layer has always printed "check the pulses, test with a
monofilament, ask how long it has been there". Those prompts went nowhere. This
router lets the answers come back in, records them against the analysis they
refine, and re-runs the routing decision with them included.

Answers escalate; they never de-escalate. The reasoning is in
analysis/followup.py -- in short, the image grade comes from a measurement and
the answers are unverified self-report, so allowing reassurance to overwrite a
measured flag would create a one-click path to dismissing it.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from .. import audit
from ..analysis import followup
from ..analysis.modules_config import GRADE_STYLE, routing_for
from ..analysis.types import Grade
from ..deps import CurrentUser, SessionDep, load_case_scoped
from ..errors import ApiError
from ..models import Analysis, Case, CaseFollowUp
from ..safety import safety_block
from ..schemas import FollowUpCreate, FollowUpListOut, FollowUpOut

router = APIRouter(prefix="/cases", tags=["follow-up"])
info_router = APIRouter(prefix="/follow-up", tags=["follow-up"])


@info_router.get("/questions/{module}")
async def module_questions(module: str, user: CurrentUser) -> dict[str, Any]:
    """The question set for a module, published rather than hidden in the UI."""
    questions = followup.questions_for(module)
    if not questions:
        raise ApiError(
            404, "no_follow_up_questions",
            f"No follow-up question set is defined for module '{module}'.",
            hint="Follow-up questions exist for: "
                 + ", ".join(sorted(followup.QUESTIONS)),
        )
    return {
        "module": module,
        "questions": [q.to_json() for q in questions],
        "combination_rule": (
            "The combined grade is the more urgent of the image grade and the "
            "answer grade. Answers raise urgency and never lower it."
        ),
        "answers_are_not_measurements": (
            "Everything recorded here is entered by a clinician and is stored "
            "as reported. QADAM does not verify it and does not measure it."
        ),
        "safety": safety_block(module),
    }


async def _latest_analysis(session, case: Case) -> Analysis | None:
    result = await session.execute(
        select(Analysis).where(Analysis.case_id == case.id)
        .order_by(Analysis.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


def _out(row: CaseFollowUp) -> FollowUpOut:
    spec = routing_for(row.module, row.combined_grade)
    return FollowUpOut(
        id=row.id,
        case_id=row.case_id,
        analysis_id=row.analysis_id,
        module=row.module,
        image_grade=row.image_grade,
        answer_grade=row.answer_grade,
        combined_grade=row.combined_grade,
        combined_label=spec["label"],
        combined_color=GRADE_STYLE[row.combined_grade]["color"],
        escalated=row.escalated,
        answers=row.answers_json or {},
        outcome=row.outcome_json or {},
        note=row.note,
        created_at=row.created_at,
        created_by=row.created_by,
        safety=safety_block(row.module, row.combined_grade),
    )


@router.post("/{case_id}/follow-up", response_model=FollowUpOut, status_code=201)
async def add_follow_up(
    case_id: uuid.UUID,
    body: FollowUpCreate,
    session: SessionDep,
    user: CurrentUser,
) -> FollowUpOut:
    case = await load_case_scoped(session, case_id, user)

    if case.module not in followup.QUESTIONS:
        raise ApiError(
            400, "no_follow_up_questions",
            f"Module '{case.module}' has no follow-up question set.",
            hint="Follow-up questions exist for: "
                 + ", ".join(sorted(followup.QUESTIONS)),
        )

    analysis: Analysis | None
    if body.analysis_id is not None:
        analysis = await session.get(Analysis, body.analysis_id)
        # Scoped through the case: an analysis id from another organisation
        # must not confirm its own existence.
        if analysis is None or analysis.case_id != case.id:
            raise ApiError(
                404, "analysis_not_found",
                "No analysis with that id belongs to this case.",
                hint="Omit analysis_id to attach the answers to the most "
                     "recent analysis.",
            )
    else:
        analysis = await _latest_analysis(session, case)

    # Answers can be recorded before any image is taken. With no analysis the
    # image contributes nothing, so the routing rests entirely on the answers.
    image_grade = (
        Grade(analysis.triage_grade) if analysis is not None else Grade.NO_FLAG
    )

    try:
        outcome = followup.evaluate(case.module, image_grade, body.answers)
    except followup.UnknownFollowUpField as exc:
        raise ApiError(
            400, "unknown_follow_up_field",
            f"'{exc.field_id}' is not a follow-up question for the "
            f"'{exc.module}' module.",
            hint="Call GET /api/v1/follow-up/questions/"
                 f"{exc.module} for the question set. Unknown fields are "
                 "rejected rather than dropped, so an answer is never silently "
                 "lost.",
            details={"allowed": exc.allowed},
        )
    except followup.InvalidFollowUpAnswer as exc:
        raise ApiError(
            400, "invalid_follow_up_answer",
            f"'{exc.value}' is not an accepted answer for '{exc.field_id}'.",
            hint="Accepted values: " + ", ".join(str(a) for a in exc.allowed),
            details={"field": exc.field_id, "allowed": exc.allowed},
        )

    note = (body.note or "").strip() or None
    row = CaseFollowUp(
        case_id=case.id,
        analysis_id=analysis.id if analysis is not None else None,
        module=case.module,
        image_grade=str(outcome.image_grade),
        answer_grade=str(outcome.answer_grade),
        combined_grade=str(outcome.combined_grade),
        escalated=outcome.escalated,
        answers_json=outcome.answered,
        outcome_json=outcome.to_json(),
        note=note,
        created_by=user.id,
    )
    session.add(row)
    await session.flush()

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id,
        action="follow_up.create", entity="case_follow_up", entity_id=row.id,
        # Deliberately no answer values and no note text: the note is free
        # clinical prose and the audit log holds no clinical content.
        meta={
            "case_id": str(case.id),
            "module": case.module,
            "image_grade": row.image_grade,
            "combined_grade": row.combined_grade,
            "escalated": row.escalated,
            "answered_count": len(outcome.answered),
            "has_note": note is not None,
        },
    )
    await session.commit()
    await session.refresh(row)
    return _out(row)


@router.get("/{case_id}/follow-up", response_model=FollowUpListOut)
async def list_follow_up(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> FollowUpListOut:
    case = await load_case_scoped(session, case_id, user)
    rows = (await session.execute(
        select(CaseFollowUp).where(CaseFollowUp.case_id == case.id)
        .order_by(CaseFollowUp.created_at.desc())
    )).scalars().all()

    return FollowUpListOut(
        case_id=case.id,
        module=case.module,
        questions=[q.to_json() for q in followup.questions_for(case.module)],
        entries=[_out(row) for row in rows],
        total=len(rows),
    )
