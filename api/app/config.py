from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .safety import INTENDED_USE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- app -----------------------------------------------------------------
    app_name: str = "QADAM"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- safety --------------------------------------------------------------
    # Hard-wired false. QADAM is not validated or registered; nothing in the
    # configuration may flip it into a "cleared for clinical use" posture.
    intended_use: str = INTENDED_USE

    # --- database ------------------------------------------------------------
    # Postgres in docker-compose; SQLite keeps a bare `pytest` / laptop run
    # working with no services. Same models, same migrations metadata.
    database_url: str = "sqlite+aiosqlite:///./qadam.db"
    db_echo: bool = False
    auto_create_schema: bool = True  # dev/test convenience; prod uses Alembic

    # --- object storage ------------------------------------------------------
    storage_backend: Literal["s3", "local"] = "local"
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_region: str = "me-central-1"  # UAE data residency by default
    s3_bucket: str = "qadam-images"
    s3_access_key: str = "qadam"
    s3_secret_key: str = "qadam-secret"
    s3_use_ssl: bool = False
    local_storage_dir: str = "./_storage"

    # --- auth ----------------------------------------------------------------
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    # --- analysis ------------------------------------------------------------
    analysis_runner: Literal["inline", "queue"] = "inline"
    redis_url: str = "redis://redis:6379/0"
    max_upload_bytes: int = 20 * 1024 * 1024

    # --- quality gate thresholds --------------------------------------------
    quality_min_short_side: int = 240
    quality_min_focus_var: float = 60.0
    quality_exposure_min: float = 45.0
    quality_exposure_max: float = 215.0
    quality_min_subject_fraction: float = 0.08

    # --- compliance ----------------------------------------------------------
    data_residency: str = "UAE"
    require_consent: bool = True

    # --- single-origin hosting ----------------------------------------------
    # Path to a built web bundle. When set, the API serves the app from its own
    # origin, so /api requests are same-origin: no CORS, and no bearer token
    # crossing an origin boundary. Empty means API only (docker compose puts
    # nginx in front, and the dev server proxies).
    serve_web_dir: str = ""

    # --- seeding -------------------------------------------------------------
    seed_admin_email: str = "admin@qadam.local"
    seed_admin_password: str = "qadam-admin"
    seed_clinician_email: str = "clinician@qadam.local"
    seed_clinician_password: str = "qadam-clinician"

    @property
    def clinical_use(self) -> bool:
        """Never true. Present so callers can read it rather than hardcode it."""
        return False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Alembic runs on the sync driver."""
        return (
            self.database_url.replace("+asyncpg", "")
            .replace("+aiosqlite", "")
        )

    @property
    def is_public_deployment(self) -> bool:
        return self.environment in ("staging", "prod")


# Defaults that exist so a laptop run works with no configuration. Every one of
# them is public knowledge -- they are in this file, in the compose file and in
# the README -- so any of them reaching a public URL is a published credential.
INSECURE_DEFAULTS = {
    "JWT_SECRET": "change-me-in-production",
    "SEED_ADMIN_PASSWORD": "qadam-admin",
    "SEED_CLINICIAN_PASSWORD": "qadam-clinician",
    "S3_SECRET_KEY": "qadam-secret",
}


class InsecureDeployment(RuntimeError):
    """Raised at import time, so the process never starts and never serves."""


def assert_deployable(s: Settings) -> None:
    """Refuse to boot a public deployment on shipped default credentials.

    A local run needs no configuration, which is the whole point of those
    defaults -- and is exactly why they must not survive the trip to a public
    host. Failing to start is the only reliable way to enforce that: a warning
    in a log nobody reads is not a control, and by the time anyone reads it the
    instance is already serving on the open internet.
    """
    if not s.is_public_deployment:
        return

    found = [
        name for name, default in INSECURE_DEFAULTS.items()
        if getattr(s, name.lower(), None) == default
    ]
    if s.storage_backend != "s3":
        found = [f for f in found if f != "S3_SECRET_KEY"]
    if not found:
        return

    raise InsecureDeployment(
        f"ENVIRONMENT={s.environment} but these are still at their shipped "
        f"default: {', '.join(found)}. They are published in this repository, "
        "so the deployment would be open to anyone who has read it. Set each "
        "to a generated secret and restart."
    )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    assert_deployable(s)
    return s


settings = get_settings()
