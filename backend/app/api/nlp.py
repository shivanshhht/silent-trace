from fastapi import APIRouter, HTTPException

from app.api.dependencies import default_graph_id, extractor, graph_service, graph_store
from app.schemas.nlp import (
    BatchReportRequest,
    ReportExtraction,
    ReportPipelineResult,
    ReportRequest,
)

router = APIRouter(prefix="/api/nlp", tags=["nlp"])


@router.post("/extract", response_model=ReportExtraction)
def extract_report(request: ReportRequest) -> ReportExtraction:
    try:
        return extractor.extract(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/process", response_model=ReportPipelineResult)
def process_report(request: ReportRequest) -> ReportPipelineResult:
    """Run report -> extraction -> canonical validation -> resolution -> graph.

    The resulting graph is written to the shared store, so it is immediately
    retrievable through ``GET /api/graph/{graph_id}``. Processing a second
    report for the same case folds it into that case graph.
    """
    try:
        extraction = extractor.extract(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    records, rejected = extractor.to_ingested_records(request, extraction)
    graph_id = request.graph_id or default_graph_id(request.case_id)

    existing = graph_store.get(graph_id)
    if existing is not None and existing.case_id != request.case_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"graph '{graph_id}' belongs to case '{existing.case_id}' and cannot "
                f"receive records from case '{request.case_id}'"
            ),
        )

    merged = graph_store.merge_records(graph_id, records)
    try:
        graph = graph_service.build(graph_id, request.case_id, merged)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    graph_store.put(graph, merged)

    return ReportPipelineResult(
        case_id=request.case_id,
        graph_id=graph.graph_id,
        extraction=extraction,
        ingested_records=records,
        rejected_records=rejected,
        resolved_entity_count=len(graph.nodes),
        graph_node_count=len(graph.nodes),
        graph_edge_count=len(graph.edges),
    )


@router.post("/extract/batch", response_model=list[ReportExtraction])
def extract_batch(request: BatchReportRequest) -> list[ReportExtraction]:
    try:
        return [extractor.extract(report) for report in request.reports]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
