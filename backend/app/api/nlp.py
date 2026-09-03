from fastapi import APIRouter

from app.schemas.graph import EntityResolutionResult
from app.schemas.nlp import BatchReportRequest, ReportExtraction, ReportPipelineResult, ReportRequest
from app.services.entity_resolution import EntityResolutionService
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.nlp_extraction import NLPExtractionService

router = APIRouter(prefix="/api/nlp", tags=["nlp"])
_extractor = NLPExtractionService()
_resolver = EntityResolutionService()
_graphs = KnowledgeGraphService(_resolver)


@router.post("/extract", response_model=ReportExtraction)
def extract_report(request: ReportRequest) -> ReportExtraction:
    return _extractor.extract(request)


@router.post("/process", response_model=ReportPipelineResult)
def process_report(request: ReportRequest) -> ReportPipelineResult:
    extraction = _extractor.extract(request)
    records = _extractor.to_ingested_records(request, extraction)
    resolved = _resolver.resolve(records)
    graph = _graphs.build(f"graph_{request.report_id.removeprefix('rpt_')}", records)
    return ReportPipelineResult(extraction=extraction, ingested_records=records, resolved_entity_count=len(resolved.entities), graph_node_count=len(graph.nodes), graph_edge_count=len(graph.edges))


@router.post("/extract/batch", response_model=list[ReportExtraction])
def extract_batch(request: BatchReportRequest) -> list[ReportExtraction]:
    return [_extractor.extract(report) for report in request.reports]
