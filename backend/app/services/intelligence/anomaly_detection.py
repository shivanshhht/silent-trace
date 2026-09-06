"""One anomaly framework, several detectors.

Every detector produces the same :class:`AnomalySignal` shape - case, entity,
type, strength, confidence, explanation, evidence - so signals can be compared,
aggregated and displayed uniformly, and so adding a detector never means adding
a parallel scoring system. There is no machine-learning model here and no
training data; each detector is an explicit, readable rule over the persisted
graph, which is what makes every signal explainable to an investigator.

**Everything is relative to the case, and where possible to the entity itself.**
Thresholds are derived from the distribution within the same investigation
rather than from constants, because "high" only means anything against a
baseline. This is also what stops a uniformly dense network from lighting up:
when every entity is highly connected, no entity is an outlier.

**Strength is not probability.** ``signal_strength`` says how pronounced a
pattern is against that baseline. ``confidence`` says how well evidenced the
observation is. Neither is a likelihood that anything unlawful occurred, and a
detector firing on an entity is not a finding about that entity.

**Detectors that cannot run say so.** A case with no transactions gets an
explicit "skipped, no financial records" entry rather than a silent absence,
because an investigator must be able to tell "looked and found nothing" from
"never looked".
"""

from statistics import pstdev

from app.schemas.intelligence import AnomalyResponse, AnomalySignal
from app.services.identity import content_hash
from app.services.intelligence.community_detection import (
    detect_communities,
    has_meaningful_structure,
)
from app.services.intelligence.graph_view import CaseGraphView
from app.services.intelligence.network_analysis import normalized_betweenness
from app.services.intelligence.temporal_analysis import (
    burst_strength,
    gap_strength,
    temporal_profiles,
)


MINIMUM_STRENGTH = 0.2


def _signal_id(case_id: str, anomaly_type: str, entity_id: str) -> str:
    return f"sig_{content_hash('|'.join([case_id, anomaly_type, entity_id]))[:16]}"


def _confidence(view: CaseGraphView, edges) -> tuple[float, str, list[str]]:
    """Confidence and assertion for an observation resting on these relationships."""
    if not edges:
        return 0.5, "inferred", []
    evidence: list[str] = []
    for edge in edges:
        for evidence_id in edge.evidence_ids:
            if evidence_id not in evidence:
                evidence.append(evidence_id)
    mean_confidence = sum(edge.confidence for edge in edges) / len(edges)
    observed = all(edge.assertion_type == "observed" for edge in edges)
    assertion = "observed" if observed else "inferred"
    factor = 1.0 if observed else 0.85
    evidence_factor = 1.0 if all(edge.evidence_ids for edge in edges) else 0.8
    return round(min(1.0, mean_confidence * factor * evidence_factor), 4), assertion, evidence


def _threshold(values: list[float], deviations: float) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return mean + deviations * pstdev(values)


# ---------------------------------------------------------------------------
# Temporal detectors
# ---------------------------------------------------------------------------


