"""Deterministic seeding of the synthetic demo investigation.

The demo case is loaded from the checked-in synthetic fixtures and from nothing
else. There is no generator and no randomness: seeding the same files twice
produces the same case, the same canonical ids and the same graph, because
every identifier in the pipeline is derived from content rather than minted
from a counter or a clock.

Seeding goes through the same :class:`InvestigationPipeline` as a live request.
A demo fixture that took a shortcut into the database would prove nothing about
whether the real pipeline persists correctly.
"""

import json
from pathlib import Path

from app.config import DEMO_DATASET_PATH, DEMO_REPORTS_PATH
from app.schemas.investigation import StrictModel, SyntheticDataset
from app.schemas.nlp import ReportRequest
from app.services.pipeline import InvestigationPipeline, default_graph_id


class DemoSeedSummary(StrictModel):
    case_id: str
    graph_id: str
    dataset_id: str
    accepted_records: int
    rejected_records: int
    reports_processed: int
    node_count: int
    edge_count: int
    errors: list[str] = []


def load_dataset(path: Path | None = None) -> SyntheticDataset:
    source = Path(path or DEMO_DATASET_PATH)
    if not source.exists():
        raise FileNotFoundError(f"synthetic dataset not found at {source}")
    return SyntheticDataset.model_validate(json.loads(source.read_text(encoding="utf-8")))


def load_reports(path: Path | None = None) -> list[ReportRequest]:
    source = Path(path or DEMO_REPORTS_PATH)
    if not source.exists():
        raise FileNotFoundError(f"synthetic reports not found at {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    return [ReportRequest.model_validate(item) for item in payload]


def seed_demo_case(
    session,
    pipeline: InvestigationPipeline | None = None,
    *,
    dataset_path: Path | None = None,
    reports_path: Path | None = None,
) -> DemoSeedSummary:
    """Load the synthetic dataset and reports into a persisted investigation."""
    pipeline = pipeline or InvestigationPipeline()

    dataset = load_dataset(dataset_path)
    reports = load_reports(reports_path)

    foreign = sorted({report.case_id for report in reports} - {dataset.case_id})
    if foreign:
        raise ValueError(
            f"demo reports reference cases {foreign} that the demo dataset "
            f"({dataset.case_id}) does not cover; seeding would cross a case boundary"
        )

    result = pipeline.ingest_dataset(session, dataset)

    processed = 0
    for report in reports:
        pipeline.process_report(session, report)
        processed += 1

    graph = pipeline.graph_for_case(session, dataset.case_id)

    return DemoSeedSummary(
        case_id=dataset.case_id,
        graph_id=graph.graph_id if graph else default_graph_id(dataset.case_id),
        dataset_id=dataset.dataset_id,
        accepted_records=result.accepted_count,
        rejected_records=result.rejected_count,
        reports_processed=processed,
        node_count=len(graph.nodes) if graph else 0,
        edge_count=len(graph.edges) if graph else 0,
        errors=list(result.errors),
    )
