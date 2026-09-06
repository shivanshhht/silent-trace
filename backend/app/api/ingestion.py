from fastapi import APIRouter

from app.api.dependencies import ingestion_service
from app.schemas.investigation import IngestionRequest, IngestionResult

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.post("", response_model=IngestionResult)
def ingest_dataset(request: IngestionRequest) -> IngestionResult:
    dataset = request.dataset
    return ingestion_service.ingest(dataset.case_id, dataset.dataset_id, dataset.records)