def _temporal_signals(view: CaseGraphView, profiles: dict) -> tuple[list[AnomalySignal], dict[str, str]]:
    signals: list[AnomalySignal] = []
    usable = [profile for profile in profiles.values() if not profile.insufficient_data]
    if not usable:
        return signals, {
            "temporal_burst": "no entity has enough timestamped relationships to profile",
            "temporal_gap": "no entity has enough timestamped relationships to profile",
        }

    skipped: dict[str, str] = {}
    for entity_id in view.node_ids:
        profile = profiles[entity_id]
        if profile.insufficient_data:
            continue

        strength = burst_strength(profile)
        if strength >= MINIMUM_STRENGTH:
            edges = [
                edge
                for edge in view.incident_edges(entity_id)
                if edge.timestamp is not None
            ]
            confidence, assertion, evidence = _confidence(view, edges)
            signals.append(
                AnomalySignal(
                    case_id=view.case_id,
                    signal_id=_signal_id(view.case_id, "temporal_burst", entity_id),
                    entity_id=entity_id,
                    label=view.label(entity_id),
                    anomaly_type="temporal_burst",
                    category="temporal",
                    signal_strength=strength,
                    confidence=confidence,
                    assertion_type=assertion,  # type: ignore[arg-type]
                    relationship_ids=sorted(edge.relationship_id for edge in edges),
                    evidence_ids=evidence,
                    observed_from=profile.first_event_at,
                    observed_to=profile.last_event_at,
                    explanation=(
                        f"{profile.peak_event_count} recorded interactions fall on "
                        f"{profile.peak_period_start.date()}, against this entity's own "
                        f"average of {profile.mean_events_per_active_period} per active "
                        f"day across {profile.active_period_count} active days."
                    ),
                )
            )

        gap, longest = gap_strength(profile)
        if gap >= MINIMUM_STRENGTH and longest is not None:
            edges = [e for e in view.incident_edges(entity_id) if e.timestamp is not None]
            confidence, assertion, evidence = _confidence(view, edges)
            signals.append(
                AnomalySignal(
                    case_id=view.case_id,
                    signal_id=_signal_id(view.case_id, "temporal_gap", entity_id),
                    entity_id=entity_id,
                    label=view.label(entity_id),
                    anomaly_type="temporal_gap",
                    category="temporal",
                    signal_strength=gap,
                    confidence=confidence,
                    assertion_type=assertion,  # type: ignore[arg-type]
                    relationship_ids=sorted(edge.relationship_id for edge in edges),
                    evidence_ids=evidence,
                    observed_from=profile.first_event_at,
                    observed_to=profile.last_event_at,
                    explanation=(
                        f"Recorded activity pauses for {longest.days} days, well beyond "
                        f"the typical spacing between this entity's own recorded events."
                    ),
                )
            )
    return signals, skipped


# ---------------------------------------------------------------------------
# Network detectors
# ---------------------------------------------------------------------------


def _network_signals(
    view: CaseGraphView, assignments: dict[str, str], betweenness: dict[str, float]
) -> tuple[list[AnomalySignal], dict[str, str]]:
    signals: list[AnomalySignal] = []
    skipped: dict[str, str] = {}

    if view.node_count < 3:
        return signals, {
            "network_bridge_load": "fewer than three entities in this case",
            "network_degree_outlier": "fewer than three entities in this case",
        }

    meaningful, _modularity, structure_reason = has_meaningful_structure(view, assignments)

    active = [value for value in betweenness.values() if value > 0] if meaningful else []
    if not meaningful:
        skipped["network_bridge_load"] = structure_reason
    elif not active:
        skipped["network_bridge_load"] = (
            "no entity lies on a non-redundant route between others; every "
            "connection has an equally short alternative"
        )
    else:
        cutoff = max(_threshold(active, 1.0), 1e-9)
        for entity_id in view.node_ids:
            value = betweenness.get(entity_id, 0.0)
            if value <= 0 or value < cutoff:
                continue
            own = assignments.get(entity_id)
            crossing = [
                edge
                for edge in view.incident_edges(entity_id)
                if assignments.get(edge.other_end(entity_id)) != own
            ]
            confidence, assertion, evidence = _confidence(view, crossing or view.incident_edges(entity_id))
            signals.append(
                AnomalySignal(
                    case_id=view.case_id,
                    signal_id=_signal_id(view.case_id, "network_bridge_load", entity_id),
                    entity_id=entity_id,
                    label=view.label(entity_id),
                    anomaly_type="network_bridge_load",
                    category="network",
                    signal_strength=round(min(1.0, value), 4),
                    confidence=confidence,
                    assertion_type=assertion,  # type: ignore[arg-type]
                    relationship_ids=sorted(
                        edge.relationship_id for edge in (crossing or view.incident_edges(entity_id))
                    ),
                    evidence_ids=evidence,
                    explanation=(
                        f"A disproportionate share of the shortest routes between other "
                        f"entities in this case passes through {view.label(entity_id)}, "
                        f"which holds {len(crossing)} relationships reaching outside its "
                        f"own cluster."
                    ),
                )
            )

    degrees = [float(view.degree(node)) for node in view.node_ids]
    degree_cutoff = _threshold(degrees, 2.0)
    if pstdev(degrees) == 0:
        skipped["network_degree_outlier"] = (
            "every entity has the same number of connections, so no entity is an outlier"
        )
    else:
        for entity_id in view.node_ids:
            degree = view.degree(entity_id)
            if degree < 3 or degree <= degree_cutoff:
                continue
            edges = view.incident_edges(entity_id)
            confidence, assertion, evidence = _confidence(view, edges)
            highest = max(degrees)
            signals.append(
                AnomalySignal(
                    case_id=view.case_id,
                    signal_id=_signal_id(view.case_id, "network_degree_outlier", entity_id),
                    entity_id=entity_id,
                    label=view.label(entity_id),
                    anomaly_type="network_degree_outlier",
                    category="network",
                    signal_strength=round(min(1.0, degree / highest), 4) if highest else 0.0,
                    confidence=confidence,
                    assertion_type=assertion,  # type: ignore[arg-type]
                    relationship_ids=sorted(edge.relationship_id for edge in edges),
                    evidence_ids=evidence,
                    explanation=(
                        f"{view.label(entity_id)} is directly connected to {degree} "
                        f"entities, more than two standard deviations above the average "
                        f"of {round(sum(degrees) / len(degrees), 2)} for this case."
                    ),
                )
            )

    return signals, skipped


