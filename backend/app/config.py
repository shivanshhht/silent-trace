"""Runtime configuration.

The database URL is the only setting that differs between development, test and
a future production deployment. It is read from the environment so that moving
from the local SQLite file to PostgreSQL is a configuration change rather than
a code change:

    SILENT_TRACE_DATABASE_URL=postgresql+psycopg://user:pass@host/silent_trace
"""

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
SYNTHETIC_DATA_DIR = REPO_ROOT / "data" / "synthetic"

DEMO_DATASET_PATH = SYNTHETIC_DATA_DIR / "demo_dataset.json"
DEMO_REPORTS_PATH = SYNTHETIC_DATA_DIR / "reports.json" 

DEFAULT_SQLITE_PATH = BACKEND_ROOT / "silent_trace.db"

DATABASE_URL_ENV = "SILENT_TRACE_DATABASE_URL"
POSTGRES_URL_ENV = "SILENT_TRACE_POSTGRES_URL"


def database_url() -> str:
    """Resolve the active database URL, defaulting to the local SQLite file."""
    configured = os.environ.get(POSTGRES_URL_ENV) or os.environ.get(DATABASE_URL_ENV)
    if configured:
        return configured
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
