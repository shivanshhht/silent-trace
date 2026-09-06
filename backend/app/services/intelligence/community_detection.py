"""Community detection by greedy modularity maximisation.

Why this algorithm: it is deterministic, it needs no random seed or resolution
parameter to be pinned for tests, it refuses to merge disconnected parts of a
graph on its own (the modularity gain for a pair with no edge between them is
always negative), and it stops when no merge improves the partition rather than
being told how many communities to find. On investigation-sized graphs the
quadratic cost is irrelevant.

**Weighting.** Parallel relationships between the same pair are collapsed into a
single weight equal to how many distinct relationships link them, so a pair who
both spoke and transacted are held together more strongly than a pair with a
single recorded link. Interaction volume is deliberately *not* used as the
weight: a family that phones each other daily would otherwise dominate the
partition purely by being close.

**What a community is not.** A community is a cluster of connected records.
Households, workplaces, congregations and friend groups are communities. Nothing
about membership is a finding about a member.
"""

from collections import Counter

from app.schemas.intelligence import Community, CommunityResponse
from app.services.intelligence.graph_view import CaseGraphView


METHOD = "greedy modularity maximisation (deterministic, ties broken on entity id)"


def _pair_weights(view: CaseGraphView) -> dict[tuple[str, str], float]:
    """Collapse parallel edges into one weight per unordered pair."""
    weights: dict[tuple[str, str], float] = {}
    for edge in view.edges:
        if edge.source == edge.target:
            continue
        key = (edge.source, edge.target) if edge.source < edge.target else (edge.target, edge.source)
        weights[key] = weights.get(key, 0.0) + 1.0
    return weights


def _modularity(
    membership: dict[str, int],
    weights: dict[tuple[str, str], float],
    strength: dict[str, float],
    total: float,
) -> float:
    if total <= 0:
        return 0.0
    internal: dict[int, float] = {}
    degree_sum: dict[int, float] = {}
    for node, community in membership.items():
        degree_sum[community] = degree_sum.get(community, 0.0) + strength.get(node, 0.0)
    for (left, right), weight in weights.items():
        if membership[left] == membership[right]:
            internal[membership[left]] = internal.get(membership[left], 0.0) + weight
    return sum(
        internal.get(community, 0.0) / total
        - (degree_sum.get(community, 0.0) / (2.0 * total)) ** 2
        for community in degree_sum
    )


def detect_communities(view: CaseGraphView) -> dict[str, str]:
    """Partition the case graph. Returns ``entity_id -> community_id``."""
    nodes = view.node_ids
    if not nodes:
        return {}

    weights = _pair_weights(view)
    total = sum(weights.values())
    strength: dict[str, float] = {node: 0.0 for node in nodes}
    for (left, right), weight in weights.items():
        strength[left] += weight
        strength[right] += weight

    membership: dict[str, int] = {node: index for index, node in enumerate(nodes)}

    if total > 0:
        while True:
            between: dict[tuple[int, int], float] = {}
            for (left, right), weight in weights.items():
                a, b = membership[left], membership[right]
                if a == b:
                    continue
                key = (a, b) if a < b else (b, a)
                between[key] = between.get(key, 0.0) + weight

            if not between:
                break

            degree_sum: dict[int, float] = {}
            for node, community in membership.items():
                degree_sum[community] = degree_sum.get(community, 0.0) + strength[node]

            best_gain = 0.0
            best_pair: tuple[int, int] | None = None
            for (a, b), shared in sorted(between.items()):
                gain = shared / total - (degree_sum[a] * degree_sum[b]) / (2.0 * total * total)
                # Strict improvement only, and ties resolved by the sorted order
                # above, so the same graph always yields the same partition.
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best_pair = (a, b)

            if best_pair is None:
                break

            keep, absorb = best_pair
            for node, community in membership.items():
                if community == absorb:
                    membership[node] = keep

    # Rename to stable, size-ordered public ids.
    groups: dict[int, list[str]] = {}
    for node in nodes:
        groups.setdefault(membership[node], []).append(node)
    ordered = sorted(groups.values(), key=lambda members: (-len(members), members[0]))
    return {
        node: f"com_{index:03d}"
        for index, members in enumerate(ordered, start=1)
        for node in members
    }


# Modularity below which a partition is not treated as real community structure.
#
# Greedy modularity always returns *some* split, because a single community
# scores exactly zero. On a graph that is genuinely one cohesive cluster - a
# hospital department, a university faculty - it therefore hands back an
# arbitrary division, and every member then appears to "connect two
# communities". That artefact is precisely how a dense legitimate network turns
# into a page of intermediaries.
#
# A low modularity score is the signal that this has happened: it says the
# partition explains little more than chance. Below this threshold the graph is
# reported as one cluster and no cross-community claim is made about anybody.
MEANINGFUL_MODULARITY = 0.20


