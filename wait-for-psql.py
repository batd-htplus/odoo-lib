#!/usr/bin/env python3
"""Block until PostgreSQL accepts connections, or exit non-zero on timeout.

Fixes vs. the upstream version shipped with the odoo image:
  * the original never closed the successful connection (``else`` after
    ``break`` is dead code) and leaked a backend slot on every start;
  * it looped without a real backoff;
  * it reported success even when the loop simply ran out of time on the
    first iteration.
"""
from __future__ import annotations

import argparse
import sys
import time

import psycopg2


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for PostgreSQL to be ready.")
    parser.add_argument("--db_host", required=True)
    parser.add_argument("--db_port", required=True)
    parser.add_argument("--db_user", required=True)
    parser.add_argument("--db_password", required=True)
    parser.add_argument("--db_name", default="postgres")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    delay = 0.5
    last_error: Exception | None = None

    while True:
        try:
            conn = psycopg2.connect(
                host=args.db_host,
                port=args.db_port,
                user=args.db_user,
                password=args.db_password,
                dbname=args.db_name,
                connect_timeout=5,
            )
        except psycopg2.OperationalError as error:
            last_error = error
        else:
            conn.close()
            print(f"postgres at {args.db_host}:{args.db_port} is ready", file=sys.stderr)
            return 0

        if time.monotonic() >= deadline:
            print(f"database connection failure: {last_error}", file=sys.stderr)
            return 1

        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)


if __name__ == "__main__":
    sys.exit(main())
