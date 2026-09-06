"""Local database administration.

    python -m app.cli init-db     create any missing tables
    python -m app.cli seed-demo   load the synthetic demo investigation
    python -m app.cli status      show what is currently persisted
    python -m app.cli reset --yes drop every table and recreate the schema

The database is chosen by SILENT_TRACE_DATABASE_URL and defaults to the local
SQLite file, so the same commands work unchanged against PostgreSQL.
"""

import argparse
import sys

from app.config import database_url
from app.db.database import create_all, drop_all, session_scope
from app.db.repositories import CaseRepository, ProjectionRepository, RecordRepository
from app.services.demo_seed import seed_demo_case
from app.services.pipeline import InvestigationPipeline
from app.services.synthetic_populations import all_populations


def cmd_init_db(_: argparse.Namespace) -> int:
    create_all()
    print(f"schema ready at {database_url()}")
    return 0


def cmd_seed_demo(_: argparse.Namespace) -> int:
    create_all()
    with session_scope() as session:
        summary = seed_demo_case(session)
    print(f"seeded {summary.case_id} into {database_url()}")
    print(f"  dataset          {summary.dataset_id}")
    print(f"  records accepted {summary.accepted_records} (rejected {summary.rejected_records})")
    print(f"  reports          {summary.reports_processed}")
    print(f"  graph            {summary.graph_id}: {summary.node_count} nodes, {summary.edge_count} edges")
    for error in summary.errors:
        print(f"  ! {error}")
    return 0


def cmd_seed_populations(_: argparse.Namespace) -> int:
    """Load the three analytical test populations through the normal pipeline."""
    create_all()
    pipeline = InvestigationPipeline()
    with session_scope() as session:
        for dataset in all_populations():
            result = pipeline.ingest_dataset(session, dataset)
            print(
                f"seeded {dataset.case_id}: {result.accepted_count} records "
                f"({result.rejected_count} rejected)"
            )
            for error in result.errors:
                print(f"  ! {error}")
    print(f"populations loaded into {database_url()}")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    create_all()
    with session_scope() as session:
        cases = CaseRepository(session).list_all()
        if not cases:
            print(f"no investigations persisted at {database_url()}")
            return 0
        print(f"{len(cases)} investigation(s) at {database_url()}")
        for case in cases:
            records = RecordRepository(session).count(case.case_id)
            projection = ProjectionRepository(session)
            print(
                f"  {case.case_id}  status={case.status}  records={records}  "
                f"entities={len(projection.list_entities(case.case_id))}  "
                f"relationships={len(projection.list_relationships(case.case_id))}"
            )
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        print("refusing to drop tables without --yes", file=sys.stderr)
        return 1
    drop_all()
    create_all()
    print(f"schema reset at {database_url()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="create any missing tables").set_defaults(
        handler=cmd_init_db
    )
    subparsers.add_parser("seed-demo", help="load the synthetic demo case").set_defaults(
        handler=cmd_seed_demo
    )
    subparsers.add_parser(
        "seed-populations", help="load the three synthetic analytical populations"
    ).set_defaults(handler=cmd_seed_populations)
    subparsers.add_parser("status", help="show persisted investigations").set_defaults(
        handler=cmd_status
    )
    reset = subparsers.add_parser("reset", help="drop and recreate every table")
    reset.add_argument("--yes", action="store_true", help="confirm the destructive reset")
    reset.set_defaults(handler=cmd_reset)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
