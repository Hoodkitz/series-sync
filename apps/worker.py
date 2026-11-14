"""CLI entry point for Series Sync background worker.

Usage:
    python -m apps.worker --once          # run one pass and exit
    python -m apps.worker --interval 15   # loop every 15s
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from apps.db.session import AsyncSessionLocal
from apps.services.worker import resume_pending_jobs, run_worker_loop


def main():
    parser = argparse.ArgumentParser(description="Series Sync Job Resumption Worker")
    parser.add_argument("--once", action="store_true", help="Process pending/paused jobs once and exit")
    parser.add_argument("--interval", type=float, default=30.0, help="Polling interval in seconds (default: 30)")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to pick per pass (default: 10)")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.once:
        count = asyncio.run(resume_pending_jobs(AsyncSessionLocal, limit=args.limit))
        logging.info("Processed %d jobs (single pass)", count)
        sys.exit(0)
    else:
        try:
            asyncio.run(run_worker_loop(AsyncSessionLocal, poll_interval=args.interval))
        except KeyboardInterrupt:
            logging.info("Worker stopped by user")


if __name__ == "__main__":
    main()
