from fastapi import APIRouter, HTTPException

from app.api.dependencies import SessionDep, pipeline
from app.schemas.investigation import IngestionRequest, IngestionResult

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.post("", response_model=IngestionResult)
def ingest_dataset(request: IngestionRequest, session: SessionDep) -> IngestionResult:
    """Validate a dataset and persist what passes.

    The response shape is unchanged from Stage A - accepted records, per-record
    errors and counts - but the accepted records now land in the investigation
    and the case projection is rebuilt from them.
    """
    try:
        return pipeline.ingest_dataset(session, request.dataset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
