"""The one authoritative, case-scoped investigation pipeline.

Every write path in the application funnels through :meth:`_persist_and_project`:

    request -> validation -> ingestion -> extraction -> entity resolution
            -> relationship resolution -> graph construction -> persistence

There is deliberately no second way to put data into a case. Structured
ingestion, NLP processing and direct graph construction differ only in how they
*produce* canonical records; once records exist, they take the identical route.

**What is authoritative and what is derived.** The validated record set is the
truth. Entities, relationships and graph snapshots are projections that Stage A
already derives deterministically from records, so they are recomputed from the
persisted records rather than mutated in place. That is what stops the stored
projection from drifting away from the evidence that produced it.

**Why the whole case is reprojected on every run.** Resolution is a property of
the record set, not of one document: a person named in a second report must
merge with the same person from the first, and an edge whose endpoint only
becomes resolvable later must become an edge. Rebuilding from the full case
record set is what makes that true, and it is why the projection is replaced
wholesale rather than appended to.
"""

from datetime import datetime, timezone

from app.db.repositories import (
    CaseRepository,
    DocumentRepository,
    GraphRepository,
    ProjectionRepository,
    RecordRepository,
    RunRepository,
)
from app.schemas.graph import KnowledgeGraph
from app.schemas.investigation import (
    IngestedRecord,
    IngestionResult,
    ProvenanceRecord,
    SyntheticDataset,
)
from app.schemas.nlp import ReportPipelineResult, ReportRequest
from app.services.entity_resolution import EntityResolutionService
from app.services.identity import (
    content_hash,
    mint_analyst_source_id,
    mint_edge_id,
    mint_relationship_id,
)
from app.services.ingestion import IngestionService, validate_and_normalize
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.nlp_extraction import NLPExtractionService


def default_graph_id(case_id: str) -> str:
    """One graph per investigation by default, so reports accumulate per case."""
    return f"graph_{case_id.removeprefix('case_')}"


def _run_id(*parts: str) -> str:
    """A deterministic run id, so re-running the same input is idempotent."""
    return f"run_{content_hash('|'.join(parts))[:16]}"


