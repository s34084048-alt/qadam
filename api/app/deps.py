from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .errors import ApiError
from .models import Case, Patient, User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
) -> User:
    payload = decode_access_token(token)
    if not payload:
        raise ApiError(
            401, "invalid_token", "Your session is not valid or has expired.",
            hint="Sign in again to obtain a new token.",
        )
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise ApiError(401, "invalid_token", "Malformed token subject.",
                       hint="Sign in again.")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError(
            401, "user_inactive", "This account is not active.",
            hint="Contact an administrator.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise ApiError(
            403, "admin_required", "This endpoint requires the admin role.",
            hint="Sign in with an administrator account.",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    # Copy-paste and mobile keyboards routinely add surrounding whitespace and
    # capitalise the first letter. Neither should lock a health worker out.
    normalised = email.strip().lower()
    result = await session.execute(select(User).where(User.email == normalised))
    return result.scalar_one_or_none()


# --- organisational isolation ------------------------------------------------
#
# Every route that touches a case or a patient loads it through one of these
# two helpers. Scattering `.where(organisation_id == ...)` across the routers
# would mean one forgotten clause is a cross-clinic data leak, so the check
# lives at the point of loading instead.
#
# A resource belonging to another organisation answers 404, NOT 403. A 403
# would confirm that the id exists, which is itself a disclosure: it lets one
# clinic enumerate another's case identifiers.


async def load_case_scoped(session: AsyncSession, case_id, user: User) -> Case:
    case = await session.get(Case, case_id)
    if case is None or case.organisation_id != user.organisation_id:
        raise ApiError(
            404, "case_not_found", f"No case with id {case_id}.",
            hint="Check the case id, or list the cases you have access to.",
        )
    return case


async def load_patient_scoped(
    session: AsyncSession, external_ref: str, user: User
) -> Patient | None:
    result = await session.execute(
        select(Patient).where(
            Patient.external_ref == external_ref,
            Patient.organisation_id == user.organisation_id,
        )
    )
    return result.scalar_one_or_none()
