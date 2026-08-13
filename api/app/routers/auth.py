from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from .. import audit
from ..config import settings
from ..deps import CurrentUser, SessionDep, get_user_by_email
from ..errors import ApiError
from ..models import Organisation, User
from ..schemas import TokenOut, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> TokenOut:
    user = await get_user_by_email(session, form.username)
    # Same response whether the account is unknown or the password is wrong.
    if user is None or not verify_password(form.password, user.password_hash):
        await audit.record(
            session,
            actor_user_id=user.id if user else None,
            organisation_id=user.organisation_id if user else None,
            action="auth.login_failed",
            entity="user",
            entity_id=user.id if user else None,
            meta={"reason": "invalid_credentials"},
        )
        await session.commit()
        raise ApiError(
            401, "invalid_credentials", "Email or password is incorrect.",
            hint="Check the address and password, or ask an admin to reset it.",
        )
    if not user.is_active:
        raise ApiError(
            403, "user_inactive", "This account has been deactivated.",
            hint="Contact an administrator.",
        )

    token, expires_in = create_access_token(user.id, user.role)
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="auth.login", entity="user",
        entity_id=user.id, meta={"role": user.role},
    )
    await session.commit()
    return TokenOut(
        access_token=token, expires_in=expires_in, role=user.role, email=user.email
    )


@router.post("/demo", response_model=TokenOut)
async def start_demo(session: SessionDep) -> TokenOut:
    """Start a session with no password. Off unless DEMO_MODE=true.

    Every visitor gets their OWN organisation, not a shared one. That is the
    whole design: the organisation boundary already isolates cases, so one
    visitor's captures are invisible to every other visitor and to the seeded
    demo account. An open link WITHOUT this would mean any photograph anyone
    uploads — and on a tool like this, someone will eventually point it at a
    real patient — is browsable by everyone who has the link.

    The account is real: it has a role, it owns rows, and the audit trail
    attributes its actions. It simply has no password anyone needs to type,
    and a password that nobody holds.
    """
    if not settings.demo_mode:
        # 404, not 403: in a normal deployment this endpoint does not exist,
        # and saying "forbidden" would advertise that it could.
        raise ApiError(
            404, "not_found", "This endpoint is not enabled.",
            hint="Open demo access is off. Sign in with an account.",
        )

    live = int((await session.execute(
        select(func.count()).select_from(Organisation)
        .where(Organisation.slug.like("demo-%"))
    )).scalar_one())
    if live >= settings.demo_max_sessions:
        raise ApiError(
            429, "demo_capacity_reached",
            "This demo has reached its session limit.",
            hint="Try again later, or sign in with an account.",
        )

    handle = uuid.uuid4().hex[:12]
    org = Organisation(name=f"Demo session {handle}", slug=f"demo-{handle}")
    session.add(org)
    await session.flush()

    user = User(
        organisation_id=org.id,
        email=f"demo-{handle}@demo.invalid",
        # Random and discarded. There is no password to hand out, so this
        # account cannot be signed into through /auth/login by anyone.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="clinician",
    )
    session.add(user)
    await session.flush()

    token, expires_in = create_access_token(user.id, user.role)
    await audit.record(
        session, actor_user_id=user.id, organisation_id=org.id,
        action="auth.demo_session", entity="user", entity_id=user.id,
        meta={"role": user.role},
    )
    await session.commit()
    return TokenOut(
        access_token=token, expires_in=expires_in, role=user.role,
        email=user.email,
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
