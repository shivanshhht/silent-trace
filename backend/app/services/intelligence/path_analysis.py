"""Connection paths between two entities, with every hop justified.

The purpose of this module is to answer "why does Silent Trace say these two are
connected?" without the investigator having to trust a score. Every hop returned
carries its relationship type, its context, whether the underlying claim was
observed or inferred, its confidence, the provenance ids backing it, the source
records and documents it came from, and its timestamps. A path with no
supporting evidence would be indistinguishable from a guess, so the evidence
travels with it.

**Bounds.** Paths are simple (no repeated entity) and capped at ``max_depth``
hops, default 3. Where a pair of entities is linked by several relationships,
each combination is a distinct path, because "they spoke" and "they transacted"
are different answers to the question. Enumeration is capped so a dense graph
cannot produce an unbounded response, and the cap is reported.

**Case isolation.** The view is built for exactly one case, so a path cannot
leave it. Endpoints are additionally checked for membership, and an entity from
another investigation is reported as not present rather than silently returning
no paths, which would look identical to "not connected".
"""

from itertools import product

from app.schemas.intelligence import ConnectionPath, PathEdge, PathResponse
from app.schemas.investigation import weakest_assertion
from app.services.intelligence.graph_view import AnalysisEdge, CaseGraphView


DEFAULT_MAX_DEPTH = 3
MAX_PATHS = 50


def _node_paths(
    view: CaseGraphView, source: str, target: str, max_depth: int
) -> list[list[str]]:
    """Depth-limited enumeration of simple node paths, in deterministic order."""
    found: list[list[str]] = []
    stack: list[tuple[str, list[str], set[str]]] = [(source, [source], {source})]

    while stack:
        current, path, visited = stack.pop()
        if len(path) - 1 >= max_depth:
            continue
        for neighbour in reversed(view.neighbours(current)):
            if neighbour in visited:
                continue
            extended = path + [neighbour]
            if neighbour == target:
                found.append(extended)
                continue
            stack.append((neighbour, extended, visited | {neighbour}))

    found.sort(key=lambda nodes: (len(nodes), nodes))
    return found


def _to_path_edge(view: CaseGraphView, edge: AnalysisEdge, step_from: str) -> PathEdge:
    """Render one hop in the direction the path traverses it.

    The stored relationship keeps its own direction; ``from``/``to`` here are the
    order of traversal, and the relationship type still says what was asserted.
    """
    step_to = edge.other_end(step_from)
    return PathEdge(
        from_entity_id=step_from,
        to_entity_id=step_to,
        from_label=view.label(step_from),
        to_label=view.label(step_to),
        relationship_id=edge.relationship_id,
        relationship_type=edge.relationship_type,  # type: ignore[arg-type]
        context=edge.context,  # type: ignore[arg-type]
        assertion_type=edge.assertion_type,  # type: ignore[arg-type]
        confidence=edge.confidence,
        evidence_ids=list(edge.evidence_ids),
        source_record_ids=list(edge.source_record_ids),
        document_ids=list(edge.document_ids),
        observed_at=edge.observed_at,
        occurred_at=edge.occurred_at,
    )


def connection_paths(
    view: CaseGraphView,
    source_entity_id: str,
    target_entity_id: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> PathResponse:
    max_depth = max(1, min(max_depth, 6))

    base = {
        "case_id": view.case_id,
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "max_depth": max_depth,
    }

    missing = [
        entity_id
        for entity_id in (source_entity_id, target_entity_id)
        if entity_id not in view.entities
    ]
    if missing:
        return PathResponse(
            **base,
            paths=[],
            count=0,
            insufficient_data=True,
            reason=(
                f"entities {sorted(missing)} are not part of investigation "
                f"{view.case_id}; connection analysis never spans investigations"
            ),
        )
    if source_entity_id == target_entity_id:
        return PathResponse(
            **base,
            paths=[],
            count=0,
            insufficient_data=True,
            reason="source and target are the same entity",
        )

    node_paths = _node_paths(view, source_entity_id, target_entity_id, max_depth)
    if not node_paths:
        return PathResponse(
            **base,
            paths=[],
            count=0,
            insufficient_data=True,
            reason=(
                f"no path of {max_depth} hops or fewer connects these entities in "
                "the recorded relationships"
            ),
        )

    paths: list[ConnectionPath] = []
    truncated = False
    for nodes in node_paths:
        hops = [view.edges_between(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
        if any(not options for options in hops):
            continue
        for combination in product(*hops):
            if len(paths) >= MAX_PATHS:
                truncated = True
                break

            edges: list[PathEdge] = []
            step_from = nodes[0]
            for edge in combination:
                edges.append(_to_path_edge(view, edge, step_from))
                step_from = edge.other_end(step_from)

            confidence = 1.0
            for edge in combination:
                confidence *= edge.confidence
            assertion = weakest_assertion([edge.assertion_type for edge in combination])

            evidence_ids: list[str] = []
            for edge in combination:
                for evidence_id in edge.evidence_ids:
                    if evidence_id not in evidence_ids:
                        evidence_ids.append(evidence_id)

            described = " -> ".join(
                [view.label(nodes[0])]
                + [f"[{edge.relationship_type}] {view.label(hop.to_entity_id)}"
                   for edge, hop in zip(combination, edges)]
            )
            paths.append(
                ConnectionPath(
                    case_id=view.case_id,
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    length=len(combination),
                    edges=edges,
                    path_confidence=round(confidence, 6),
                    assertion_type=assertion,  # type: ignore[arg-type]
                    evidence_ids=evidence_ids,
                    explanation=(
                        f"{len(combination)}-hop connection: {described}. "
                        f"Every hop above is backed by the listed evidence; the path "
                        f"is {assertion} overall because that is its weakest link."
                    ),
                )
            )
        if truncated:
            break

    paths.sort(
        key=lambda item: (
            item.length,
            -item.path_confidence,
            [edge.relationship_id for edge in item.edges],
        )
    )

    return PathResponse(
        **base,
        paths=paths,
        count=len(paths),
        insufficient_data=False,
        reason=(
            f"enumeration capped at {MAX_PATHS} paths; more exist" if truncated else None
        ),
    )