def partition_modularity(view: CaseGraphView, assignments: dict[str, str]) -> float:
    """Modularity of an existing assignment, for callers that already have one."""
    if not assignments:
        return 0.0
    weights = _pair_weights(view)
    total = sum(weights.values())
    strength: dict[str, float] = {node: 0.0 for node in view.node_ids}
    for (left, right), weight in weights.items():
        strength[left] += weight
        strength[right] += weight
    numeric = {node: int(cid.removeprefix("com_")) for node, cid in assignments.items()}
    return _modularity(numeric, weights, strength, total)


def has_meaningful_structure(
    view: CaseGraphView, assignments: dict[str, str]
) -> tuple[bool, float, str]:
    """Whether cross-community reasoning is justified on this graph.

    Returns ``(ok, modularity, reason)``. When this is false, no detector may
    describe an entity as connecting or bridging clusters, because the clusters
    themselves are an artefact of partitioning a single cohesive group.
    """
    modularity = partition_modularity(view, assignments)
    distinct = len(set(assignments.values()))
    if distinct < 2:
        return False, modularity, (
            "this case forms a single connected cluster, so no entity connects "
            "separate groups"
        )
    if modularity < MEANINGFUL_MODULARITY:
        return False, modularity, (
            f"this network is one cohesive cluster (modularity {round(modularity, 3)} "
            f"is below {MEANINGFUL_MODULARITY}); its apparent sub-groups are an "
            "artefact of partitioning, so no entity is treated as bridging them"
        )
    return True, modularity, ""


def _density(view: CaseGraphView, members: list[str]) -> float:
    if len(members) < 2:
        return 0.0
    member_set = set(members)
    connected_pairs = {
        (edge.source, edge.target) if edge.source < edge.target else (edge.target, edge.source)
        for edge in view.edges
        if edge.source in member_set and edge.target in member_set and edge.source != edge.target
    }
    possible = len(members) * (len(members) - 1) / 2
    return round(len(connected_pairs) / possible, 4) if possible else 0.0


def communities(view: CaseGraphView) -> CommunityResponse:
    assignments = detect_communities(view)

    if not assignments:
        return CommunityResponse(
            case_id=view.case_id,
            communities=[],
            count=0,
            modularity=0.0,
            method=METHOD,
            insufficient_data=True,
            reason="this investigation has no persisted entities yet",
        )

    weights = _pair_weights(view)
    total = sum(weights.values())
    strength: dict[str, float] = {node: 0.0 for node in view.node_ids}
    for (left, right), weight in weights.items():
        strength[left] += weight
        strength[right] += weight
    numeric = {node: int(cid.removeprefix("com_")) for node, cid in assignments.items()}
    modularity = _modularity(numeric, weights, strength, total)

    grouped: dict[str, list[str]] = {}
    for node, community_id in assignments.items():
        grouped.setdefault(community_id, []).append(node)

    results: list[Community] = []
    for community_id in sorted(grouped):
        members = sorted(grouped[community_id])
        member_set = set(members)

        internal = [
            edge
            for edge in view.edges
            if edge.source in member_set and edge.target in member_set
        ]
        external = [
            edge
            for edge in view.edges
            if (edge.source in member_set) != (edge.target in member_set)
        ]
        representatives = sorted(members, key=lambda node: (-view.degree(node), node))[:3]
        context_counts = Counter(edge.context for edge in internal)
        dominant = [context for context, _ in context_counts.most_common(3)]
        density = _density(view, members)

        if len(members) == 1:
            explanation = (
                f"{view.label(members[0])} forms a community of one: it has no "
                "recorded relationship that ties it more closely to any other cluster."
            )
        else:
            leading = ", ".join(view.label(node) for node in representatives)
            context_text = (
                f" Connections are mostly {dominant[0]} in nature."
                if dominant and dominant[0] != "unknown"
                else ""
            )
            explanation = (
                f"{len(members)} entities held together by {len(internal)} internal "
                f"relationships (internal density {density}), against {len(external)} "
                f"relationships reaching outside the group. Members were grouped because "
                f"they are more densely connected to each other than to the rest of the "
                f"case.{context_text} Most connected members: {leading}."
            )

        results.append(
            Community(
                case_id=view.case_id,
                community_id=community_id,
                member_entity_ids=members,
                size=len(members),
                representative_entity_ids=representatives,
                internal_relationship_ids=sorted(edge.relationship_id for edge in internal),
                external_relationship_ids=sorted(edge.relationship_id for edge in external),
                dominant_contexts=dominant,  # type: ignore[arg-type]
                internal_density=density,
                explanation=explanation,
            )
        )

    return CommunityResponse(
        case_id=view.case_id,
        communities=results,
        count=len(results),
        modularity=round(modularity, 6),
        method=METHOD,
    )
