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

    # --- pre-analysis input gate ---------------------------------------------
    # Whether the frame is a clinical photograph at all. Calibrated against
    # tests/fixtures, which are DRAWINGS -- see analysis/input_gate.py for the
    # measured separations each of these sits inside, and for which of them are
    # boundaries the data drew and which are choices inside a gap.
    gate_overlay_min_fill_cv: float = 0.15        # gap 0.073 .. 0.230
    gate_overlay_max_min_solidity: float = 0.50   # gap 0.186 .. 0.811
    gate_lattice_peak_z: float = 6.0              # gap 3.46 .. 8.63
    gate_lattice_weak_z: float = 4.5              # corroborating only; a guess
    gate_screen_panel_contrast: float = 45.0      # levels; a guess
    # Bounded from BOTH sides by evidence, which is why it is only a little
    # above the 0.08 that `quality_min_subject_fraction` still carries:
    #   below 0.09  the pipeline goes non-monotonic -- see input_gate.py
    #   at 0.109    a foot is graded correctly, percentages within 2% of the
    #               same scene shot wide
    #   at 0.121    test_subject_not_skin_refusal requires a verdict
    #   at 0.145    test_smooth_skin_is_never_mistaken_for_a_card, and
    #               test_shadow_is_not_reported_as_dead_tissue, require a grade
    #   at 0.149    test_a_tightly_cropped_lesion_is_seen requires a grade
    # 0.15 was tried first and broke all four: the project has already decided,
    # deliberately, that a tightly cropped lesion must be seen. The usable
    # window is 0.09 .. 0.12 and 0.10 sits in it.
    #
    # The number is NOT where the safety came from. The old check was not weak
    # because 0.08 is small; it was weak because it measured
    # `estimate_subject_mask`, which returns 1.0 when it fails. What changed is
    # the measurement underneath, not the constant on top of it.
    gate_min_subject_presence: float = 0.10

    # --- compliance ----------------------------------------------------------
    data_residency: str = "UAE"
    require_consent: bool = True

    # --- single-origin hosting ----------------------------------------------
    # Path to a built web bundle. When set, the API serves the app from its own
    # origin, so /api requests are same-origin: no CORS, and no bearer token
    # crossing an origin boundary. Empty means API only (docker compose puts
    # nginx in front, and the dev server proxies).
    serve_web_dir: str = ""

    # --- open demo access ----------------------------------------------------
    # When true, anyone with the link can start a session with one click and no
    # password. Each visitor gets their OWN organisation, so the isolation
    # boundary that already exists keeps their captures private from every
    # other visitor. Without that, an open link means any photograph anyone
    # uploads is browsable by everyone who has the link.
    demo_mode: bool = False
    # A ceiling, because the endpoint creates rows and is open to the internet.
    demo_max_sessions: int = 500

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
