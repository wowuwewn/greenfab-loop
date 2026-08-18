"""CLI for idempotently importing a Detect dashboard artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.database import transactional_session
from app.enums import SourceType
from app.errors import DomainError
from app.services.detect_import import import_detect_artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import dashboard_data.json into Cases")
    parser.add_argument("artifact", type=Path, help="Path to a contract-compatible JSON artifact")
    parser.add_argument("--source-type", choices=("REAL", "DEMO"), default="REAL")
    parser.add_argument("--actor", default="detect_import_cli")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with transactional_session() as session:
            result = import_detect_artifact(
                session,
                args.artifact,
                source_type=SourceType(args.source_type),
                actor=args.actor,
                max_bytes=settings.detect_artifact_max_bytes,
            )
    except DomainError as exc:
        print(f"Detect import failed: {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    print(result.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
