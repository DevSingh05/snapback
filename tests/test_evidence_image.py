"""J1 (#10): GET /cases/{id}/evidence-image, the ad photo beside the scan view it matched."""

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.agent.join import KitLookups
from snapback.api.casefiles import CaseFiles
from snapback.api.main import create_app
from snapback.contracts import DataSource, EvidenceFile, EvidencePhoto, EvidencePoints, LocateStatus
from snapback.settings import Settings
from snapback.vision.evidence_image import HEIGHT, MIN_SIDE, WIDTH, caption, footprint, render

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PNG = ROOT / "fixtures" / "evidence" / "evidence_image_P1.png"


def jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.convert("RGB").save(out, format="JPEG", quality=88)
    return out.getvalue()


def fixture_pair(tmp_path):
    """A team-made synthetic scan face, and an 'ad photo' cropped from it (FIXTURE)."""
    face = Image.open(FixtureMatterport(tmp_path).sweeps("fx-model-a")[2].faces[1]).convert("RGB")
    return jpeg(face.crop((30, 20, 230, 190))), jpeg(face)


POINTS = EvidencePoints(
    n_total=45,
    sampled=[(0.2, 0.3, 0.25, 0.35), (0.6, 0.5, 0.55, 0.52), (0.8, 0.7, 0.72, 0.66)],
)


def evidence(status=LocateStatus.LOCATED_IN_CLAIMED, flipped=None) -> EvidenceFile:
    return EvidenceFile(
        case_id="x",
        source=DataSource.FIXTURE,
        thresholds_version="t",
        bars={"min_inliers": 30},
        photos=[
            EvidencePhoto(alias="P1", status=status, inliers=45, points=POINTS, flipped=flipped),
            EvidencePhoto(alias="P2", status=LocateStatus.NOT_LOCATED),
        ],
    )


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def case_with_files(client, tmp_path, **kw):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"}).json()
    ad, scan = fixture_pair(tmp_path)
    files = CaseFiles(evidence=evidence(**kw))
    files.images[("P1", "photo")], files.images[("P1", "scan")] = ad, scan
    client.app.state.store.get(made["case_id"]).files = files
    return made, {"Authorization": f"Bearer {made['read_token']}"}


def test_a_placed_photo_returns_the_png(client, tmp_path):
    made, auth = case_with_files(client, tmp_path)
    r = client.get(f"/cases/{made['case_id']}/evidence-image?photo=1", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(r.content)) as image:
        assert image.size == (WIDTH, HEIGHT)


def test_an_unplaced_photo_or_no_photo_is_404(client, tmp_path):
    made, auth = case_with_files(client, tmp_path)
    base = f"/cases/{made['case_id']}/evidence-image"
    assert client.get(f"{base}?photo=2", headers=auth).status_code == 404  # not located
    assert client.get(f"{base}?photo=9", headers=auth).status_code == 404  # no such photo


def test_the_token_goes_in_a_header_only(client, tmp_path):
    made, auth = case_with_files(client, tmp_path)
    base = f"/cases/{made['case_id']}/evidence-image"
    assert client.get(base).status_code == 401
    assert client.get(base, headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client.get(f"{base}?token={made['read_token']}", headers=auth).status_code == 401
    assert client.get(base, headers={"X-Case-Token": made["read_token"]}).status_code == 200


def test_the_caption_is_code_written_with_counts_only():
    line = caption("P1", LocateStatus.LOCATED_IN_CLAIMED, 312, None, DataSource.LIVE)
    assert line == "P1 · Taken in this building · 312 matched points · LIVE"
    flipped = caption("P2", LocateStatus.LOCATED_ELSEWHERE, 88, True, DataSource.LIVE)
    assert "different building" in flipped and "flipped left to right" in flipped
    es = caption("P1", LocateStatus.LOCATED_IN_CLAIMED, 312, None, DataSource.FIXTURE, "es")
    assert es.startswith("P1 · Tomada en este edificio") and es.endswith("FIXTURE")
    # no digits but the alias number and the count
    assert not re.search(r"\d", re.sub(r"P\d|\b312\b", "", line))
    with pytest.raises(ValueError):
        caption("P3", LocateStatus.NOT_LOCATED, None, None, DataSource.LIVE)


def test_the_committed_fixture_png_is_the_contract_shape(tmp_path):
    """Rishit codes against fixtures/evidence/evidence_image_P1.png (team-made synthetic scan)."""
    with Image.open(FIXTURE_PNG) as image:
        assert image.format == "PNG" and image.size == (WIDTH, HEIGHT)
    ad, scan = fixture_pair(tmp_path)
    fresh = render(
        ad,
        scan,
        POINTS,
        caption("P1", LocateStatus.LOCATED_IN_CLAIMED, 45, None, DataSource.FIXTURE),
    )
    with Image.open(io.BytesIO(fresh)) as image:
        assert image.size == (WIDTH, HEIGHT)


def test_the_scan_panel_is_cropped_to_where_the_photo_lands():
    """Eye check (#10): the whole 90-degree face beside a photo that covers part of it reads as
    "not the same place". The box holds every matched point and has the photo's shape."""
    pts = EvidencePoints(n_total=4, sampled=[(0.1, 0.1, 0.6, 0.5), (0.9, 0.9, 0.9, 0.8)])
    left, top, right, bottom = footprint(pts, aspect=4 / 3)
    assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1
    for _, _, u, v in pts.sampled:
        assert left <= u <= right and top <= v <= bottom
    assert (right - left) / (bottom - top) == pytest.approx(4 / 3, rel=0.02)
    assert right - left < 1  # cropped, not the whole face


def test_the_crop_never_shrinks_below_the_floor_or_leaves_the_frame():
    one = EvidencePoints(n_total=1, sampled=[(0.5, 0.5, 0.99, 0.01)])
    left, top, right, bottom = footprint(one, aspect=1.0)
    assert right - left >= MIN_SIDE - 1e-9 and bottom - top >= MIN_SIDE - 1e-9
    assert left >= 0 and right <= 1 and top >= 0 and bottom <= 1
    assert footprint(None, 1.5) == (0.0, 0.0, 1.0, 1.0)
    assert footprint(EvidencePoints(n_total=0), 1.5) == (0.0, 0.0, 1.0, 1.0)
