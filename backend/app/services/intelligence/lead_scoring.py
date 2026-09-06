"""Aggregation of signals into investigative leads.

**Aggregate, never absorb.** A lead is a container for the signals that produced
it. Every contributing signal keeps its own type, strength, confidence,
relationships, evidence and explanation, so an investigator can always see which
part of a lead is strong, which is weak, and which rests on inferred rather than
observed claims. A lead with its signals stripped out would be exactly the
unexplained score this system is not allowed to produce.

**How strengths combine.** Signals in the same category are correlated - four
temporal detectors firing on one entity are largely one observation - so only
the strongest signal per category counts, and the categories are then combined
with a noisy-OR. Several independent weak signals therefore do add up to
something worth looking at, while a pile of signals of a single kind does not
inflate on its own.

**How ordinary life is kept out.** Before combining, each signal is weighted by
the context of the relationships supporting it. A pattern occurring entirely
within a family, a workplace or a community organisation is reduced, and the
reason is written into the lead. This is what prevents a large legitimate
network - a hospital, a university, a company - from accumulating a high
priority merely by being densely and legitimately connected.

**What network_priority means.** It is a triage ordering for analyst attention:
how structurally notable this cluster of signals is within this one case. It is
not a probability, not a risk rating for a person, and not a statement that
anything unlawful happened.
"""

from datetime import datetime, timezone

from app.schemas.intelligence import (
    ActivityIndicator,
    AnomalySignal,
    BridgeEntity,
    ContributingSignal,
    InvestigativeLead,
    LeadResponse,
)
from app.schemas.investigation import weakest_assertion
from app.services.identity import content_hash
from app.services.intelligence.context import context_dampening
from app.services.intelligence.graph_view import CaseGraphView


INDICATOR_CATEGORY = {
    "repeated_co_occurrence": "structural",
    "hub_intermediary_structure": "network",
    "financial_chain_structure": "financial",
    "communication_overlap": "communication",
    "geographic_coordination": "geographic",
    "cross_case_recurrence": "recurrence",
}

# A lead below this aggregate is not worth an analyst's attention and is not
# emitted at all. Reporting every faint pattern as a lead would make the output
# useless and would imply significance the data does not carry.
LEAD_FLOOR = 0.25
HIGH_AGGREGATE = 0.6
MEDIUM_AGGREGATE = 0.4

# The strongest single contributing signal a lead must contain to reach each
# priority, after context dampening.
HIGH_SINGLE_SIGNAL = 0.5
MEDIUM_SINGLE_SIGNAL = 0.3


def _noisy_or(strengths: list[float]) -> float:
    combined = 1.0
    for strength in strengths:
        combined *= 1.0 - max(0.0, min(1.0, strength))
    return 1.0 - combined


def _lead_id(case_id: str, entity_id: str) -> str:
    return f"lead_{content_hash('|'.join([case_id, entity_id]))[:16]}"


def _from_anomaly(view: CaseGraphView, signal: AnomalySignal) -> ContributingSignal:
    multiplier, note = context_dampening(view, signal.relationship_ids)
    return ContributingSignal(
        source_kind="anomaly",
        signal_type=signal.anomaly_type,
        category=signal.category,
        signal_strength=round(signal.signal_strength * multiplier, 4),
        confidence=signal.confidence,
        entity_ids=[signal.entity_id],
        relationship_ids=signal.relationship_ids,
        evidence_ids=signal.evidence_ids,
        explanation=signal.explanation + note,
    )


def _from_indicator(view: CaseGraphView, indicator: ActivityIndicator) -> ContributingSignal:
    return ContributingSignal(
        source_kind="indicator",
        signal_type=indicator.indicator_type,
        category=INDICATOR_CATEGORY.get(indicator.indicator_type, "structural"),  # type: ignore[arg-type]
        signal_strength=indicator.confidence,
        confidence=indicator.confidence,
        entity_ids=indicator.entity_ids,
        relationship_ids=indicator.relationship_ids,
        evidence_ids=indicator.evidence_ids,
        explanation=indicator.explanation,
    )


def _from_bridge(view: CaseGraphView, bridge: BridgeEntity) -> ContributingSignal:
    multiplier, note = context_dampening(view, bridge.cross_community_relationship_ids)
    return ContributingSignal(
        source_kind="network",
        signal_type="potential_bridge_position",
        category="network",
        signal_strength=round(min(1.0, bridge.normalized_betweenness) * multiplier, 4),
        confidence=bridge.confidence,
        entity_ids=[bridge.entity_id],
        relationship_ids=bridge.cross_community_relationship_ids,
        evidence_ids=bridge.evidence_ids,
        explanation=bridge.explanation + note,
    )


