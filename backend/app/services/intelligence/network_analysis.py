"""Centrality over the persisted case graph.

Algorithms are exact rather than sampled, and implemented here rather than
pulled from a graph library, for three reasons: the graphs are investigation
sized, every result must be reproducible byte for byte across runs, and each
score has to arrive attached to an explanation phrased in terms of records and
relationships rather than in terms of a number.

Determinism comes from iterating ``view.node_ids`` (sorted) everywhere and from
breaking rank ties on entity id.

**What these metrics are.** Degree counts direct connections. Weighted degree
counts recorded interactions, so one call and forty calls differ. Betweenness
(Brandes, exact) counts how often an entity sits on a shortest path between two
others. Closeness measures how few hops it takes to reach the rest of the graph.

**What they are not.** None of them measures wrongdoing. An entity can top every
one of these rankings by being a switchboard, a landlord, a family matriarch, or
a shared vehicle.
"""

from collections import deque

from app.schemas.intelligence import CentralityResponse, CentralityScore
from app.services.intelligence.graph_view import CaseGraphView


METHOD = {
    "degree": "count of distinct directly connected entities",
    "weighted_degree": "sum of source records supporting each incident relationship",
    "betweenness": "exact Brandes shortest-path betweenness, undirected, unweighted",
    "closeness": "Wasserman-Faust closeness over reachable entities, undirected",
}


def degree_centrality(view: CaseGraphView) -> dict[str, float]:
    return {node: float(view.degree(node)) for node in view.node_ids}


def weighted_degree_centrality(view: CaseGraphView) -> dict[str, float]:
    return {node: view.weighted_degree(node) for node in view.node_ids}


def betweenness_centrality(view: CaseGraphView) -> dict[str, float]:
    """Exact betweenness via Brandes.

    Accumulates dependencies over shortest-path DAGs from every source, then
    halves the total because an undirected graph traverses each pair twice.
    """
    nodes = view.node_ids
    betweenness: dict[str, float] = {node: 0.0 for node in nodes}
    if len(nodes) < 3:
        return betweenness

    for source in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in nodes}
        sigma: dict[str, float] = {node: 0.0 for node in nodes}
        distance: dict[str, int] = {node: -1 for node in nodes}
        sigma[source] = 1.0
        distance[source] = 0
        queue: deque[str] = deque([source])

        while queue:
            current = queue.popleft()
            stack.append(current)
            for neighbour in view.neighbours(current):
                if distance[neighbour] < 0:
                    distance[neighbour] = distance[current] + 1
                    queue.append(neighbour)
                if distance[neighbour] == distance[current] + 1:
                    sigma[neighbour] += sigma[current]
                    predecessors[neighbour].append(current)

        delta: dict[str, float] = {node: 0.0 for node in nodes}
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                if sigma[node]:
                    delta[predecessor] += (sigma[predecessor] / sigma[node]) * (1.0 + delta[node])
            if node != source:
                betweenness[node] += delta[node]

    return {node: value / 2.0 for node, value in betweenness.items()}


def normalized_betweenness(view: CaseGraphView) -> dict[str, float]:
    """Betweenness scaled to 0..1 by the number of pairs it could sit between."""
    raw = betweenness_centrality(view)
    count = len(view.node_ids)
    if count < 3:
        return {node: 0.0 for node in raw}
    denominator = (count - 1) * (count - 2) / 2.0
    return {node: value / denominator for node, value in raw.items()}


def closeness_centrality(view: CaseGraphView) -> dict[str, float]:
    """Closeness, scaled by reachable fraction so disconnected parts stay comparable."""
    nodes = view.node_ids
    count = len(nodes)
    scores: dict[str, float] = {}

    for source in nodes:
        distance = {source: 0}
        queue: deque[str] = deque([source])
        total = 0
        while queue:
            current = queue.popleft()
            for neighbour in view.neighbours(current):
                if neighbour not in distance:
                    distance[neighbour] = distance[current] + 1
                    total += distance[neighbour]
                    queue.append(neighbour)
        reachable = len(distance) - 1
        if reachable <= 0 or total == 0:
            scores[source] = 0.0
            continue
        # Wasserman-Faust: average closeness within the reachable set, weighted
        # by how much of the graph that set represents.
        scores[source] = (reachable / total) * (reachable / (count - 1)) if count > 1 else 0.0

    return scores


