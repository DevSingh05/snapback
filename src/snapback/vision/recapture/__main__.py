"""`uv run python -m snapback.vision.recapture --manifest ... --out data/recapture/v0.json`."""

import sys

from snapback.vision.recapture.train import main

if __name__ == "__main__":
    sys.exit(main())