def _priority(aggregate: float, categories: int, strongest: float) -> str:
    """Priority needs breadth *and* substance.

    Combining independent signals is the point of aggregation, but a noisy-OR
    over enough faint signals will approach 1.0 on its own, which would let a
    busy ordinary life accumulate into a top-priority lead purely by having many
    small things recorded about it. Requiring at least one individually
    substantial signal is what stops breadth alone from escalating.
    """
    if categories >= 3 and aggregate >= HIGH_AGGREGATE and strongest >= HIGH_SINGLE_SIGNAL:
        return "high"
    if categories >= 2 and aggregate >= MEDIUM_AGGREGATE and strongest >= MEDIUM_SINGLE_SIGNAL:
        return "medium"
    return "low"


def _lead_type(signals: list[ContributingSignal]) -> str:
    types = {signal.signal_type for signal in signals}
    categories = {signal.category for signal in signals}
    if "potential_bridge_position" in types or "hub_intermediary_structure" in types:
        return "potential_bridge_entity"
    if len(categories - {"temporal"}) >= 2:
        return "coordinated_activity_pattern"
    if categories == {"temporal"}:
        return "temporal_pattern_of_interest"
    return "network_priority_entity"


def investigative_leads(
    view: CaseGraphView,
    signals: list[AnomalySignal],
    indicators: list[ActivityIndicator],
    bridges: list[BridgeEntity],
    *,
    generated_at: datetime | None = None,
) -> LeadResponse:
    generated_at = generated_at or datetime.now(timezone.utc)

    contributions: dict[str, list[ContributingSignal]] = {}

    for signal in signals:
        contributions.setdefault(signal.entity_id, []).append(_from_anomaly(view, signal))
    for bridge in bridges:
        contributions.setdefault(bridge.entity_id, []).append(_from_bridge(view, bridge))
    for indicator in indicators:
        contribution = _from_indicator(view, indicator)
        for entity_id in indicator.entity_ids:
            if entity_id in view.entities:
                contributions.setdefault(entity_id, []).append(contribution)

    leads: list[InvestigativeLead] = []
    for entity_id in sorted(contributions):
        entity_signals = sorted(
            contributions[entity_id],
            key=lambda item: (-item.signal_strength, item.signal_type),
        )

        strongest_per_category: dict[str, float] = {}
        for signal in entity_signals:
            current = strongest_per_category.get(signal.category, 0.0)
            strongest_per_category[signal.category] = max(current, signal.signal_strength)

        aggregate = _noisy_or(list(strongest_per_category.values()))
        if aggregate < LEAD_FLOOR:
            continue

        categories = len(strongest_per_category)
        strongest = max(strongest_per_category.values()) if strongest_per_category else 0.0
        priority = _priority(aggregate, categories, strongest)
        lead_type = _lead_type(entity_signals)

        weight_total = sum(signal.signal_strength for signal in entity_signals)
        if weight_total > 0:
            confidence = sum(
                signal.confidence * signal.signal_strength for signal in entity_signals
            ) / weight_total
        else:
            confidence = min(signal.confidence for signal in entity_signals)

        evidence_ids: list[str] = []
        for signal in entity_signals:
            for evidence_id in signal.evidence_ids:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)

        assertion = weakest_assertion(
            [
                "observed" if signal.source_kind == "indicator" else "inferred"
                for signal in entity_signals
            ]
            or ["inferred"]
        )

        subject_ids = [entity_id]
        headline = ", ".join(
            f"{signal.signal_type} ({signal.signal_strength})" for signal in entity_signals[:4]
        )
        explanation = (
            f"{view.label(entity_id)} is raised as an analytical lead because "
            f"{len(entity_signals)} signal(s) across {categories} independent "
            f"categor{'y' if categories == 1 else 'ies'} converge on it: {headline}. "
            f"Network priority is {priority.upper()}, describing how structurally "
            f"notable this position is within case {view.case_id} and how well "
            f"evidenced it is. It is not a statement that this entity has done "
            f"anything wrong, and each contributing signal above can be opened "
            f"and read against its own evidence."
        )

        leads.append(
            InvestigativeLead(
                case_id=view.case_id,
                lead_id=_lead_id(view.case_id, entity_id),
                subject_entity_ids=subject_ids,
                subject_labels=[view.label(entity_id)],
                lead_type=lead_type,  # type: ignore[arg-type]
                network_priority=priority,  # type: ignore[arg-type]
                confidence=round(min(1.0, confidence), 4),
                contributing_signals=entity_signals,
                signal_count=len(entity_signals),
                independent_category_count=categories,
                evidence_ids=evidence_ids,
                assertion_type=assertion,  # type: ignore[arg-type]
                explanation=explanation,
                generated_at=generated_at,
            )
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    leads.sort(
        key=lambda lead: (
            priority_order[lead.network_priority],
            -lead.independent_category_count,
            -lead.confidence,
            lead.lead_id,
        )
    )

    return LeadResponse(
        case_id=view.case_id,
        leads=leads,
        count=len(leads),
        generated_at=generated_at,
    )