CALCULATORS = {
    "degree": degree_centrality,
    "weighted_degree": weighted_degree_centrality,
    "betweenness": betweenness_centrality,
    "closeness": closeness_centrality,
}


def _explain(
    view: CaseGraphView,
    metric: str,
    entity_id: str,
    value: float,
    communities: dict[str, str] | None,
) -> str:
    degree = view.degree(entity_id)
    edges = view.incident_edges(entity_id)
    observed = sum(1 for edge in edges if edge.assertion_type == "observed")
    interactions = int(view.weighted_degree(entity_id))

    reach = ""
    if communities:
        touched = sorted({communities[n] for n in view.neighbours(entity_id) if n in communities})
        if len(touched) > 1:
            reach = f" spanning {len(touched)} communities"

    if metric == "degree":
        return (
            f"Directly connected to {degree} other entities through "
            f"{len(edges)} recorded relationships ({observed} observed){reach}."
        )
    if metric == "weighted_degree":
        return (
            f"Involved in {interactions} recorded interactions across {degree} "
            f"direct connections{reach}."
        )
    if metric == "betweenness":
        if value <= 0:
            return (
                f"Sits on no shortest path between other entities; its {degree} "
                "connections are all reachable another way."
            )
        return (
            f"Lies on shortest paths between other entities in this case, "
            f"connecting {degree} direct relationships{reach}. Removing it would "
            "lengthen or break those routes."
        )
    return (
        f"Reaches the rest of the case graph in comparatively few hops from its "
        f"{degree} direct connections{reach}."
    )


def _ranked(values: dict[str, float]) -> list[tuple[str, float, int]]:
    """Competition ranking, ties broken deterministically by entity id."""
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ranked: list[tuple[str, float, int]] = []
    previous_value: float | None = None
    previous_rank = 0
    for index, (entity_id, value) in enumerate(ordered, start=1):
        if previous_value is not None and abs(value - previous_value) < 1e-12:
            rank = previous_rank
        else:
            rank = index
            previous_rank = rank
            previous_value = value
        ranked.append((entity_id, value, rank))
    return ranked


def centrality(
    view: CaseGraphView,
    metric: str = "degree",
    *,
    communities: dict[str, str] | None = None,
    limit: int | None = None,
) -> CentralityResponse:
    if metric not in CALCULATORS:
        raise ValueError(f"unknown centrality metric '{metric}'")

    if view.node_count == 0:
        return CentralityResponse(
            case_id=view.case_id,
            metric=metric,  # type: ignore[arg-type]
            scores=[],
            count=0,
            insufficient_data=True,
            reason="this investigation has no persisted entities yet",
            method=METHOD[metric],
        )
    if metric == "betweenness" and view.node_count < 3:
        return CentralityResponse(
            case_id=view.case_id,
            metric=metric,  # type: ignore[arg-type]
            scores=[],
            count=0,
            insufficient_data=True,
            reason=(
                f"betweenness needs at least three entities to be meaningful; "
                f"this case has {view.node_count}"
            ),
            method=METHOD[metric],
        )

    values = CALCULATORS[metric](view)
    ranked = _ranked(values)
    if limit is not None:
        ranked = ranked[:limit]

    scores = [
        CentralityScore(
            case_id=view.case_id,
            entity_id=entity_id,
            entity_type=view.entity_type(entity_id),  # type: ignore[arg-type]
            label=view.label(entity_id),
            metric=metric,  # type: ignore[arg-type]
            value=round(value, 6),
            rank=rank,
            degree=view.degree(entity_id),
            explanation=_explain(view, metric, entity_id, value, communities),
        )
        for entity_id, value, rank in ranked
    ]

    return CentralityResponse(
        case_id=view.case_id,
        metric=metric,  # type: ignore[arg-type]
        scores=scores,
        count=len(scores),
        method=METHOD[metric],
    )
