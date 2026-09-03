from fastapi import APIRouter

from app.schemas.investigation import IngestionRequest, IngestionResult
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])
_service = IngestionService()


@router.post("", response_model=IngestionResult)
def ingest_dataset(request: IngestionRequest) -> IngestionResult:
    return _service.ingest(request.dataset.dataset_id, request.dataset.records)
