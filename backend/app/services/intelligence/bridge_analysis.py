"""Potential bridge entities: who connects otherwise separated clusters.

A bridge is identified from topology alone - an entity with neighbours in two or
more detected communities *and* non-zero betweenness, meaning traffic between
those clusters actually routes through it. No hardcoded rule about entity type,
name or relationship type takes part in the decision.

Betweenness alone is not enough, and neither is touching two communities alone.
An entity in a densely interconnected group can touch several clusters while
being entirely redundant, because every route through it has an equally short
alternative; its betweenness is then zero and it is correctly not a bridge. This
is the property that keeps a large legitimate organisation from being reported
as full of intermediaries.

``confidence`` here describes how well evidenced the bridging *observation* is -
the confidence and provenance of the crossing relationships - and is kept
separate from ``normalized_betweenness``, which describes how structurally
pronounced the position is. Neither is a statement about the entity.
"""

from app.schemas.intelligence import BridgeEntity, BridgeResponse
from app.schemas.investigation import weakest_assertion
from app.services.intelligence.community_detection import (
    detect_communities,
    has_meaningful_structure,
)
from app.services.intelligence.graph_view import CaseGraphView
from app.services.intelligence.network_analysis import normalized_betweenness


def bridges(
    view: CaseGraphView,
    *,
    assignments: dict[str, str] | None = None,
    minimum_betweenness: float = 1e-9,
) -> BridgeResponse:
    if view.node_count < 3:
        return BridgeResponse(
            case_id=view.case_id,
            bridges=[],
            count=0,
            insufficient_data=True,
            reason=(
                f"bridge detection needs at least three entities; this case has "
                f"{view.node_count}"
            ),
        )

    assignments = assignments if assignments is not None else detect_communities(view)

    meaningful, modularity, reason = has_meaningful_structure(view, assignments)
    if not meaningful:
        # Nothing is bridging anything if the groups are not really groups.
        return BridgeResponse(
            case_id=view.case_id, bridges=[], count=0, insufficient_data=True, reason=reason
        )

    betweenness = normalized_betweenness(view)

    found: list[BridgeEntity] = []
    for entity_id in view.node_ids:
        score = betweenness.get(entity_id, 0.0)
        if score <= minimum_betweenness:
            continue

        own_community = assignments.get(entity_id)
        crossing = [
            edge
            for edge in view.incident_edges(entity_id)
            if assignments.get(edge.other_end(entity_id)) != own_community
        ]
        touched = sorted(
            {assignments[node] for node in view.neighbours(entity_id) if node in assignments}
            | ({own_community} if own_community else set())
        )
        if len(touched) < 2 or not crossing:
            continue

        evidence_ids: list[str] = []
        for edge in crossing:
            for evidence_id in edge.evidence_ids:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)

        assertion = weakest_assertion([edge.assertion_type for edge in crossing])
        mean_confidence = sum(edge.confidence for edge in crossing) / len(crossing)
        # An observation resting on inferred links, or on links with no stored
        # provenance, is reported as less well evidenced - not as less true.
        assertion_factor = 1.0 if assertion == "observed" else 0.85
        evidence_factor = 1.0 if all(edge.evidence_ids for edge in crossing) else 0.8
        confidence = round(min(1.0, mean_confidence * assertion_factor * evidence_factor), 4)

        community_text = ", ".join(touched)
        found.append(
            BridgeEntity(
                case_id=view.case_id,
                entity_id=entity_id,
                entity_type=view.entity_type(entity_id),  # type: ignore[arg-type]
                label=view.label(entity_id),
                connected_community_ids=touched,
                community_count=len(touched),
                betweenness=round(betweenness.get(entity_id, 0.0), 6),
                normalized_betweenness=round(min(1.0, score), 6),
                cross_community_relationship_ids=sorted(
                    edge.relationship_id for edge in crossing
                ),
                evidence_ids=evidence_ids,
                assertion_type=assertion,  # type: ignore[arg-type]
                confidence=confidence,
                explanation=(
                    f"{view.label(entity_id)} holds {len(crossing)} relationships that "
                    f"cross between {len(touched)} otherwise separately clustered groups "
                    f"({community_text}), and shortest routes between those groups pass "
                    f"through it. This describes a structural position, not conduct."
                ),
            )
        )

    found.sort(key=lambda item: (-item.community_count, -item.normalized_betweenness, item.entity_id))

    return BridgeResponse(
        case_id=view.case_id,
        bridges=found,
        count=len(found),
        insufficient_data=not found,
        reason=(
            None
            if found
            else "no entity connects two or more clusters along a non-redundant route"
        ),
    )
