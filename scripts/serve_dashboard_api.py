"""Start the Phase 20.1 localhost-only, read-only ArbiScan JSON API.

No credentials or live provider calls. Demo fixtures require explicit --demo.
The full interactive browser dashboard is scheduled for Phase 20.2.
"""

from __future__ import annotations

import argparse

from arbiscan.api.http import create_local_http_server
from arbiscan.api.service import ArbiScanApi
from arbiscan.api.synthetic import SyntheticApiDataSource

VERSION = "0.1.0.dev0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=8000, help="Local port (default 8000; 1-65535)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show clearly marked synthetic fixtures, not real odds or opportunities",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    source = SyntheticApiDataSource(demo=args.demo)
    api = ArbiScanApi(source, version=VERSION)
    mode = "synthetic" if args.demo else "empty"
    with create_local_http_server(api=api, mode=mode, version=VERSION, port=args.port) as server:
        print(
            f"ArbiScan Phase 20.1: http://127.0.0.1:{server.server_port}/ "
            f"(data_mode={mode}; only local GET requests)",
            flush=True,
        )
        print(
            "No real provider connections, live quote authorization, trading or persistence. "
            "Ctrl+C to stop.",
            flush=True,
        )
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
