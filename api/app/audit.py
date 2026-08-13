from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog

# Keys that must never reach the audit meta blob or the application log.
_FORBIDDEN_META_KEYS = {
    "image",
    "image_bytes",
    "file",
    "content",
    "overlay",
    "overlay_png",
    "name",
    "patient_name",
    "dob",
    "email",
    "phone",
    "address",
    "mrn",
}


def scrub(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Drop anything that could carry PHI or image bytes into the audit trail."""
    if not meta:
        return {}
    out: dict[str, Any] = {}
    for key, value in meta.items():
        if key.lower() in _FORBIDDEN_META_KEYS:
            continue
        if isinstance(value, (bytes, bytearray, memoryview)):
            continue
        if isinstance(value, str) and len(value) > 512:
            value = value[:512] + "…"
        if isinstance(value, dict):
            value = scrub(value)
        out[key] = value
    return out


async def record(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    organisation_id: uuid.UUID | None = None,
    action: str,
    entity: str,
    entity_id: str | uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Append an audit row. Caller commits.

    Append-only by construction: there is no update or delete path for
    AuditLog anywhere in the application.
    """
    session.add(
        AuditLog(
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            meta_json=scrub(meta),
        )
    )
