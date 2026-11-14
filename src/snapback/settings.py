"""Runtime settings, read from the environment and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from snapback.contracts import DataSource


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # One switch for every adapter: fixture data by default, live sponsor data on request.
    snapback_data_source: DataSource = DataSource.FIXTURE

    # Where the web app lives. Verify links on cards point here.
    snapback_public_base_url: str = "http://localhost:5173"
    # Sponsor data, caches and uploads. Git-ignored, and purged after the event.
    snapback_data_dir: Path = Path("data")
    # Pause between trace events on the SSE route, for a demo. 0 sends them as they happen.
    snapback_trace_pace_ms: int = 0
    # Who makes the agent's choices: the code policy (no key needed) or the deepagents graph.
    snapback_agent: Literal["policy", "deepagents"] = "policy"
    # Checks one renter may start per day.
    snapback_daily_limit: int = 3

    # Sponsor credentials. SecretStr keeps them out of logs and reprs.
    matterport_api_key: SecretStr | None = None
    matterport_api_token: SecretStr | None = None
    vexcel_api_key: SecretStr | None = None
    costar_zip_password: SecretStr | None = None
    costar_kit_url: str | None = None
    costar_kit_zip: str | None = None

    anthropic_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
