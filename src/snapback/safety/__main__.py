"""`uv run python -m snapback.safety purge | delete-case <id> | delete-renter <id>`."""

import argparse
from pathlib import Path

from snapback.safety import delete_case, delete_renter, purge
from snapback.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="SNAPBACK data safety commands.")
    parser.add_argument("--data", type=Path, default=None, help="defaults to SNAPBACK_DATA_DIR")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("purge", help="delete everything under data/")
    sub.add_parser("delete-case").add_argument("case_id")
    sub.add_parser("delete-renter").add_argument("renter_id")
    args = parser.parse_args()
    data = args.data or get_settings().snapback_data_dir
    if args.cmd == "purge":
        print(f"purge: removed {purge(data)} entries from {Path(data).resolve()}")
    elif args.cmd == "delete-case":
        r = delete_case(args.case_id, data)
        print(f"delete-case: {r.rows} rows and {r.files} files removed")
    else:
        print(f"delete-renter: {len(delete_renter(args.renter_id, data))} cases removed")


if __name__ == "__main__":
    main()
