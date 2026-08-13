from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from .. import audit
from ..deps import CurrentUser, SessionDep, get_user_by_email
from ..errors import ApiError
from ..schemas import TokenOut, UserOut
from ..security import create_access_token, verify_password

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


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
