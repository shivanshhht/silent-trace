"""Context-aware relationship analysis.

This module extends the Stage A relationship model rather than replacing it. The
canonical relationship vocabulary is untouched; what is added is the *setting* a
relationship sits in, which is what allows analysis to tell an ordinary dense
network apart from a coordinated one without looking at density alone.

**Where context comes from.** If a source document stated it, the context is
that, and it is reported as ``observed``. Otherwise a structural context is
derived from the relationship type (a transaction is financial, a call is
communication) and reported as ``inferred``. Personal attributes are never used
to guess: shared surnames, addresses and demographics are not evidence of a
family or community tie, and treating them as such would be exactly the
sensitive inference this system must not make. Where nothing supports a context,
it stays ``unknown``.

**Why it matters for scoring.** Frequent contact inside a family, a workplace or
a community organisation is ordinary. A detector firing on a pattern that lies
entirely within such contexts is dampened and says so in its explanation, so
being close to your relatives or busy at work does not accumulate into an
investigative lead.
"""

from collections import Counter

from app.schemas.intelligence import ClassifiedRelationship, RelationshipContextResponse
from app.services.intelligence.graph_view import CaseGraphView


# Settings in which frequent, dense interaction is unremarkable. Membership here
# lowers the weight of a signal; it never raises it, and it never suppresses a
# signal that also rests on relationships outside these settings.
ORDINARY_CONTEXTS = {"family", "community", "business"}

# How much a pattern is discounted when it lies wholly inside an ordinary
# setting. Set high deliberately: the failure mode this guards against is a
# family or a workplace accumulating enough small signals to be escalated, and
# a timid discount does not prevent that.
ORDINARY_DAMPENING = 0.75

ANALYTICAL_NOTE = {
    "family": (
        "Family contact is ordinary. Frequency within a family is not treated as "
        "an analytical signal."
    ),
    "community": (
        "Community and membership ties are ordinary. Density within a community "
        "is not treated as an analytical signal."
    ),
    "business": (
        "Business and employment ties are ordinary. Volume of workplace contact "
        "is not treated as an analytical signal."
    ),
    "communication": "Recorded communication between two entities.",
    "financial": "Recorded transfer of value between two entities.",
    "geographic": "Recorded presence at, or association with, a place.",
    "operational": "A recorded interaction, use or involvement.",
    "unknown": (
        "The source asserted a link without stating its nature. No setting is "
        "assumed."
    ),
}


def ordinary_pairs(view: CaseGraphView) -> set[frozenset[str]]:
    """Pairs of entities that share a documented ordinary setting.

    Context has to propagate, or the dampening is useless. A phone call between
    two hospital colleagues is recorded as a communication, not as a workplace
    relationship, so on its own it looks like any other call. What makes it
    ordinary is a *separate* recorded fact: both parties are members of the same
    employer. This walks those stated affiliations and returns the pairs they
    connect.

    Only affiliations the source actually stated are used - a shared employer,
    household or community organisation, each carrying an ordinary context on
    its own relationship. Nothing is inferred from names, addresses or any
    personal attribute, and an affiliation through a merely co-located place is
    not enough on its own to make an unrelated interaction ordinary.
    """
    cached = getattr(view, "_ordinary_pairs_cache", None)
    if cached is not None:
        return cached

    anchors: dict[str, set[str]] = {}
    pairs: set[frozenset[str]] = set()

    for edge in view.edges:
        if edge.context not in ORDINARY_CONTEXTS:
            continue
        # A stated ordinary relationship makes that pair ordinary directly.
        pairs.add(frozenset({edge.source, edge.target}))
        # Membership of a shared organisation or household anchor.
        for node, other in ((edge.source, edge.target), (edge.target, edge.source)):
            if view.entity_type(other) in {"organization", "location"}:
                anchors.setdefault(other, set()).add(node)

    for members in anchors.values():
        ordered = sorted(members)
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                pairs.add(frozenset({first, second}))

    object.__setattr__(view, "_ordinary_pairs_cache", pairs)
    return pairs


def ordinary_fraction(view: CaseGraphView, relationship_ids: list[str]) -> float:
    """Share of these relationships that sit in an ordinary social setting.

    A relationship counts as ordinary either because its own context says so, or
    because its two endpoints share a documented ordinary affiliation.
    """
    if not relationship_ids:
        return 0.0
    wanted = set(relationship_ids)
    matched = [edge for edge in view.edges if edge.relationship_id in wanted]
    if not matched:
        return 0.0
    affiliated = ordinary_pairs(view)
    ordinary = sum(
        1
        for edge in matched
        if edge.context in ORDINARY_CONTEXTS
        or frozenset({edge.source, edge.target}) in affiliated
    )
    return ordinary / len(matched)


def context_dampening(view: CaseGraphView, relationship_ids: list[str]) -> tuple[float, str]:
    """Multiplier for a signal resting on these relationships, plus the reason.

    A signal grounded entirely in ordinary settings is reduced substantially; a
    mixed one is reduced in proportion. Nothing is ever amplified here.
    """
    fraction = ordinary_fraction(view, relationship_ids)
    if fraction <= 0.0:
        return 1.0, ""
    multiplier = 1.0 - ORDINARY_DAMPENING * fraction
    if fraction >= 0.999:
        return multiplier, (
            " Weighted down because every supporting relationship sits in an "
            "ordinary family, community or workplace setting, where this pattern "
            "is expected."
        )
    return multiplier, (
        f" Weighted down because {round(fraction * 100)}% of the supporting "
        "relationships sit in ordinary family, community or workplace settings."
    )


def classify_relationships(view: CaseGraphView) -> RelationshipContextResponse:
    classified: list[ClassifiedRelationship] = []
    for edge in sorted(view.edges, key=lambda item: item.relationship_id):
        classified.append(
            ClassifiedRelationship(
                case_id=view.case_id,
                relationship_id=edge.relationship_id,
                from_entity_id=edge.source,
                to_entity_id=edge.target,
                relationship_type=edge.relationship_type,  # type: ignore[arg-type]
                context=edge.context,  # type: ignore[arg-type]
                context_assertion=edge.context_assertion,  # type: ignore[arg-type]
                interaction_count=edge.interaction_count,
                evidence_ids=list(edge.evidence_ids),
                analytical_note=ANALYTICAL_NOTE.get(edge.context, ANALYTICAL_NOTE["unknown"]),
            )
        )

    totals = Counter(item.context for item in classified)
    return RelationshipContextResponse(
        case_id=view.case_id,
        relationships=classified,
        count=len(classified),
        context_totals=dict(sorted(totals.items())),
    )
