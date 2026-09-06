"""Explainable indicators of coordinated activity.

There is deliberately no "organised crime score". An aggregate number would hide
the only thing that matters here - *which* structural pattern was observed and
which records show it - behind a figure that reads as a verdict. Instead each
indicator names one pattern, lists the entities and relationships that exhibit
it, carries the evidence ids needed to read the underlying records, and states
plainly that an indicator is not proof.

Every indicator is derived from topology, timing and recorded relationship types
only. None of them keys off a name, a location, an entity type or any attribute
of a person, and none of them treats density on its own as meaningful: a
workplace where everyone knows everyone produces no indicator here, because
mutual connection within a single cluster is not coordination between clusters.
"""

from datetime import timedelta

from app.schemas.intelligence import ActivityIndicator, IndicatorResponse
from app.schemas.investigation import weakest_assertion
from app.services.identity import content_hash
from app.services.intelligence.anomaly_detection import _directed_chains
from app.services.intelligence.community_detection import (
    detect_communities,
    has_meaningful_structure,
)
from app.services.intelligence.context import context_dampening
from app.services.intelligence.graph_view import CaseGraphView
from app.services.intelligence.network_analysis import normalized_betweenness


COORDINATION_WINDOW = timedelta(days=14)


def _indicator_id(case_id: str, indicator_type: str, entity_ids: list[str]) -> str:
    return f"ind_{content_hash('|'.join([case_id, indicator_type, *sorted(entity_ids)]))[:16]}"


def _evidence(edges) -> list[str]:
    collected: list[str] = []
    for edge in edges:
        for evidence_id in edge.evidence_ids:
            if evidence_id not in collected:
                collected.append(evidence_id)
    return collected


def _build(
    view: CaseGraphView,
    indicator_type: str,
    entity_ids: list[str],
    edges: list,
    confidence: float,
    explanation: str,
) -> ActivityIndicator:
    return ActivityIndicator(
        case_id=view.case_id,
        indicator_id=_indicator_id(view.case_id, indicator_type, entity_ids),
        indicator_type=indicator_type,  # type: ignore[arg-type]
        entity_ids=sorted(entity_ids),
        labels=[view.label(entity_id) for entity_id in sorted(entity_ids)],
        relationship_ids=sorted(edge.relationship_id for edge in edges),
        evidence_ids=_evidence(edges),
        assertion_type=weakest_assertion([edge.assertion_type for edge in edges])  # type: ignore[arg-type]
        if edges
        else "inferred",
        confidence=round(min(1.0, max(0.0, confidence)), 4),
        explanation=explanation,
    )


def _repeated_co_occurrence(view: CaseGraphView) -> list[ActivityIndicator]:
    """Pairs linked in more than one distinct way."""
    pairs: dict[tuple[str, str], list] = {}
    for edge in view.edges:
        if edge.source == edge.target:
            continue
        key = (edge.source, edge.target) if edge.source < edge.target else (edge.target, edge.source)
        pairs.setdefault(key, []).append(edge)

    indicators: list[ActivityIndicator] = []
    for (left, right), edges in sorted(pairs.items()):
        types = sorted({edge.relationship_type for edge in edges})
        if len(types) < 2:
            continue
        multiplier, note = context_dampening(view, [edge.relationship_id for edge in edges])
        base = min(1.0, 0.45 + 0.15 * len(types))
        indicators.append(
            _build(
                view,
                "repeated_co_occurrence",
                [left, right],
                edges,
                base * multiplier,
                (
                    f"{view.label(left)} and {view.label(right)} are linked in "
                    f"{len(types)} different recorded ways ({', '.join(types)}) across "
                    f"{len(edges)} relationships.{note}"
                ),
            )
        )
    return indicators


def _hub_intermediary(view: CaseGraphView, assignments: dict[str, str]) -> list[ActivityIndicator]:
    betweenness = normalized_betweenness(view)
    indicators: list[ActivityIndicator] = []
    for entity_id in view.node_ids:
        score = betweenness.get(entity_id, 0.0)
        if score <= 0:
            continue
        own = assignments.get(entity_id)
        crossing = [
            edge
            for edge in view.incident_edges(entity_id)
            if assignments.get(edge.other_end(entity_id)) != own
        ]
        touched = sorted(
            {assignments[node] for node in view.neighbours(entity_id) if node in assignments}
        )
        if len(touched) < 3 or not crossing:
            continue
        multiplier, note = context_dampening(view, [edge.relationship_id for edge in crossing])
        indicators.append(
            _build(
                view,
                "hub_intermediary_structure",
                [entity_id],
                crossing,
                min(1.0, 0.4 + 0.1 * len(touched)) * multiplier,
                (
                    f"{view.label(entity_id)} sits between {len(touched)} clusters that "
                    f"have few other connections to each other, holding "
                    f"{len(crossing)} of the relationships that join them.{note}"
                ),
            )
        )
    return indicators