# ---------------------------------------------------------------------------
# Financial, communication and geographic detectors
# ---------------------------------------------------------------------------


def _directed_chains(view: CaseGraphView, relationship_type: str, max_depth: int = 5):
    """Simple directed paths in one relationship subgraph, longest first."""
    outgoing: dict[str, list] = {}
    for edge in view.edges_of_type(relationship_type):
        outgoing.setdefault(edge.source, []).append(edge)

    chains: list[list] = []
    for start in sorted(outgoing):
        stack = [(start, [], {start})]
        while stack:
            node, path, seen = stack.pop()
            for edge in sorted(outgoing.get(node, []), key=lambda e: e.relationship_id):
                if edge.target in seen:
                    continue
                extended = path + [edge]
                if len(extended) >= 2:
                    chains.append(extended)
                if len(extended) < max_depth:
                    stack.append((edge.target, extended, seen | {edge.target}))
    chains.sort(key=lambda chain: (-len(chain), [e.relationship_id for e in chain]))
    return chains


def _financial_signals(view: CaseGraphView) -> tuple[list[AnomalySignal], dict[str, str]]:
    transactions = view.edges_of_type("transacted_with")
    if not transactions:
        return [], {
            "financial_chain_participation": "this case has no recorded financial transactions"
        }

    chains = _directed_chains(view, "transacted_with")
    if not chains:
        return [], {
            "financial_chain_participation": (
                "transactions exist but none form a chain that passes through an "
                "intermediary"
            )
        }

    longest_for: dict[str, list] = {}
    for chain in chains:
        # Intermediaries only: an entity that both receives and forwards value.
        for earlier, later in zip(chain, chain[1:]):
            middle = earlier.target
            if middle != later.source:
                continue
            if middle not in longest_for or len(chain) > len(longest_for[middle]):
                longest_for[middle] = chain

    signals: list[AnomalySignal] = []
    for entity_id in sorted(longest_for):
        chain = longest_for[entity_id]
        confidence, assertion, evidence = _confidence(view, chain)
        hops = len(chain)
        route = " -> ".join(
            [view.label(chain[0].source)] + [view.label(edge.target) for edge in chain]
        )
        signals.append(
            AnomalySignal(
                case_id=view.case_id,
                signal_id=_signal_id(view.case_id, "financial_chain_participation", entity_id),
                entity_id=entity_id,
                label=view.label(entity_id),
                anomaly_type="financial_chain_participation",
                category="financial",
                signal_strength=round(min(1.0, 0.4 + (hops - 2) * 0.2), 4),
                confidence=confidence,
                assertion_type=assertion,  # type: ignore[arg-type]
                relationship_ids=sorted(edge.relationship_id for edge in chain),
                evidence_ids=evidence,
                explanation=(
                    f"{view.label(entity_id)} both receives and passes on value along a "
                    f"{hops}-step recorded transaction sequence ({route}). Pass-through "
                    "position is a structural observation about the records, not a "
                    "conclusion about the payments."
                ),
            )
        )
    return signals, {}


