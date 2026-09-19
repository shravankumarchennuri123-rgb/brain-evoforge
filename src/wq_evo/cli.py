from __future__ import annotations

import argparse
import logging
import os
import sys

from .brain.client import BrainClient
from .orchestration.orchestrator import EvoForge
from .storage.db import StateDB


def configure_logging(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(path, encoding="utf-8")],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="BRAIN-EvoForge autonomous research orchestrator")
    ap.add_argument(
        "command",
        choices=["discover", "research-plan", "once", "status", "run", "live-test-one"],
        help="live-test-one runs exactly one candidate through the guarded pipeline and then exits",
    )
    args = ap.parse_args()
    configure_logging(os.getenv("WQ_LOG_PATH", "logs/evoforge.log"))
    email = os.getenv("WQ_BRAIN_EMAIL")
    password = os.getenv("WQ_BRAIN_PASSWORD")
    if not email or not password:
        print("WQ_BRAIN_EMAIL and WQ_BRAIN_PASSWORD are required", file=sys.stderr)
        return 2

    forge = EvoForge(
        StateDB(os.getenv("WQ_DB_PATH", "data/evoforge.sqlite3")),
        BrainClient(email, password),
    )

    if args.command == "discover":
        print(forge.bootstrap())
        return 0
    if args.command == "research-plan":
        print(forge.research_plan(int(os.getenv("WQ_RESEARCH_PLAN_SIZE", "20"))))
        return 0
    if args.command == "once":
        print(forge.run_once())
        return 0
    if args.command == "live-test-one":
        result = forge.live_test_one()
        print(result)
        return 0 if result.get("ok") else 1
    if args.command == "status":
        print(forge.status())
        return 0
    forge.run_forever()
    return 0
