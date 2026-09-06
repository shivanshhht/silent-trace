"""Contracts for the Stage C intelligence layer.

**What every number in this module means, and what it does not.**

``value``, ``signal_strength``, ``confidence`` and ``network_priority`` describe
*analytical relevance*: how structurally notable something is in this graph, and
how well evidenced that observation is. None of them is a probability of
criminality, a guilt score, or a risk rating for a person. A high centrality
value says an entity sits on many paths; it says nothing whatsoever about
whether that entity has done anything wrong, and a dense neighbourhood is a
property of a graph, not an accusation.

Two orthogonal Stage A semantics carry through unchanged. ``assertion_type``
still records whether the underlying claim was observed in a source or inferred
by the machine, and every analytical finding that rests on evidence carries the
``evidence_ids`` needed to go back and read that evidence. An analytical finding
derived from inferred relationships is itself reported as ``inferred``.

Where the data cannot support a finding, the response says so explicitly
(``insufficient_data`` with a reason) rather than emitting a confident-looking
zero.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.investigation import (
    CASE_ID_PATTERN,
    AssertionType,
    EntityType,
    RelationshipContext,
    RelationshipType,
    StrictModel,
)


CentralityMetric = Literal["degree", "weighted_degree", "betweenness", "closeness"]

# Analytical relevance for triage order. Explicitly not a criminality rating.
NetworkPriority = Literal["low", "medium", "high"]

SignalCategory = Literal[
    "network",
    "temporal",
    "financial",
    "communication",
    "geographic",
    "structural",
    "recurrence",
]

AnomalyType = Literal[
    "temporal_burst",
    "temporal_gap",
    "network_bridge_load",
    "network_degree_outlier",
    "financial_chain_participation",
    "communication_overlap",
    "geographic_convergence",
    "cross_case_recurrence",
]

IndicatorType = Literal[
    "repeated_co_occurrence",
    "hub_intermediary_structure",
    "financial_chain_structure",
    "communication_overlap",
    "geographic_coordination",
    "cross_case_recurrence",
]

LeadType = Literal[
    "potential_bridge_entity",
    "network_priority_entity",
    "coordinated_activity_pattern",
    "temporal_pattern_of_interest",
]

# Attached to every indicator and lead. The wording is deliberately fixed so it
# cannot be softened or dropped by a caller rendering these objects.
NOT_PROOF = (
    "Indicator is not proof. This describes a structural or temporal pattern in "
    "synthetic investigative data and is not evidence of wrongdoing by any entity."
)


class AnalyticalBase(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)


# ---------------------------------------------------------------------------
# Centrality
# ---------------------------------------------------------------------------


class CentralityScore(AnalyticalBase):
    entity_id: str
    entity_type: EntityType
    label: str
    metric: CentralityMetric
    value: float = Field(ge=0)
    rank: int = Field(ge=1)
    degree: int = Field(ge=0)
    explanation: str


class CentralityResponse(AnalyticalBase):
    metric: CentralityMetric
    scores: list[CentralityScore] = Field(default_factory=list)
    count: int = 0
    insufficient_data: bool = False
    reason: str | None = None
    method: str
    caveat: str = (
        "Centrality measures position in a graph of synthetic records. It is not "
        "a measure of culpability."
    )


# ---------------------------------------------------------------------------
# Communities
# ---------------------------------------------------------------------------


class Community(AnalyticalBase):
    community_id: str
    member_entity_ids: list[str] = Field(default_factory=list)
    size: int = 0
    representative_entity_ids: list[str] = Field(default_factory=list)
    internal_relationship_ids: list[str] = Field(default_factory=list)
    external_relationship_ids: list[str] = Field(default_factory=list)
    dominant_contexts: list[RelationshipContext] = Field(default_factory=list)
    internal_density: float = Field(ge=0, le=1)
    explanation: str


class CommunityResponse(AnalyticalBase):
    communities: list[Community] = Field(default_factory=list)
    count: int = 0
    modularity: float
    method: str
    insufficient_data: bool = False
    reason: str | None = None
    caveat: str = (
        "A community is a cluster of connected records. Communities routinely "
        "represent families, workplaces and social groups; membership is not a "
        "finding about any member."
    )


# ---------------------------------------------------------------------------
# Bridges
# ---------------------------------------------------------------------------


class BridgeEntity(AnalyticalBase):
    entity_id: str
    entity_type: EntityType
    label: str
    connected_community_ids: list[str] = Field(default_factory=list)
    community_count: int = 0
    betweenness: float = Field(ge=0)
    normalized_betweenness: float = Field(ge=0, le=1)
    cross_community_relationship_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    assertion_type: AssertionType = "inferred"
    confidence: float = Field(ge=0, le=1)
    explanation: str


class BridgeResponse(AnalyticalBase):
    bridges: list[BridgeEntity] = Field(default_factory=list)
    count: int = 0
    insufficient_data: bool = False
    reason: str | None = None
    caveat: str = (
        "A potential bridge entity occupies a connecting position between "
        "clusters. This is a structural observation, not an allegation of "
        "intermediary conduct."
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


class PathEdge(StrictModel):
    """One hop, carrying everything needed to justify it without a score."""

    from_entity_id: str
    to_entity_id: str
    from_label: str
    to_label: str
    relationship_id: str
    relationship_type: RelationshipType
    context: RelationshipContext
    assertion_type: AssertionType
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    occurred_at: datetime | None = None


class ConnectionPath(AnalyticalBase):
    source_entity_id: str
    target_entity_id: str
    length: int = Field(ge=1)
    edges: list[PathEdge] = Field(min_length=1)
    path_confidence: float = Field(ge=0, le=1)
    assertion_type: AssertionType
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str


class PathResponse(AnalyticalBase):
    source_entity_id: str
    target_entity_id: str
    max_depth: int
    paths: list[ConnectionPath] = Field(default_factory=list)
    count: int = 0
    insufficient_data: bool = False
    reason: str | None = None


# ---------------------------------------------------------------------------
# Temporal
# ---------------------------------------------------------------------------


class TemporalBucket(StrictModel):
    period_start: datetime
    event_count: int = Field(ge=0)
    relationship_ids: list[str] = Field(default_factory=list)


class TemporalProfile(AnalyticalBase):
    entity_id: str
    label: str
    event_count: int = 0
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None
    active_period_count: int = 0
    mean_events_per_active_period: float = 0.0
    peak_period_start: datetime | None = None
    peak_event_count: int = 0
    buckets: list[TemporalBucket] = Field(default_factory=list)
    repeated_counterparty_ids: list[str] = Field(default_factory=list)
    insufficient_data: bool = False
    reason: str | None = None
    explanation: str


class TemporalResponse(AnalyticalBase):
    bucket_size: str
    profiles: list[TemporalProfile] = Field(default_factory=list)
    count: int = 0
    insufficient_data: bool = False
    reason: str | None = None


# ---------------------------------------------------------------------------
# Anomalies and indicators
# ---------------------------------------------------------------------------


class AnomalySignal(AnalyticalBase):
    """One detector, one observation, one explanation.

    ``signal_strength`` is how pronounced the pattern is relative to the rest of
    this case, normalized to 0..1. It is not a probability of anything.
    """

    signal_id: str
    entity_id: str
    label: str
    anomaly_type: AnomalyType
    category: SignalCategory
    signal_strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    assertion_type: AssertionType
    relationship_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    explanation: str


class AnomalyResponse(AnalyticalBase):
    signals: list[AnomalySignal] = Field(default_factory=list)
    count: int = 0
    detectors_run: list[str] = Field(default_factory=list)
    detectors_skipped: dict[str, str] = Field(default_factory=dict)
    caveat: str = (
        "An anomaly signal marks a pattern that differs from the rest of this "
        "case. Unusual is not unlawful."
    )


class ActivityIndicator(AnalyticalBase):
    indicator_id: str
    indicator_type: IndicatorType
    entity_ids: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    assertion_type: AssertionType
    confidence: float = Field(ge=0, le=1)
    explanation: str
    caveat: str = NOT_PROOF


class IndicatorResponse(AnalyticalBase):
    indicators: list[ActivityIndicator] = Field(default_factory=list)
    count: int = 0
    caveat: str = NOT_PROOF


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


class ContributingSignal(StrictModel):
    """A single retained reason a lead exists.

    Leads aggregate, but never absorb: the individual signal keeps its own
    strength, confidence and explanation so an investigator can see which parts
    of a lead are strong and which are weak.
    """

    source_kind: Literal["anomaly", "indicator", "network"]
    signal_type: str
    category: SignalCategory
    signal_strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    entity_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str


class InvestigativeLead(AnalyticalBase):
    lead_id: str
    subject_entity_ids: list[str] = Field(min_length=1)
    subject_labels: list[str] = Field(default_factory=list)
    lead_type: LeadType
    network_priority: NetworkPriority
    confidence: float = Field(ge=0, le=1)
    contributing_signals: list[ContributingSignal] = Field(min_length=1)
    signal_count: int = 0
    independent_category_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    assertion_type: AssertionType
    explanation: str
    generated_at: datetime
    caveat: str = NOT_PROOF


class LeadResponse(AnalyticalBase):
    leads: list[InvestigativeLead] = Field(default_factory=list)
    count: int = 0
    generated_at: datetime
    caveat: str = NOT_PROOF


# ---------------------------------------------------------------------------
# Relationship context
# ---------------------------------------------------------------------------


class ClassifiedRelationship(AnalyticalBase):
    relationship_id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    context: RelationshipContext
    context_assertion: AssertionType = Field(
        description="observed when the source stated the context, inferred when derived"
    )
    interaction_count: int = 1
    evidence_ids: list[str] = Field(default_factory=list)
    analytical_note: str


class RelationshipContextResponse(AnalyticalBase):
    relationships: list[ClassifiedRelationship] = Field(default_factory=list)
    count: int = 0
    context_totals: dict[str, int] = Field(default_factory=dict)
    caveat: str = (
        "Context describes the setting a relationship was recorded in. Frequent "
        "contact within a family, workplace or community is ordinary and is not "
        "treated as an analytical signal on its own."
    )
