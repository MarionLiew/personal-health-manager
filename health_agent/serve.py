from __future__ import annotations

import uvicorn

from health_agent.webapp import create_app


def main() -> None:
    """Read-only doctor view, loopback by default; pass --host to expose."""
    import argparse

    parser = argparse.ArgumentParser(description="Serve the doctor-view web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8800)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
