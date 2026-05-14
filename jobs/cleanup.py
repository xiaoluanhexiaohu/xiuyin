"""Cleanup expired web job files."""

from __future__ import annotations

import json

from jobs.status import cleanup_expired


def main() -> int:
    """Run cleanup and print a compact summary."""

    count = cleanup_expired()
    print(json.dumps({"expired_jobs_cleaned": count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
