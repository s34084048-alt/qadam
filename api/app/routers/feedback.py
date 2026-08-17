"""Recorded disagreement: what the clinician saw, against what was reported.

This is the validation dataset being built one row at a time.

Every threshold in this platform was tuned on synthetic images, and synthetic
images have misled it repeatedly. Every real defect it has ever had — a healthy
toe called necrotic, a shadow read as tissue, callus counted as a wound, a
timezone crash — was found by a person looking at a real photograph, not by a
test suite that now runs to nearly four hundred cases. Nothing changes that
except recorded disagreement from people holding real feet.

IT CHANGES NOTHING LIVE. No grade moves because feedback was left and no
threshold adapts. A system that retunes itself on unvalidated corrections is a
system whose behaviour nobody can state — least of all to a regulator.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from .. import audit
from ..deps import AdminUser, CurrentUser, SessionDep, load_case_scoped
from ..errors import ApiError
from ..models import Analysis, AnalysisFeedback
from ..safety import safety_block
from ..schemas import FeedbackCreate, FeedbackListOut, FeedbackOut

router = APIRouter(prefix="/cases", tags=["feedback"])
admin_router = APIRouter(prefix="/admin", tags=["feedback"])

VERDICTS = {
    "agree": "The reported result matched what I saw.",
    "too_high": "It was more alarming than what I saw.",
    "too_low": "It was less alarming than what I saw.",
    "unusable_image": "The photograph could not be judged either way.",
}

GROUND_TRUTH = {
    "intact_skin": "Intact skin — nothing on the surface.",
    "callus": "Callus or thickened keratin over intact skin.",
    "open_ulcer": "An open ulcer — the skin is broken through.",
    "eschar": "Eschar or dry necrotic tissue.",
    "other": "Something else.",
    "not_sure": "Not sure from what I could see.",
}


def _stored_features(analysis) -> dict:
    """The features exactly as they were persisted with this analysis.

    Deliberately NOT recomputed. The point of the column is what the clinician
    was actually shown; re-running today's code against yesterday's image would
    record the wrong thing and quietly destroy the only evidence that the
    behaviour ever changed.
    """
    return (analysis.rationale_json or {}).get("features", {}) or {}


def _out(row: AnalysisFeedback) -> FeedbackOut:
    return FeedbackOut(
        id=row.id,
        case_id=row.case_id,
        analysis_id=row.analysis_id,
        reported_grade=row.reported_grade,
        model_version=row.model_version,
        evidence_ceiling=row.evidence_ceiling,
        grade_capped=row.grade_capped,
        verdict=row.verdict,
        verdict_label=VERDICTS.get(row.verdict, row.verdict),
        ground_truth=row.ground_truth,
        ground_truth_label=GROUND_TRUTH.get(row.ground_truth or "", None),
        note=row.note,
        created_at=row.created_at,
        created_by=row.created_by,
    )


@router.get("/{case_id}/feedback", response_model=FeedbackListOut)
async def list_feedback(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> FeedbackListOut:
    case = await load_case_scoped(session, case_id, user)
    rows = (await session.execute(
        select(AnalysisFeedback).where(AnalysisFeedback.case_id == case.id)
        .order_by(AnalysisFeedback.created_at.desc())
    )).scalars().all()
    return FeedbackListOut(
        case_id=case.id,
        verdicts=VERDICTS,
        ground_truth_options=GROUND_TRUTH,
        entries=[_out(r) for r in rows],
        total=len(rows),
        note=("Recorded for validation. Nothing here changes a grade, now or "
              "later — no threshold adapts to it."),
    )


@router.post("/{case_id}/feedback", response_model=FeedbackOut, status_code=201)
async def add_feedback(
    case_id: uuid.UUID,
    body: FeedbackCreate,
    session: SessionDep,
    user: CurrentUser,
) -> FeedbackOut:
    case = await load_case_scoped(session, case_id, user)

    if body.verdict not in VERDICTS:
        raise ApiError(
            400, "unknown_verdict", f"'{body.verdict}' is not a verdict.",
            hint="Use one of: " + ", ".join(sorted(VERDICTS)),
        )
    if body.ground_truth and body.ground_truth not in GROUND_TRUTH:
        raise ApiError(
            400, "unknown_ground_truth",
            f"'{body.ground_truth}' is not a recognised finding.",
            hint="Use one of: " + ", ".join(sorted(GROUND_TRUTH)),
        )

    analysis = await session.get(Analysis, body.analysis_id)
    if analysis is None or analysis.case_id != case.id:
        raise ApiError(
            404, "analysis_not_found",
            "No analysis with that id belongs to this case.",
            hint="Feedback is left against a specific result, so the image and "
                 "its measurements can be looked at later alongside it.",
        )

    row = AnalysisFeedback(
        case_id=case.id,
        analysis_id=analysis.id,
        # Copied, not joined: the row must still mean something after a
        # re-analysis or a threshold change.
        reported_grade=analysis.triage_grade,
        model_version=analysis.model_version,
        # What the evidence layer allowed, beside what the areas said. Read
        # from the stored analysis so it is the ceiling that was actually in
        # force when the clinician looked, not whatever the code does today.
        evidence_ceiling=_stored_features(analysis).get("evidence", {}).get("ceiling"),
        grade_capped=_stored_features(analysis).get("grade_capped_by_evidence"),
        verdict=body.verdict,
        ground_truth=body.ground_truth,
        note=(body.note or "").strip() or None,
        created_by=user.id,
    )
    session.add(row)
    await session.flush()

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id,
        action="feedback.create", entity="analysis_feedback", entity_id=row.id,
        meta={"case_id": str(case.id), "verdict": row.verdict,
              "reported_grade": row.reported_grade,
              "ground_truth": row.ground_truth,
              "model_version": row.model_version},
    )
    await session.commit()
    await session.refresh(row)
    return _out(row)


@admin_router.get("/feedback")
async def feedback_summary(
    session: SessionDep,
    user: AdminUser,
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    """The dataset so far, and the only honest performance statement available.

    Scoped to the administrator's own organisation like everything else.
    """
    rows = (await session.execute(
        select(AnalysisFeedback)
        .join(Analysis, Analysis.id == AnalysisFeedback.analysis_id)
        .order_by(AnalysisFeedback.created_at.desc())
        .limit(limit)
    )).scalars().all()

    by_verdict: dict[str, int] = {}
    matrix: dict[str, dict[str, int]] = {}
    # The question the evidence layer created: when it lowered a grade, was it
    # right to? Split so a "too_low" report can be attributed to the cap rather
    # than to the thresholds.
    capped: dict[str, int] = {"capped": 0, "not_capped": 0, "unrecorded": 0}
    missed_after_cap = 0
    for row in rows:
        by_verdict[row.verdict] = by_verdict.get(row.verdict, 0) + 1
        truth = row.ground_truth or "unrecorded"
        matrix.setdefault(row.reported_grade, {})
        matrix[row.reported_grade][truth] = (
            matrix[row.reported_grade].get(truth, 0) + 1
        )
        key = ("unrecorded" if row.grade_capped is None
               else "capped" if row.grade_capped else "not_capped")
        capped[key] += 1
        if row.grade_capped and row.verdict == "too_low":
            missed_after_cap += 1

    total = len(rows)
    return {
        "total": total,
        "by_verdict": by_verdict,
        "reported_grade_vs_ground_truth": matrix,
        "evidence_cap": {
            "counts": capped,
            "too_low_on_a_capped_grade": missed_after_cap,
            "why_this_split_exists": (
                "The evidence layer can lower a grade the measured areas alone "
                "would have raised. That closed a reproduced false positive, "
                "and the risk of any such change is that it opens a false "
                "negative. 'too_low' on a CAPPED grade is a report that the cap "
                "was wrong; 'too_low' on an uncapped one is a report about the "
                "thresholds. They need different fixes."
            ),
            "not_a_rate": (
                "A count, not a rate. The denominator is whoever chose to leave "
                "feedback, which is not a sample of anything."
            ),
        },
        "verdicts": VERDICTS,
        "ground_truth_options": GROUND_TRUTH,
        "what_this_is_not": (
            "Not a validation study. These are opportunistic reports from "
            "whoever happened to use the demo, on images nobody selected, with "
            "no protocol and no independent adjudication. It shows where the "
            "platform is wrong; it cannot state how often it is right."
        ),
        "what_would_make_it_one": (
            "A defined patient group, a pre-specified protocol, ground truth "
            "recorded by a clinician who has examined the foot rather than "
            "only the photograph, and a sample size fixed in advance."
        ),
        "safety": safety_block("foot"),
    }
