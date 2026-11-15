"""``python -m samg.api [--host H] [--port P]``: serve the control-center API (default 127.0.0.1:8000)."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run("samg.api.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
