"""Runtime settings, read from the environment and an optional .env file."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from snapback.contracts import DataSource


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # One switch for every adapter: fixture data by default, live sponsor data on request.
    snapback_data_source: DataSource = DataSource.FIXTURE

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
