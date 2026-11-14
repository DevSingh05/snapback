"""FastAPI entry point. Run with `make api`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from snapback.contracts import Evidence, Verdict
from snapback.settings import get_settings
from snapback.verdict import decide

app = FastAPI(title="SNAPBACK API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness plus the active data source, so every client can show LIVE or FIXTURE."""
    return {"status": "ok", "data_source": get_settings().snapback_data_source.value}


@app.post("/verdict")
def verdict(evidence: Evidence) -> Verdict:
    """Decide a verdict from evidence the caller already gathered. No model is involved."""
    return decide(evidence)
