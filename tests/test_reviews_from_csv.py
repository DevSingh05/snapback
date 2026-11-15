import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "reviews_from_csv", Path(__file__).resolve().parents[1] / "scripts/reviews_from_csv.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

CSV = (
    "Timestamp,Q1,Q2,Q3,Q4,Q5,Q6,Q7,Name\n"
    '2026/11/15 1:00:00 AM EST,5,Yes,4,Yes,"SECRET free text",Clear and fast,Yes,Sam Q\n'
    "2026/11/15 1:05:00 AM EST,2,No,1,No,more private text,,No,\n"
    "2026/11/15 1:06:00 AM EST,9,Maybe,3,Maybe,x,,Yes,\n"
    "2026/11/15 1:07:00 AM EST,4,Not sure,3,Maybe,y,,,\n"
)


def test_convert_maps_columns_and_drops_q5_and_bad_rows():
    out = mod.convert(CSV, form_url="https://forms.example/x", updated="2026-11-15")
    assert out["form_url"] == "https://forms.example/x"
    assert len(out["responses"]) == 3
    first = out["responses"][0]
    assert first == {
        "q1_easy": 5,
        "q2_would_pay": "yes",
        "q3_trust": 4,
        "q4_use_again": "yes",
        "q6_quote": "Clear and fast",
        "q6_name": "Sam",
        "q7_rented": True,
    }
    assert "q6_quote" not in out["responses"][1]
    assert out["responses"][1]["q7_rented"] is False
    assert "q7_rented" not in out["responses"][2]
    assert "SECRET" not in json.dumps(out) and "private" not in json.dumps(out)


def test_cli_keeps_existing_form_url(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(CSV)
    dest = tmp_path / "reviews.json"
    dest.write_text(json.dumps({"updated": "", "form_url": "https://f/y", "responses": []}))
    assert mod.main([str(src), "--out", str(dest)]) == 0
    data = json.loads(dest.read_text())
    assert data["form_url"] == "https://f/y" and len(data["responses"]) == 3