def _communication_signals(
    view: CaseGraphView, assignments: dict[str, str]
) -> tuple[list[AnomalySignal], dict[str, str]]:
    contacts = view.edges_of_type("contacted")
    if not contacts:
        return [], {"communication_overlap": "this case has no recorded communications"}

    meaningful, _modularity, structure_reason = has_meaningful_structure(view, assignments)
    if not meaningful:
        # "Talks to people in several clusters" is meaningless when the clusters
        # are an artefact of splitting one cohesive group.
        return [], {"communication_overlap": structure_reason}

    signals: list[AnomalySignal] = []
    for entity_id in view.node_ids:
        incident = [edge for edge in view.incident_edges(entity_id) if edge.relationship_type == "contacted"]
        if len(incident) < 2:
            continue
        counterparties = {edge.other_end(entity_id) for edge in incident}
        touched = {assignments.get(node) for node in counterparties if node in assignments}
        touched.discard(None)
        if len(touched) < 2:
            continue
        confidence, assertion, evidence = _confidence(view, incident)
        signals.append(
            AnomalySignal(
                case_id=view.case_id,
                signal_id=_signal_id(view.case_id, "communication_overlap", entity_id),
                entity_id=entity_id,
                label=view.label(entity_id),
                anomaly_type="communication_overlap",
                category="communication",
                signal_strength=round(min(1.0, 0.3 + 0.2 * len(touched)), 4),
                confidence=confidence,
                assertion_type=assertion,  # type: ignore[arg-type]
                relationship_ids=sorted(edge.relationship_id for edge in incident),
                evidence_ids=evidence,
                explanation=(
                    f"{view.label(entity_id)} has recorded communications with "
                    f"{len(counterparties)} counterparties spread across "
                    f"{len(touched)} separate clusters."
                ),
            )
        )
    return signals, {}


def _geographic_signals(
    view: CaseGraphView, assignments: dict[str, str]
) -> tuple[list[AnomalySignal], dict[str, str]]:
    locations = [node for node in view.node_ids if view.entity_type(node) == "location"]
    if not locations:
        return [], {"geographic_convergence": "this case has no recorded locations"}

    meaningful, _modularity, structure_reason = has_meaningful_structure(view, assignments)
    if not meaningful:
        return [], {"geographic_convergence": structure_reason}

    signals: list[AnomalySignal] = []
    for location_id in locations:
        edges = view.incident_edges(location_id)
        people = sorted(
            {
                edge.other_end(location_id)
                for edge in edges
                if view.entity_type(edge.other_end(location_id)) == "person"
            }
        )
        if len(people) < 3:
            continue
        touched = {assignments.get(person) for person in people if person in assignments}
        touched.discard(None)
        if len(touched) < 2:
            continue
        relevant = [edge for edge in edges if edge.other_end(location_id) in people]
        confidence, assertion, evidence = _confidence(view, relevant)
        signals.append(
            AnomalySignal(
                case_id=view.case_id,
                signal_id=_signal_id(view.case_id, "geographic_convergence", location_id),
                entity_id=location_id,
                label=view.label(location_id),
                anomaly_type="geographic_convergence",
                category="geographic",
                signal_strength=round(min(1.0, 0.3 + 0.15 * len(touched) + 0.05 * len(people)), 4),
                confidence=confidence,
                assertion_type=assertion,  # type: ignore[arg-type]
                relationship_ids=sorted(edge.relationship_id for edge in relevant),
                evidence_ids=evidence,
                explanation=(
                    f"{len(people)} people from {len(touched)} otherwise separate "
                    f"clusters are recorded at {view.label(location_id)}. Shared public "
                    "or workplace locations produce this pattern routinely."
                ),
            )
        )
    return signals, {}


