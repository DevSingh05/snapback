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
    # The eval harness's results, written by `make eval`: aggregate numbers only. Served
    # read-only at GET /eval/results.csv for the Lab panel.
    snapback_eval_results: Path = Path("eval/results.csv")
    # Pause between trace events on the SSE route, for a demo. 0 sends them as they happen.
    snapback_trace_pace_ms: int = 0
    # What happens after the renter approves the challenge (A14). "stand_in" answers at once
    # from the fixture. "reply" waits for the poster's real reply photo, sent to
    # POST /cases/{id}/reply, and checks it.
    snapback_challenge: Literal["stand_in", "reply"] = "stand_in"
    # Who makes the agent's choices: the code policy (no key needed) or the deepagents graph.
    snapback_agent: Literal["policy", "deepagents"] = "policy"
    # Checks one renter (or one browser) may start per day, and a ceiling per network address
    # so that clearing cookies is not a way around it.
    snapback_daily_limit: int = 3
    snapback_daily_limit_per_address: int = 100
    # Upload caps, enforced before the body is parsed and again per file.
    snapback_max_photos: int = 10
    snapback_max_photo_mb: int = 10

    # Sponsor credentials. SecretStr keeps them out of logs and reprs.
    matterport_api_key: SecretStr | None = None
    matterport_api_token: SecretStr | None = None
    vexcel_api_key: SecretStr | None = None
    costar_zip_password: SecretStr | None = None
    costar_kit_url: str | None = None
    costar_kit_zip: str | None = None

    # Key for hashing phone numbers so they are compared without being kept (A7). Unset, a
    # fixture run uses a fixed synthetic salt and a live run makes one per process.
    snapback_phone_salt: SecretStr | None = None

    anthropic_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
