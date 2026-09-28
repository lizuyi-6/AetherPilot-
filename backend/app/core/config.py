"""Application settings, driven by environment variables (prefix AETHER_)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AETHER_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000

    # Runtime data root: experiments workspaces, sqlite db, telemetry.
    data_dir: Path = Path(os.environ.get("AETHER_DATA_DIR", "data"))

    # Optional LLM (OpenAI-compatible). System works without it.
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_s: float = 30.0

    # Telemetry sampling intervals (seconds).
    telemetry_system_interval_s: float = 2.0
    telemetry_gpu_interval_s: float = 2.0

    # Demo workload step pacing is controlled by the workload itself.

    @property
    def project_root(self) -> Path:
        # backend/app/core/config.py → parents[3] is the repository root.
        return Path(__file__).resolve().parents[3]

    @property
    def demo_workload_path(self) -> Path:
        return self.project_root / "demo" / "training_workload.py"

    @property
    def skills_dir(self) -> Path:
        return self.project_root / "skills"

    @property
    def experiments_dir(self) -> Path:
        return self.data_dir / "experiments"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "aetherpilot.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