def _cross_case_signals(
    view: CaseGraphView, session, include_cross_case: bool
) -> tuple[list[AnomalySignal], dict[str, str]]:
    """Recurrence of the same described entity in other investigations.

    Disabled by default. Case isolation is the stronger guarantee, and answering
    this question at all requires reading outside the requested case, so it must
    be an explicit, auditable choice rather than a default. Even when enabled,
    only a *count* is returned: no identifier, name, relationship or evidence
    from another investigation crosses into this response.
    """
    if not include_cross_case:
        return [], {
            "cross_case_recurrence": (
                "disabled by default: correlating entities across investigations "
                "requires reading outside this case and must be requested explicitly"
            )
        }
    if session is None:
        return [], {"cross_case_recurrence": "no database session available"}

    from sqlalchemy import func, select

    from app.db.models import EntityRow

    signals: list[AnomalySignal] = []
    for entity_id in view.node_ids:
        entity = view.entities[entity_id]
        canonical_value = None
        for row in session.execute(
            select(EntityRow.canonical_value).where(
                EntityRow.case_id == view.case_id, EntityRow.canonical_id == entity_id
            )
        ).scalars():
            canonical_value = row
        if not canonical_value:
            continue

        other_cases = session.execute(
            select(func.count(func.distinct(EntityRow.case_id))).where(
                EntityRow.canonical_value == canonical_value,
                EntityRow.entity_type == entity.entity_type,
                EntityRow.case_id != view.case_id,
            )
        ).scalar_one()
        if not other_cases:
            continue

        signals.append(
            AnomalySignal(
                case_id=view.case_id,
                signal_id=_signal_id(view.case_id, "cross_case_recurrence", entity_id),
                entity_id=entity_id,
                label=view.label(entity_id),
                anomaly_type="cross_case_recurrence",
                category="recurrence",
                signal_strength=round(min(1.0, 0.3 + 0.2 * other_cases), 4),
                confidence=0.6,
                assertion_type="inferred",
                relationship_ids=[],
                evidence_ids=list(entity.evidence_ids),
                explanation=(
                    f"An entity described identically to {view.label(entity_id)} also "
                    f"appears in {other_cases} other investigation(s). Names and "
                    "descriptions recur legitimately; this is a prompt to check, not a "
                    "link between investigations."
                ),
            )
        )
    return signals, {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def detect_anomalies(
    view: CaseGraphView,
    *,
    assignments: dict[str, str] | None = None,
    profiles: dict | None = None,
    betweenness: dict[str, float] | None = None,
    session=None,
    include_cross_case: bool = False,
) -> AnomalyResponse:
    assignments = assignments if assignments is not None else detect_communities(view)
    profiles = profiles if profiles is not None else temporal_profiles(view)
    betweenness = betweenness if betweenness is not None else normalized_betweenness(view)

    signals: list[AnomalySignal] = []
    skipped: dict[str, str] = {}

    for produced, reasons in (
        _temporal_signals(view, profiles),
        _network_signals(view, assignments, betweenness),
        _financial_signals(view),
        _communication_signals(view, assignments),
        _geographic_signals(view, assignments),
        _cross_case_signals(view, session, include_cross_case),
    ):
        signals.extend(produced)
        skipped.update(reasons)

    signals.sort(key=lambda item: (-item.signal_strength, item.anomaly_type, item.entity_id))

    all_detectors = {
        "temporal_burst",
        "temporal_gap",
        "network_bridge_load",
        "network_degree_outlier",
        "financial_chain_participation",
        "communication_overlap",
        "geographic_convergence",
        "cross_case_recurrence",
    }
    return AnomalyResponse(
        case_id=view.case_id,
        signals=signals,
        count=len(signals),
        detectors_run=sorted(all_detectors - set(skipped)),
        detectors_skipped=skipped,
    )