class InvestigationPipeline:
    def __init__(
        self,
        resolver: EntityResolutionService | None = None,
        graph_service: KnowledgeGraphService | None = None,
        extractor: NLPExtractionService | None = None,
        ingestion_service: IngestionService | None = None,
    ) -> None:
        self.resolver = resolver or EntityResolutionService()
        self.graph_service = graph_service or KnowledgeGraphService(self.resolver)
        self.extractor = extractor or NLPExtractionService()
        self.ingestion_service = ingestion_service or IngestionService()

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    @staticmethod
    def _reject_foreign_records(
        graph_id: str, case_id: str, records: list[IngestedRecord]
    ) -> None:
        foreign = sorted({record.case_id for record in records} - {case_id})
        if foreign:
            raise ValueError(
                f"cannot build graph '{graph_id}' for case '{case_id}': "
                f"records also reference {foreign}"
            )

    @staticmethod
    def _reject_foreign_graph(session, graph_id: str, case_id: str) -> None:
        owner = GraphRepository(session).case_of_graph(graph_id)
        if owner is not None and owner != case_id:
            raise ValueError(
                f"graph '{graph_id}' belongs to case '{owner}' and cannot "
                f"receive records from case '{case_id}'"
            )

    # ------------------------------------------------------------------
    # The single write path
    # ------------------------------------------------------------------

    def _persist_and_project(
        self,
        session,
        *,
        case_id: str,
        graph_id: str,
        new_records: list[IngestedRecord],
        run_id: str | None = None,
    ) -> KnowledgeGraph:
        """Persist records, then rebuild and store the case projection.

        The graph is built from *every* record in the case, not just the ones
        that arrived in this request, which is what lets a later document
        resolve onto an entity an earlier one introduced.
        """
        self._reject_foreign_records(graph_id, case_id, new_records)
        self._reject_foreign_graph(session, graph_id, case_id)

        RecordRepository(session).upsert_many(case_id, new_records, run_id)
        all_records = RecordRepository(session).list_for_case(case_id)

        graph = self.graph_service.build(graph_id, case_id, all_records)

        GraphRepository(session).save(case_id, graph, run_id)
        ProjectionRepository(session).replace(case_id, graph)
        CaseRepository(session).touch(case_id)
        return graph

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def create_case(
        self, session, case_id: str, title: str, description: str | None = None, status: str = "open"
    ):
        cases = CaseRepository(session)
        if cases.get(case_id) is not None:
            raise ValueError(f"investigation '{case_id}' already exists")
        case = cases.create(case_id, title, description, status)
        session.commit()
        return case

    def ingest_dataset(
        self, session, dataset: SyntheticDataset, *, graph_id: str | None = None
    ) -> IngestionResult:
        """Structured ingestion: validate, persist, and reproject the case."""
        result = self.ingestion_service.ingest(
            dataset.case_id, dataset.dataset_id, dataset.records
        )

        case_id = dataset.case_id
        graph_id = graph_id or default_graph_id(case_id)
        self._reject_foreign_graph(session, graph_id, case_id)

        cases = CaseRepository(session)
        case = cases.ensure(case_id, f"Investigation {case_id}")
        if not case.description and dataset.description:
            case.description = dataset.description
        session.flush()

        run_id = _run_id(case_id, dataset.dataset_id, "structured")
        run = RunRepository(session).start(
            case_id, run_id, "structured", dataset_id=dataset.dataset_id, graph_id=graph_id
        )

        self._register_structured_documents(session, case_id, dataset)

        self._persist_and_project(
            session,
            case_id=case_id,
            graph_id=graph_id,
            new_records=result.accepted_records,
            run_id=run_id,
        )

        RunRepository(session).complete(
            run,
            status="completed" if not result.errors else "partial",
            accepted_count=result.accepted_count,
            rejected_count=result.rejected_count,
            errors=result.errors,
        )
        session.commit()
        return result

    def _register_structured_documents(self, session, case_id: str, dataset: SyntheticDataset) -> None:
        """Record the source documents a structured dataset refers to.

        Evidence-source records describe a document fully. Every other record
        still names the document it came from, so a minimal row is created for
        those references too rather than leaving provenance pointing at a
        document the database has never heard of.
        """
        documents = DocumentRepository(session)
        described: set[str] = set()

        for record in dataset.records:
            if record.record_type != "evidence_source":
                continue
            payload = record.payload
            content = payload.get("content")
            documents.upsert(
                case_id,
                record.source_record_id,
                payload.get("source_type") or "synthetic_report",
                title=payload.get("title"),
                content=content,
                content_hash=content_hash(content) if content else None,
                reliability=payload.get("reliability"),
                collected_at=record.observed_at,
            )
            described.add(record.source_record_id)

        for record in dataset.records:
            if record.source_record_id in described:
                continue
            documents.upsert(
                case_id,
                record.source_record_id,
                "structured_record",
                title=None,
                collected_at=record.observed_at,
            )
            described.add(record.source_record_id)

    def process_report(self, session, request: ReportRequest) -> ReportPipelineResult:
        """NLP path: extract, validate through the canonical boundary, persist."""
        extraction = self.extractor.extract(request)
        records, rejected = self.extractor.to_ingested_records(request, extraction)

        case_id = request.case_id
        graph_id = request.graph_id or default_graph_id(case_id)
        self._reject_foreign_graph(session, graph_id, case_id)

        CaseRepository(session).ensure(case_id, f"Investigation {case_id}")
        session.flush()

        run_id = extraction.extraction_run_id
        run = RunRepository(session).start(
            case_id,
            run_id,
            "nlp",
            document_id=request.source_record_id,
            graph_id=graph_id,
        )

        DocumentRepository(session).upsert(
            case_id,
            request.source_record_id,
            "synthetic_report",
            title=request.report_id,
            content=request.text,
            content_hash=extraction.content_hash,
            collected_at=request.observed_at,
        )

        graph = self._persist_and_project(
            session,
            case_id=case_id,
            graph_id=graph_id,
            new_records=records,
            run_id=run_id,
        )

        RunRepository(session).complete(
            run,
            status="completed",
            accepted_count=len(records),
            rejected_count=len(rejected),
            errors=[],
        )
        session.commit()

        return ReportPipelineResult(
            case_id=case_id,
            graph_id=graph.graph_id,
            extraction=extraction,
            ingested_records=records,
            rejected_records=rejected,
            resolved_entity_count=len(graph.nodes),
            graph_node_count=len(graph.nodes),
            graph_edge_count=len(graph.edges),
        )

    def build_graph(
        self, session, graph_id: str, case_id: str, records: list[IngestedRecord]
    ) -> KnowledgeGraph:
        """Direct graph construction from already-canonical records."""
        self._reject_foreign_records(graph_id, case_id, records)

        CaseRepository(session).ensure(case_id, f"Investigation {case_id}")
        session.flush()

        run_id = _run_id(case_id, graph_id, "graph_build")
        run = RunRepository(session).start(case_id, run_id, "graph_build", graph_id=graph_id)

        graph = self._persist_and_project(
            session,
            case_id=case_id,
            graph_id=graph_id,
            new_records=records,
            run_id=run_id,
        )

        RunRepository(session).complete(
            run,
            status="completed",
            accepted_count=len(records),
            rejected_count=0,
            errors=[],
        )
        session.commit()
        return graph

    def create_analyst_relationship(
        self,
        session,
        case_id: str,
        *,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: str,
        confidence: float = 1.0,
        context: str | None = None,
        analyst_id: str | None = None,
        note: str | None = None,
        occurred_at: datetime | None = None,
    ) -> tuple[KnowledgeGraph, str]:
        """Record a relationship asserted by a human analyst.

        This takes the same route as every other write: the payload passes the
        canonical validation boundary, becomes an ``IngestedRecord``, and goes
        through ``_persist_and_project``. There is no analyst-only shortcut into
        the graph, so an asserted link is resolved, projected and evidenced by
        exactly the same code as one read out of a document.

        **Provenance is not fabricated.** No document id, no content hash and no
        character span is invented, because none exists. The provenance points at
        the assertion itself, carries ``source_type='analyst_assertion'``, and is
        typed ``unknown`` - meaning supporting source evidence has not been
        established in this system. The analyst may have good reasons; the
        database simply does not hold them, and it must not imply otherwise.

        **Semantics are preserved.** The record is ``inferred``: no source
        observed it. If it duplicates a relationship a document already asserts,
        Stage A edge identity pools both onto one edge and the weakest assertion
        wins, so adding an analyst opinion can never upgrade a link to observed.

        Returns the rebuilt graph and the id of the edge the assertion landed on.
        """
        entities = {
            row.canonical_id: row for row in ProjectionRepository(session).list_entities(case_id)
        }
        missing = [
            entity_id
            for entity_id in (from_entity_id, to_entity_id)
            if entity_id not in entities
        ]
        if missing:
            raise ValueError(
                f"entities {sorted(missing)} are not part of investigation '{case_id}'; "
                "an analyst relationship cannot span investigations or reference an "
                "entity this case has never recorded"
            )
        if from_entity_id == to_entity_id:
            raise ValueError("an analyst relationship must join two different entities")

        # Graph endpoints are matched on the *source* identifiers a record used,
        # so the canonical id the analyst selected is translated back to one of
        # the source ids that resolved into it. Picking the lowest keeps the
        # minted record id deterministic.
        source_endpoint = sorted(entities[from_entity_id].source_entity_ids)[0]
        target_endpoint = sorted(entities[to_entity_id].source_entity_ids)[0]

        assertion_source_id = mint_analyst_source_id(
            case_id, relationship_type, from_entity_id, to_entity_id, analyst_id
        )
        record_id = mint_relationship_id(
            case_id, relationship_type, source_endpoint, target_endpoint, assertion_source_id
        )
        recorded_at = datetime.now(timezone.utc)

        payload = {
            "record_id": record_id,
            "from_entity_id": source_endpoint,
            "to_entity_id": target_endpoint,
            "relationship_type": relationship_type,
            "source_record_id": assertion_source_id,
            "confidence": confidence,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "analyst_created": True,
            "analyst_id": analyst_id,
            "analyst_note": note,
        }
        if context is not None:
            payload["context"] = context

        # The one validation boundary, same as structured and NLP records.
        normalized = validate_and_normalize("relationship", payload)

        record = IngestedRecord(
            case_id=case_id,
            record_id=record_id,
            record_type="relationship",
            observed_at=recorded_at,
            data=normalized,
            assertion_type="inferred",
            provenance=[
                ProvenanceRecord(
                    case_id=case_id,
                    source_record_id=assertion_source_id,
                    record_id=record_id,
                    provenance_type="unknown",
                    document_id=None,
                    content_hash=None,
                    source_type="analyst_assertion",
                    observed_at=recorded_at,
                )
            ],
        )

        graph_id = default_graph_id(case_id)
        self._reject_foreign_graph(session, graph_id, case_id)

        run_id = _run_id(case_id, record_id, "analyst")
        run = RunRepository(session).start(case_id, run_id, "analyst", graph_id=graph_id)

        graph = self._persist_and_project(
            session,
            case_id=case_id,
            graph_id=graph_id,
            new_records=[record],
            run_id=run_id,
        )

        RunRepository(session).complete(
            run, status="completed", accepted_count=1, rejected_count=0, errors=[]
        )
        session.commit()

        return graph, mint_edge_id(case_id, relationship_type, from_entity_id, to_entity_id)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    def graph_by_id(session, graph_id: str) -> KnowledgeGraph | None:
        return GraphRepository(session).current(graph_id)

    @staticmethod
    def graph_for_case(session, case_id: str) -> KnowledgeGraph | None:
        return GraphRepository(session).current_for_case(case_id)

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
