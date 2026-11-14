"""`uv run python -m snapback.redteam --src <team photos> --out data/redteam --seed 1`."""

import argparse
from collections import Counter
from pathlib import Path

from snapback.redteam.generator import generate, write_manifest

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate labelled synthetic attacks.")
    parser.add_argument("--src", type=Path, required=True, help="team-made photos only")
    parser.add_argument("--out", type=Path, default=Path("data/redteam"))
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    sources = sorted(p for p in args.src.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    rows = generate(sources, args.out, seed=args.seed)
    manifest = write_manifest(rows, args.out / "manifest.csv")
    print(f"sources: {len(sources)}  cases: {len(rows)}  manifest: {manifest}")
    for attack, n in sorted(Counter(r.attack.value for r in rows).items()):
        print(f"{attack}: {n}")


if __name__ == "__main__":
    main()