def _financial_chain(view: CaseGraphView) -> list[ActivityIndicator]:
    chains = [chain for chain in _directed_chains(view, "transacted_with") if len(chain) >= 3]
    if not chains:
        return []
    longest = chains[0]
    participants = [longest[0].source] + [edge.target for edge in longest]
    route = " -> ".join(view.label(node) for node in participants)
    multiplier, note = context_dampening(view, [edge.relationship_id for edge in longest])
    return [
        _build(
            view,
            "financial_chain_structure",
            participants,
            longest,
            min(1.0, 0.4 + 0.12 * len(longest)) * multiplier,
            (
                f"Value moves along a recorded {len(longest)}-step sequence: {route}. "
                f"A chain describes the shape of the transaction records; it says "
                f"nothing about the purpose of any payment.{note}"
            ),
        )
    ]


def _communication_overlap(view: CaseGraphView, assignments: dict[str, str]) -> list[ActivityIndicator]:
    contacts: dict[str, set[str]] = {}
    for edge in view.edges_of_type("contacted"):
        contacts.setdefault(edge.source, set()).add(edge.target)
        contacts.setdefault(edge.target, set()).add(edge.source)

    indicators: list[ActivityIndicator] = []
    people = sorted(contacts)
    for index, first in enumerate(people):
        for second in people[index + 1 :]:
            shared = contacts[first] & contacts[second]
            shared.discard(first)
            shared.discard(second)
            if len(shared) < 2:
                continue
            if assignments.get(first) == assignments.get(second):
                # Shared contacts inside one cluster is what a cluster *is*.
                continue
            edges = [
                edge
                for edge in view.edges_of_type("contacted")
                if {edge.source, edge.target} & {first, second}
                and (edge.source in shared or edge.target in shared)
            ]
            if not edges:
                continue
            multiplier, note = context_dampening(view, [edge.relationship_id for edge in edges])
            indicators.append(
                _build(
                    view,
                    "communication_overlap",
                    [first, second, *sorted(shared)],
                    edges,
                    min(1.0, 0.35 + 0.15 * len(shared)) * multiplier,
                    (
                        f"{view.label(first)} and {view.label(second)} sit in different "
                        f"clusters yet share {len(shared)} common communication "
                        f"counterparties.{note}"
                    ),
                )
            )
    return indicators


def _geographic_coordination(view: CaseGraphView, assignments: dict[str, str]) -> list[ActivityIndicator]:
    indicators: list[ActivityIndicator] = []
    for location_id in [node for node in view.node_ids if view.entity_type(node) == "location"]:
        edges = [
            edge
            for edge in view.incident_edges(location_id)
            if view.entity_type(edge.other_end(location_id)) == "person"
        ]
        people = sorted({edge.other_end(location_id) for edge in edges})
        if len(people) < 3:
            continue
        touched = sorted({assignments[p] for p in people if p in assignments})
        if len(touched) < 2:
            continue

        timestamps = sorted(edge.timestamp for edge in edges if edge.timestamp is not None)
        clustered = bool(timestamps) and (timestamps[-1] - timestamps[0]) <= COORDINATION_WINDOW
        timing = (
            f" All recorded presences fall within {(timestamps[-1] - timestamps[0]).days} days."
            if clustered
            else " Recorded presences are not concentrated in time."
        )
        multiplier, note = context_dampening(view, [edge.relationship_id for edge in edges])
        base = 0.35 + 0.1 * len(touched) + (0.15 if clustered else 0.0)
        indicators.append(
            _build(
                view,
                "geographic_coordination",
                [location_id, *people],
                edges,
                min(1.0, base) * multiplier,
                (
                    f"{len(people)} people from {len(touched)} separate clusters are "
                    f"recorded at {view.label(location_id)}.{timing} Shared public, "
                    f"retail and workplace locations produce this pattern routinely."
                    f"{note}"
                ),
            )
        )
    return indicators


def activity_indicators(
    view: CaseGraphView, *, assignments: dict[str, str] | None = None
) -> IndicatorResponse:
    assignments = assignments if assignments is not None else detect_communities(view)

    meaningful, _modularity, _reason = has_meaningful_structure(view, assignments)

    indicators: list[ActivityIndicator] = []
    indicators.extend(_repeated_co_occurrence(view))
    indicators.extend(_financial_chain(view))
    # Every indicator below describes coordination *between* clusters, so none of
    # them can be asserted when the clusters are not genuinely separate.
    if meaningful:
        indicators.extend(_hub_intermediary(view, assignments))
        indicators.extend(_communication_overlap(view, assignments))
        indicators.extend(_geographic_coordination(view, assignments))

    indicators.sort(key=lambda item: (-item.confidence, item.indicator_type, item.indicator_id))
    return IndicatorResponse(
        case_id=view.case_id, indicators=indicators, count=len(indicators)
    )
