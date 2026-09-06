"""Case-scoped data access.

Every method that touches case data takes ``case_id`` and filters on it. There
is no repository method that can read or write across investigations, because
the way a leak happens in practice is a convenience query that "just" forgets a
predicate. The one deliberate exception is
:meth:`GraphRepository.case_of_graph`, which exists precisely so the pipeline
can *detect* an attempt to reuse one graph id across two cases and refuse it.

Timestamps are normalized to UTC on the way in and re-attached on the way out.
SQLite discards the offset it is given; PostgreSQL does not. Normalizing at this
boundary means the rest of the application sees timezone-aware UTC either way.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.models import (
    EntityProvenance,
    EntityRow,
    GraphSnapshot,
    IngestedRecordRow,
    IngestionRun,
    InvestigationCase,
    ProvenanceRow,
    RelationshipProvenance,
    RelationshipRow,
    SourceDocument,
)
from app.schemas.graph import KnowledgeGraph
from app.schemas.investigation import IngestedRecord, ProvenanceRecord
from app.services.entity_resolution import resolution_key
from app.services.identity import mint_provenance_id


def to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CaseRepository:
    def __init__(self, session) -> None:
        self.session = session

    def get(self, case_id: str) -> InvestigationCase | None:
        return self.session.get(InvestigationCase, case_id)

    def list_all(self) -> list[InvestigationCase]:
        return list(
            self.session.execute(
                select(InvestigationCase).order_by(InvestigationCase.created_at)
            ).scalars()
        )

    def create(
        self,
        case_id: str,
        title: str,
        description: str | None = None,
        status: str = "open",
    ) -> InvestigationCase:
        case = InvestigationCase(
            case_id=case_id, title=title, description=description, status=status
        )
        self.session.add(case)
        self.session.flush()
        return case

    def ensure(self, case_id: str, title: str | None = None) -> InvestigationCase:
        """Get the case, creating a minimal record for it if the pipeline is first to see it.

        Ingesting into an unregistered case is legitimate - the dataset itself is
        what declares the investigation exists - but the case row must be created
        before any of its data, so nothing is ever parented to a missing case.
        """
        case = self.get(case_id)
        if case is not None:
            return case
        return self.create(case_id, title or case_id, None, "open")

    def touch(self, case_id: str) -> None:
        case = self.get(case_id)
        if case is not None:
            case.updated_at = datetime.now(timezone.utc)


class DocumentRepository:
    def __init__(self, session) -> None:
        self.session = session

    def upsert(
        self,
        case_id: str,
        document_id: str,
        source_type: str,
        *,
        title: str | None = None,
        content: str | None = None,
        content_hash: str | None = None,
        reliability: str | None = None,
        collected_at: datetime | None = None,
    ) -> SourceDocument:
        existing = self.session.get(SourceDocument, {"case_id": case_id, "document_id": document_id})
        if existing is None:
            existing = SourceDocument(case_id=case_id, document_id=document_id, source_type=source_type)
            self.session.add(existing)
        existing.source_type = source_type
        if title is not None:
            existing.title = title
        if content is not None:
            existing.content = content
        if content_hash is not None:
            existing.content_hash = content_hash
        if reliability is not None:
            existing.reliability = reliability
        if collected_at is not None:
            existing.collected_at = to_utc(collected_at)
        self.session.flush()
        return existing

    def list_for_case(self, case_id: str) -> list[SourceDocument]:
        return list(
            self.session.execute(
                select(SourceDocument)
                .where(SourceDocument.case_id == case_id)
                .order_by(SourceDocument.document_id)
            ).scalars()
        )


class RunRepository:
    def __init__(self, session) -> None:
        self.session = session

    def start(
        self,
        case_id: str,
        run_id: str,
        kind: str,
        *,
        document_id: str | None = None,
        dataset_id: str | None = None,
        graph_id: str | None = None,
    ) -> IngestionRun:
        run = self.session.get(IngestionRun, {"case_id": case_id, "run_id": run_id})
        if run is None:
            run = IngestionRun(case_id=case_id, run_id=run_id, kind=kind, status="running")
            self.session.add(run)
        run.kind = kind
        run.status = "running"
        run.document_id = document_id
        run.dataset_id = dataset_id
        run.graph_id = graph_id
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = None
        self.session.flush()
        return run

    def complete(
        self,
        run: IngestionRun,
        *,
        status: str,
        accepted_count: int,
        rejected_count: int,
        errors: list[str] | None = None,
    ) -> IngestionRun:
        run.status = status
        run.accepted_count = accepted_count
        run.rejected_count = rejected_count
        run.errors = list(errors or [])
        run.completed_at = datetime.now(timezone.utc)
        self.session.flush()
        return run

    def list_for_case(self, case_id: str) -> list[IngestionRun]:
        return list(
            self.session.execute(
                select(IngestionRun)
                .where(IngestionRun.case_id == case_id)
                .order_by(IngestionRun.started_at)
            ).scalars()
        )


def _provenance_id(case_id: str, provenance: ProvenanceRecord) -> str:
    return mint_provenance_id(
        case_id,
        provenance.record_id,
        provenance.source_record_id,
        provenance.character_start,
        provenance.character_end,
        provenance.snippet,
        provenance.extraction_run_id,
    )


class RecordRepository:
    """The authoritative record store, with its provenance."""

    def __init__(self, session) -> None:
        self.session = session

    def upsert_many(
        self, case_id: str, records: list[IngestedRecord], run_id: str | None = None
    ) -> None:
        for record in records:
            if record.case_id != case_id:
                raise ValueError(
                    f"record '{record.record_id}' belongs to case '{record.case_id}', "
                    f"not '{case_id}'; persistence cannot cross a case boundary"
                )
            row = self.session.get(
                IngestedRecordRow, {"case_id": case_id, "record_id": record.record_id}
            )
            if row is None:
                row = IngestedRecordRow(case_id=case_id, record_id=record.record_id)
                self.session.add(row)
            row.record_type = record.record_type
            row.observed_at = to_utc(record.observed_at)
            row.assertion_type = record.assertion_type
            row.data = record.data
            row.run_id = run_id
            self.session.flush()
            self.upsert_provenance(case_id, record.provenance)

    def upsert_provenance(self, case_id: str, provenance: list[ProvenanceRecord]) -> list[str]:
        """Write provenance rows idempotently and return their ids."""
        ids: list[str] = []
        for item in provenance:
            if item.case_id != case_id:
                raise ValueError(
                    f"provenance for '{item.record_id}' belongs to case '{item.case_id}', "
                    f"not '{case_id}'"
                )
            provenance_id = _provenance_id(case_id, item)
            ids.append(provenance_id)
            row = self.session.get(
                ProvenanceRow, {"case_id": case_id, "provenance_id": provenance_id}
            )
            if row is None:
                row = ProvenanceRow(case_id=case_id, provenance_id=provenance_id)
                self.session.add(row)
            row.record_id = item.record_id
            row.source_record_id = item.source_record_id
            row.provenance_type = item.provenance_type
            row.document_id = item.document_id
            row.content_hash = item.content_hash
            row.source_type = item.source_type
            row.extraction_run_id = item.extraction_run_id
            row.character_start = item.character_start
            row.character_end = item.character_end
            row.snippet = item.snippet
            row.observed_at = to_utc(item.observed_at)
        self.session.flush()
        return ids

    def provenance_for_record(self, case_id: str, record_id: str) -> list[ProvenanceRecord]:
        rows = self.session.execute(
            select(ProvenanceRow)
            .where(ProvenanceRow.case_id == case_id, ProvenanceRow.record_id == record_id)
            .order_by(ProvenanceRow.provenance_id)
        ).scalars()
        return [self.to_schema(row) for row in rows]

    @staticmethod
    def to_schema(row: ProvenanceRow) -> ProvenanceRecord:
        return ProvenanceRecord(
            case_id=row.case_id,
            source_record_id=row.source_record_id,
            record_id=row.record_id,
            provenance_type=row.provenance_type,
            document_id=row.document_id,
            content_hash=row.content_hash,
            source_type=row.source_type,
            extraction_run_id=row.extraction_run_id,
            character_start=row.character_start,
            character_end=row.character_end,
            snippet=row.snippet,
            observed_at=to_utc(row.observed_at),
        )

    def list_for_case(self, case_id: str) -> list[IngestedRecord]:
        """Rehydrate every record of a case into its canonical Stage A shape."""
        record_rows = list(
            self.session.execute(
                select(IngestedRecordRow)
                .where(IngestedRecordRow.case_id == case_id)
                .order_by(IngestedRecordRow.created_at, IngestedRecordRow.record_id)
            ).scalars()
        )
        provenance_rows = list(
            self.session.execute(
                select(ProvenanceRow).where(ProvenanceRow.case_id == case_id)
            ).scalars()
        )
        by_record: dict[str, list[ProvenanceRow]] = {}
        for row in provenance_rows:
            by_record.setdefault(row.record_id, []).append(row)

        records: list[IngestedRecord] = []
        for row in record_rows:
            attached = sorted(by_record.get(row.record_id, []), key=lambda p: p.provenance_id)
            if not attached:
                # A record without provenance cannot satisfy the Stage A contract
                # and must not be silently resurrected as evidence-free.
                raise ValueError(
                    f"record '{row.record_id}' in case '{case_id}' has no persisted provenance"
                )
            records.append(
                IngestedRecord(
                    case_id=row.case_id,
                    record_id=row.record_id,
                    record_type=row.record_type,
                    observed_at=to_utc(row.observed_at),
                    data=row.data,
                    assertion_type=row.assertion_type,
                    provenance=[self.to_schema(p) for p in attached],
                )
            )
        return records

    def list_evidence(self, case_id: str) -> list[tuple[ProvenanceRow, str | None, str | None]]:
        """Provenance for a case, paired with the record type and assertion it backs."""
        rows = self.session.execute(
            select(ProvenanceRow, IngestedRecordRow.record_type, IngestedRecordRow.assertion_type)
            .join(
                IngestedRecordRow,
                (IngestedRecordRow.case_id == ProvenanceRow.case_id)
                & (IngestedRecordRow.record_id == ProvenanceRow.record_id),
                isouter=True,
            )
            .where(ProvenanceRow.case_id == case_id)
            .order_by(ProvenanceRow.record_id, ProvenanceRow.provenance_id)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def count(self, case_id: str) -> int:
        return len(
            list(
                self.session.execute(
                    select(IngestedRecordRow.record_id).where(IngestedRecordRow.case_id == case_id)
                ).scalars()
            )
        )


class ProjectionRepository:
    """Entities and relationships, rewritten wholesale from the graph projection."""

    def __init__(self, session) -> None:
        self.session = session

    def replace(self, case_id: str, graph: KnowledgeGraph) -> None:
        if graph.case_id != case_id:
            raise ValueError(
                f"graph '{graph.graph_id}' belongs to case '{graph.case_id}', not '{case_id}'"
            )

        # Delete children before parents so the foreign keys stay satisfied.
        for model in (RelationshipProvenance, EntityProvenance, RelationshipRow, EntityRow):
            self.session.execute(delete(model).where(model.case_id == case_id))
        self.session.flush()

        records = RecordRepository(self.session)

        for node in graph.nodes:
            self.session.add(
                EntityRow(
                    case_id=case_id,
                    canonical_id=node.node_id,
                    entity_type=node.entity_type,
                    canonical_value=resolution_key(node.entity_type, node.attributes)[:500],
                    attributes=node.attributes,
                    source_entity_ids=list(node.source_entity_ids),
                    match_status=node.match_status,
                    match_confidence=node.match_confidence,
                    assertion_type=node.assertion_type,
                    review_candidates=list(node.review_candidates),
                )
            )
        self.session.flush()

        for node in graph.nodes:
            for provenance_id in dict.fromkeys(
                records.upsert_provenance(case_id, node.provenance)
            ):
                self.session.add(
                    EntityProvenance(
                        case_id=case_id, canonical_id=node.node_id, provenance_id=provenance_id
                    )
                )
        self.session.flush()

        for edge in graph.edges:
            self.session.add(
                RelationshipRow(
                    case_id=case_id,
                    relationship_id=edge.edge_id,
                    from_entity_id=edge.from_node_id,
                    to_entity_id=edge.to_node_id,
                    relationship_type=edge.relationship_type,
                    assertion_type=edge.assertion_type,
                    confidence=edge.confidence,
                    source_record_ids=list(edge.source_record_ids),
                    observed_at=to_utc(edge.observed_at),
                    occurred_at=to_utc(edge.occurred_at),
                )
            )
        self.session.flush()

        for edge in graph.edges:
            for provenance_id in dict.fromkeys(
                records.upsert_provenance(case_id, edge.provenance)
            ):
                self.session.add(
                    RelationshipProvenance(
                        case_id=case_id,
                        relationship_id=edge.edge_id,
                        provenance_id=provenance_id,
                    )
                )
        self.session.flush()

    def list_entities(self, case_id: str) -> list[EntityRow]:
        return list(
            self.session.execute(
                select(EntityRow)
                .where(EntityRow.case_id == case_id)
                .order_by(EntityRow.entity_type, EntityRow.canonical_id)
            ).scalars()
        )

    def list_relationships(self, case_id: str) -> list[RelationshipRow]:
        return list(
            self.session.execute(
                select(RelationshipRow)
                .where(RelationshipRow.case_id == case_id)
                .order_by(RelationshipRow.relationship_type, RelationshipRow.relationship_id)
            ).scalars()
        )

    def provenance_ids_for_entity(self, case_id: str, canonical_id: str) -> list[str]:
        return list(
            self.session.execute(
                select(EntityProvenance.provenance_id).where(
                    EntityProvenance.case_id == case_id,
                    EntityProvenance.canonical_id == canonical_id,
                )
            ).scalars()
        )

    def provenance_ids_for_relationship(self, case_id: str, relationship_id: str) -> list[str]:
        return list(
            self.session.execute(
                select(RelationshipProvenance.provenance_id).where(
                    RelationshipProvenance.case_id == case_id,
                    RelationshipProvenance.relationship_id == relationship_id,
                )
            ).scalars()
        )


class GraphRepository:
    """Versioned graph snapshots."""

    def __init__(self, session) -> None:
        self.session = session

    def case_of_graph(self, graph_id: str) -> str | None:
        """Which case owns this graph id, if any.

        Deliberately not case-scoped: this is the lookup that lets the pipeline
        refuse to let a second investigation write into an existing graph.
        """
        return self.session.execute(
            select(GraphSnapshot.case_id).where(GraphSnapshot.graph_id == graph_id).limit(1)
        ).scalar_one_or_none()

    def _next_version(self, case_id: str, graph_id: str) -> int:
        versions = list(
            self.session.execute(
                select(GraphSnapshot.version).where(
                    GraphSnapshot.case_id == case_id, GraphSnapshot.graph_id == graph_id
                )
            ).scalars()
        )
        return (max(versions) + 1) if versions else 1

    def save(self, case_id: str, graph: KnowledgeGraph, run_id: str | None = None) -> GraphSnapshot:
        if graph.case_id != case_id:
            raise ValueError(
                f"graph '{graph.graph_id}' belongs to case '{graph.case_id}', not '{case_id}'"
            )
        version = self._next_version(case_id, graph.graph_id)

        for previous in self.session.execute(
            select(GraphSnapshot).where(
                GraphSnapshot.case_id == case_id,
                GraphSnapshot.graph_id == graph.graph_id,
                GraphSnapshot.is_current.is_(True),
            )
        ).scalars():
            previous.is_current = False

        payload = graph.model_dump(mode="json")
        snapshot = GraphSnapshot(
            snapshot_id=f"snp_{graph.graph_id}_{version}",
            case_id=case_id,
            graph_id=graph.graph_id,
            version=version,
            is_current=True,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            nodes=payload["nodes"],
            edges=payload["edges"],
            unresolved_record_ids=payload["unresolved_record_ids"],
            rejected_edges=payload["rejected_edges"],
            run_id=run_id,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    @staticmethod
    def to_schema(snapshot: GraphSnapshot) -> KnowledgeGraph:
        return KnowledgeGraph(
            graph_id=snapshot.graph_id,
            case_id=snapshot.case_id,
            nodes=snapshot.nodes,
            edges=snapshot.edges,
            unresolved_record_ids=snapshot.unresolved_record_ids,
            rejected_edges=snapshot.rejected_edges,
        )

    def current_row(self, graph_id: str) -> GraphSnapshot | None:
        return self.session.execute(
            select(GraphSnapshot)
            .where(GraphSnapshot.graph_id == graph_id, GraphSnapshot.is_current.is_(True))
            .order_by(GraphSnapshot.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def current(self, graph_id: str) -> KnowledgeGraph | None:
        row = self.current_row(graph_id)
        return None if row is None else self.to_schema(row)

    def current_for_case(self, case_id: str) -> KnowledgeGraph | None:
        row = self.session.execute(
            select(GraphSnapshot)
            .where(GraphSnapshot.case_id == case_id, GraphSnapshot.is_current.is_(True))
            .order_by(GraphSnapshot.generated_at.desc(), GraphSnapshot.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if row is None else self.to_schema(row)

    def versions_for_case(self, case_id: str) -> list[GraphSnapshot]:
        return list(
            self.session.execute(
                select(GraphSnapshot)
                .where(GraphSnapshot.case_id == case_id)
                .order_by(GraphSnapshot.graph_id, GraphSnapshot.version)
            ).scalars()
        )
