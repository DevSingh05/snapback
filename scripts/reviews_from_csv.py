"""Turn the Google Form CSV export into apps/web/src/reviews/reviews.json.

Column order is the form's (plan/rating-form.md): Timestamp, Q1 easy, Q2 would pay, Q3 trust,
Q4 use again, Q5 free text (never published, never read), Q6 quote, Q7 rented, then an optional
ninth column with the reviewer's name. The first row is the header and is skipped.

Usage: reviews_from_csv.py EXPORT.csv [--out PATH] [--form-url URL]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "apps/web/src/reviews/reviews.json"

# Positions: 0 Timestamp, 1-4 Q1-Q4, 5 Q5 (ignored), 6 Q6 quote, 7 Q7 rented, 8 name (optional).
YES_NO_NOT_SURE = {"yes": "yes", "no": "no", "not sure": "not sure"}
YES_MAYBE_NO = {"yes": "yes", "maybe": "maybe", "no": "no"}


def _scale(raw: str) -> int | None:
    try:
        v = int(raw.strip())
    except ValueError:
        return None
    return v if 1 <= v <= 5 else None


def row_to_response(row: list[str]) -> dict | None:
    """One CSV row to one response, or None when a required answer is missing or invalid."""
    cells = [c.strip() for c in row] + [""] * 9
    easy, trust = _scale(cells[1]), _scale(cells[3])
    pay = YES_NO_NOT_SURE.get(cells[2].lower())
    again = YES_MAYBE_NO.get(cells[4].lower())
    if easy is None or trust is None or pay is None or again is None:
        return None
    out: dict = {"q1_easy": easy, "q2_would_pay": pay, "q3_trust": trust, "q4_use_again": again}
    if cells[6]:
        out["q6_quote"] = cells[6]
        if cells[8]:
            out["q6_name"] = cells[8].split()[0]
    rented = {"yes": True, "no": False}.get(cells[7].lower())
    if rented is not None:
        out["q7_rented"] = rented
    return out


def convert(csv_text: str, form_url: str = "", updated: str | None = None) -> dict:
    rows = list(csv.reader(csv_text.splitlines()))[1:]
    responses = [r for r in (row_to_response(row) for row in rows if any(row)) if r]
    return {
        "updated": updated or date.today().isoformat(),
        "form_url": form_url,
        "responses": responses,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--form-url", default=None, help="default: keep the URL already in --out")
    args = ap.parse_args(argv)
    url = args.form_url
    if url is None:
        url = ""
        if args.out.exists():
            url = json.loads(args.out.read_text()).get("form_url", "")
    data = convert(args.csv_path.read_text(encoding="utf-8-sig"), url)
    args.out.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {len(data['responses'])} responses to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
