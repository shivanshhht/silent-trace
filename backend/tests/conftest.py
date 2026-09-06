from datetime import datetime, timezone

import pytest

from app.db import database
from app.schemas.investigation import IngestedRecord, ProvenanceRecord


DEFAULT_CASE = "case_test-001"
DEFAULT_SOURCE = "src_test-001"
DEFAULT_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path):
    """Point every test at its own SQLite file.

    A real file rather than an in-memory database, so the tests exercise the
    same storage path the application uses, and a fresh one per test so no test
    can pass because of state another test left behind.
    """
    database.configure(f"sqlite:///{(tmp_path / 'silent_trace_test.db').as_posix()}")
    database.create_all()
    yield
    database.dispose()


@pytest.fixture
def session():
    """A unit of work for tests that exercise repositories or the pipeline directly."""
    with database.session_scope() as active:
        yield active


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
