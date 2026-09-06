from datetime import datetime, timezone

import pytest

from app.api.dependencies import graph_store
from app.schemas.investigation import IngestedRecord, ProvenanceRecord


DEFAULT_CASE = "case_test-001"
DEFAULT_SOURCE = "src_test-001"
DEFAULT_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_graph_store():
    """The graph store is process-wide, so each test starts from an empty one."""
    graph_store.clear()
    yield
    graph_store.clear()


@pytest.fixture
def make_record():
    """Build a canonical IngestedRecord for tests that exercise later stages."""

    def _make(
        record_id: str,
        record_type: str,
        data: dict,
        *,
        case_id: str = DEFAULT_CASE,
        source_record_id: str = DEFAULT_SOURCE,
        assertion_type: str = "observed",
        observed_at: datetime = DEFAULT_TIME,
        provenance: list[ProvenanceRecord] | None = None,
    ) -> IngestedRecord:
        return IngestedRecord(
            case_id=case_id,
            record_id=record_id,
            record_type=record_type,
            observed_at=observed_at,
            data=data,
            assertion_type=assertion_type,
            provenance=provenance
            or [
                ProvenanceRecord(
                    case_id=case_id,
                    source_record_id=source_record_id,
                    record_id=record_id,
                    observed_at=observed_at,
                )
            ],
        )

    return _make
