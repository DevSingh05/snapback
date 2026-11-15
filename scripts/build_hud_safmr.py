"""Build fixtures/public/hud_safmr_tx.csv from HUD's FY SAFMR spreadsheet (public domain).

    uv run python scripts/build_hud_safmr.py /abs/path/FY27_safmrs.xlsx FY2027

Standard library only. Keeps Texas ZIPs and the 0 to 4 bedroom Small Area FMR columns; the 90 and
110 percent payment standards are dropped. Source:
https://www.huduser.gov/portal/datasets/fmr/fmr2027/FY27_safmrs.xlsx
"""

import csv
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "public" / "hud_safmr_tx.csv"
BR_COLUMNS = {"D": 0, "G": 1, "J": 2, "M": 3, "P": 4}  # SAFMR 0BR..4BR (not the 90/110% columns)


def is_texas(zip_code: str) -> bool:
    n = int(zip_code)
    return 75000 <= n <= 79999 or 73301 <= n <= 73344 or 88510 <= n <= 88589


def main(path: Path, vintage: str) -> None:
    with zipfile.ZipFile(path) as z:
        strings = [
            "".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml"))
        ]
        rows = []
        for _, row in ET.iterparse(z.open("xl/worksheets/sheet1.xml")):
            if not row.tag.endswith("}row") or row.get("r") == "1":
                continue
            cells = {}
            for c in row:
                col = re.match(r"[A-Z]+", c.get("r")).group(0)
                v = c.find("m:v", NS)
                if v is not None:
                    cells[col] = strings[int(v.text)] if c.get("t") == "s" else v.text
            rows.append(cells)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["zip", "area", "vintage", "br0", "br1", "br2", "br3", "br4"])
        for cells in rows:
            zip_code = (cells.get("A") or "").strip().zfill(5)
            if not zip_code.isdigit() or not is_texas(zip_code):
                continue
            w.writerow(
                [zip_code, cells.get("C", ""), vintage] + [int(float(cells[c])) for c in BR_COLUMNS]
            )
            kept += 1
    print(f"{kept} Texas ZIP rows -> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
