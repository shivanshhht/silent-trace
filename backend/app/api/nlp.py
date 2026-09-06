from fastapi import APIRouter, HTTPException

from app.api.dependencies import SessionDep, extractor, pipeline
from app.schemas.nlp import (
    BatchReportRequest,
    ReportExtraction,
    ReportPipelineResult,
    ReportRequest,
)

router = APIRouter(prefix="/api/nlp", tags=["nlp"])


@router.post("/extract", response_model=ReportExtraction)
def extract_report(request: ReportRequest) -> ReportExtraction:
    """Extraction alone, with nothing written.

    Kept as a read-only view of what the extractor would produce, so a report
    can be inspected before it is committed to an investigation.
    """
    try:
        return extractor.extract(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/process", response_model=ReportPipelineResult)
def process_report(request: ReportRequest, session: SessionDep) -> ReportPipelineResult:
    """Run report -> extraction -> canonical validation -> resolution -> graph -> persistence.

    The resulting graph is persisted, so it is retrievable through
    ``GET /api/graph/{graph_id}`` and ``GET /api/investigations/{case_id}/graph``
    and survives a restart. Processing a second report for the same case folds
    it into that investigation.
    """
    try:
        return pipeline.process_report(session, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/extract/batch", response_model=list[ReportExtraction])
def extract_batch(request: BatchReportRequest) -> list[ReportExtraction]:
    try:
        return [extractor.extract(report) for report in request.reports]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
