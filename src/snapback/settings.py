"""Runtime settings, read from the environment and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from snapback.contracts import DataSource

DEMO_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "demo"


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
    # Locate accuracy on the kit's own photos, written by `make eval-locate-real` (A8):
    # totals only. Served read-only at GET /eval/locate_real.csv.
    snapback_eval_locate_real: Path = Path("eval/locate_real.csv")
    # The measured ad batch written by `make eval-ads` (FIXTURE results are committed):
    snapback_eval_ads: Path = Path("eval/ads_results.csv")
    # Pause between trace events on the SSE route, for a demo. 0 sends them as they happen.
    snapback_trace_pace_ms: int = 0
    # M3: what opens GET /events/stream, sent in a header. Unset closes the stream to everyone.
    snapback_events_token: SecretStr | None = None
    # What happens after the renter approves the challenge (A14). "stand_in" answers at once
    # from the fixture. "reply" waits for the poster's real reply photo, sent to
    # POST /cases/{id}/reply, and checks it.
    snapback_challenge: Literal["stand_in", "reply"] = "stand_in"
    # A24 stretch: may the agent ask the renter for a license number the ad did not give?
    # Off by default: a case that asks waits for POST /cases/{id}/answer, and no screen sends it.
    snapback_ask_renter: bool = False
    # A22: the live locator. Index folder under data/index, and the time one case may spend
    # placing its photos (a photo not done in time reads "not located", never "elsewhere").
    snapback_locate_index: str = "demo"
    snapback_locate_budget_s: float = 25.0
    # The zone a card's times are shown in: the building's, not the server's. Houston is
    # America/Chicago.
    snapback_card_timezone: str = "America/Chicago"

    @property
    def agent_timeout_s(self) -> float:
        """The deep agent's time limit for this mode: the explicit SNAPBACK_AGENT_TIMEOUT_S if one
        was set, else 25 s on the request path and the longer budget for the background."""
        if "snapback_agent_timeout_s" in self.model_fields_set:
            return self.snapback_agent_timeout_s
        if self.snapback_agent == "deepagents_async":
            return self.snapback_agent_async_default_timeout_s
        return self.snapback_agent_timeout_s

    @field_validator("snapback_card_timezone")
    @classmethod
    def _a_known_time_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"SNAPBACK_CARD_TIMEZONE is not a known time zone: {value!r}. "
                "Use a name like America/Chicago."
            ) from None
        return value

    # Who makes the agent's choices: the code policy (no key needed) or the deepagents graph.
    # `deepagents_async`: the case runs on the policy and the answer returns at once; the deep
    # agent then works the same case in the background and streams its steps into the timeline.
    snapback_agent: Literal["policy", "deepagents", "deepagents_async"] = "policy"
    # The deep agent's time per run (seconds) before code finishes the case, and which Claude
    # model it uses (None: the graph's default). The key is ANTHROPIC_API_KEY, from the env.
    snapback_agent_timeout_s: float = 25.0
    # deepagents_async has no request waiting on it, so unless SNAPBACK_AGENT_TIMEOUT_S is set
    # explicitly its default is this longer budget (measured: a full run takes about 25 s).
    snapback_agent_async_default_timeout_s: float = 60.0
    snapback_agent_model: str = "claude-sonnet-5-5"
    # The sub-agents (one per check family) read a few facts and write a note: a small, fast model.
    snapback_subagent_model: str = "claude-haiku-5-5"
    # Most background agent runs at once (deepagents_async); the rest wait their turn.
    snapback_agent_max_concurrent: int = Field(default=2, ge=1, le=16)
    # LangSmith tracing for the deepagents path. A human creates the key (AGENTS.md rule 8); with
    # none set, tracing stays off. Standard env vars LANGSMITH_API_KEY / LANGSMITH_PROJECT work too.
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "snapback"
    # The project's page in LangSmith, for the "LangSmith" link on the trace cards. A plain
    # https address on smith.langchain.com with no query, fragment or sign-in in it: a key or
    # a token never goes in an address, so anything else is dropped.
    snapback_langsmith_url: str | None = None
    # Checks one renter (or one browser) may start per day, and a ceiling per network address
    # so that clearing cookies is not a way around it.
    snapback_daily_limit: int = 3
    snapback_daily_limit_per_address: int = 100
    # Upload caps, enforced before the body is parsed and again per file.
    snapback_max_photos: int = 10
    snapback_max_photo_mb: int = 10

    # A staged demo case from fixtures/demo (a, b or c), read from DEMO_CASE. With it set,
    # every new check runs on that case's stand-ins. Unset or empty for normal runs.
    demo_case: str | None = None

    @field_validator("snapback_langsmith_url", mode="before")
    @classmethod
    def _a_plain_langsmith_address(cls, value: object) -> str | None:
        url = str(value).strip() if value is not None else ""
        try:
            parts = urlsplit(url)
            host = parts.hostname or ""
        except ValueError:
            return None
        on_langsmith = host == "smith.langchain.com" or host.endswith(".smith.langchain.com")
        plain = not (parts.query or parts.fragment or parts.username or parts.password)
        return url if parts.scheme == "https" and on_langsmith and plain else None

    @field_validator("demo_case", mode="before")
    @classmethod
    def _a_known_demo_case(cls, value: object) -> str | None:
        chosen = str(value).strip().lower() if value is not None else ""
        if not chosen:
            return None
        known = sorted(path.parent.name for path in DEMO_DIR.glob("*/case.json"))
        if chosen not in known:
            raise ValueError(f"DEMO_CASE must be one of: {', '.join(known)}. Got {chosen!r}.")
        return chosen

    # Sponsor credentials. SecretStr keeps them out of logs and reprs.
    matterport_api_key: SecretStr | None = None
    matterport_api_token: SecretStr | None = None
    # W1 web sub-agent (#8, Vidyut 20:10). A missing key means "not checked", never a failure.
    brightdata_api_token: SecretStr | None = None
    apify_token: SecretStr | None = None
    browser_use_api_key: SecretStr | None = None
    # Bright Data zone names (not secret): one Web Unlocker zone and one SERP API zone.
    brightdata_unlocker_zone: str = "snapback_unlocker"
    brightdata_serp_zone: str = "snapback_serp"
    # Apify actors for the same home posted elsewhere, as "owner~name". None turns one off.
    apify_zillow_actor: str | None = "maxcopell~zillow-scraper"
    apify_craigslist_actor: str | None = None
    # The three checks share one limit; past it a check reads "timed out" and the case goes on.
    snapback_web_limit_s: float = 20.0  # Apify's search measured 8.9 to 14.2 s (n=3, LIVE)
    # Run the web checks on LIVE cases. Off by default so tests, CI and a public host never call
    # out; set SNAPBACK_WEB_CHECKS=1 in the demo laptop's .env with the three keys.
    snapback_web_checks: bool = False
    # Browser Use spend cap per link check, in dollars (the account has little credit).
    browser_use_max_cost_usd: float = 0.10
    # At most this many cases start web checks in any rolling hour (each case starts them once).
    snapback_web_max_per_hour: int = 30
    # Without Bright Data zones, read the building's own site with a plain direct fetch (free).
    # Off by default so a case with no keys makes no call; the demo laptop turns it on.
    snapback_web_direct_fetch: bool = False
    vexcel_api_key: SecretStr | None = None
    costar_zip_password: SecretStr | None = None
    costar_kit_url: str | None = None
    costar_kit_zip: str | None = None

    # Key for hashing phone numbers so they are compared without being kept (A7). Unset, a
    # fixture run uses a fixed synthetic salt and a live run makes one per process.
    snapback_phone_salt: SecretStr | None = None

    # Show CoStar's record figures (rent bands, units available, links) in a LIVE case. Off by
    # default: set it only in the local demo .env, never on a public host. A fixture case always
    # shows them (synthetic). Never in card.png, the report pack, the MCP output or the iMessage.
    snapback_show_record_figures: bool = False

    anthropic_api_key: SecretStr | None = None

    # Voice for the Finder (ElevenLabs text to speech and Scribe speech to text). Unset, the voice
    # routes answer 503 and the web app hides read-aloud. The key only ever goes in xi-api-key.
    elevenlabs_api_key: SecretStr | None = None
    # A warm, natural premade voice ("Sarah"); any voice id from the ElevenLabs library works.
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    # Voice requests one network address may make per day, per direction.
    snapback_voice_daily_limit: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
