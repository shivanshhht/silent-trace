"""Temporal profiling from persisted timestamps only.

No timestamp is ever invented. An event exists at a point in time only if a
persisted relationship carries ``occurred_at`` (when the thing happened) or, in
its absence, ``observed_at`` (when the record was collected). Where neither
exists, the entity is reported with ``insufficient_data`` and a reason, rather
than being given a default time that would then be analysed as if it were real.

Everything here is compared against **the entity's own baseline**, never against
a population norm. "Three contacts in a day" means nothing on its own; three
contacts in a day from someone who otherwise averages one contact a fortnight is
a change in that person's own pattern, and that is all the signal claims.

Buckets are calendar days in UTC. Days are the smallest unit the synthetic data
supports meaningfully, and a fixed unit keeps results reproducible.
"""

from datetime import datetime, timedelta, timezone
from statistics import median, pstdev

from app.schemas.intelligence import TemporalBucket, TemporalProfile, TemporalResponse
from app.services.intelligence.graph_view import CaseGraphView


BUCKET_SIZE = "P1D"
MINIMUM_EVENTS = 3


def _day(moment: datetime) -> datetime:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    aware = aware.astimezone(timezone.utc)
    return datetime(aware.year, aware.month, aware.day, tzinfo=timezone.utc)


def build_profile(view: CaseGraphView, entity_id: str) -> TemporalProfile:
    edges = view.incident_edges(entity_id)
    timed = sorted(
        ((edge.timestamp, edge) for edge in edges if edge.timestamp is not None),
        key=lambda item: (item[0], item[1].relationship_id),
    )

    label = view.label(entity_id)
    if len(timed) < MINIMUM_EVENTS:
        return TemporalProfile(
            case_id=view.case_id,
            entity_id=entity_id,
            label=label,
            event_count=len(timed),
            first_event_at=timed[0][0] if timed else None,
            last_event_at=timed[-1][0] if timed else None,
            insufficient_data=True,
            reason=(
                f"only {len(timed)} timestamped relationship(s) are recorded for this "
                f"entity; at least {MINIMUM_EVENTS} are needed to describe a pattern"
            ),
            explanation=(
                f"{label} has too few timestamped records for temporal analysis. "
                "No temporal claim is made."
            ),
        )

    buckets: dict[datetime, list[str]] = {}
    for moment, edge in timed:
        buckets.setdefault(_day(moment), []).append(edge.relationship_id)

    ordered = sorted(buckets)
    counts = [len(buckets[period]) for period in ordered]
    peak_count = max(counts)
    peak_period = next(period for period in ordered if len(buckets[period]) == peak_count)
    mean = sum(counts) / len(counts)

    counterparties: dict[str, int] = {}
    for _, edge in timed:
        other = edge.other_end(entity_id)
        counterparties[other] = counterparties.get(other, 0) + 1
    repeated = sorted(node for node, count in counterparties.items() if count >= 2)

    repeat_text = (
        f" {len(repeated)} counterparty relationships recur across more than one record."
        if repeated
        else ""
    )

    return TemporalProfile(
        case_id=view.case_id,
        entity_id=entity_id,
        label=label,
        event_count=len(timed),
        first_event_at=timed[0][0],
        last_event_at=timed[-1][0],
        active_period_count=len(ordered),
        mean_events_per_active_period=round(mean, 4),
        peak_period_start=peak_period,
        peak_event_count=peak_count,
        buckets=[
            TemporalBucket(
                period_start=period,
                event_count=len(buckets[period]),
                relationship_ids=sorted(buckets[period]),
            )
            for period in ordered
        ],
        repeated_counterparty_ids=repeated,
        insufficient_data=False,
        explanation=(
            f"{len(timed)} timestamped relationships between "
            f"{timed[0][0].date()} and {timed[-1][0].date()}, spread over "
            f"{len(ordered)} active day(s), averaging {round(mean, 2)} per active day "
            f"with a peak of {peak_count} on {peak_period.date()}.{repeat_text}"
        ),
    )


def burst_strength(profile: TemporalProfile) -> float:
    """How far the busiest day rises above this entity's own average, 0..1.

    Expressed as standard deviations above the mean and squashed into 0..1, so a
    steady pattern scores near zero however busy it is overall.
    """
    if profile.insufficient_data or profile.active_period_count < 2:
        return 0.0
    counts = [bucket.event_count for bucket in profile.buckets]
    spread = pstdev(counts)
    if spread == 0:
        return 0.0
    deviations = (profile.peak_event_count - profile.mean_events_per_active_period) / spread
    return round(max(0.0, min(1.0, deviations / 3.0)), 4)


def gap_strength(profile: TemporalProfile) -> tuple[float, timedelta | None]:
    """How pronounced the longest silence is against this entity's typical spacing."""
    if profile.insufficient_data or len(profile.buckets) < 4:
        return 0.0, None
    periods = [bucket.period_start for bucket in profile.buckets]
    gaps = [later - earlier for earlier, later in zip(periods, periods[1:])]
    if not gaps:
        return 0.0, None
    typical = median(gaps)
    longest = max(gaps)
    if typical.total_seconds() <= 0:
        return 0.0, longest
    ratio = longest / typical
    if ratio < 3.0:
        return 0.0, longest
    return round(max(0.0, min(1.0, (ratio - 3.0) / 7.0 + 0.3)), 4), longest


def temporal_profiles(view: CaseGraphView) -> dict[str, TemporalProfile]:
    return {entity_id: build_profile(view, entity_id) for entity_id in view.node_ids}


def temporal(view: CaseGraphView, entity_id: str | None = None) -> TemporalResponse:
    if view.node_count == 0:
        return TemporalResponse(
            case_id=view.case_id,
            bucket_size=BUCKET_SIZE,
            profiles=[],
            count=0,
            insufficient_data=True,
            reason="this investigation has no persisted entities yet",
        )

    if entity_id is not None:
        if entity_id not in view.entities:
            return TemporalResponse(
                case_id=view.case_id,
                bucket_size=BUCKET_SIZE,
                profiles=[],
                count=0,
                insufficient_data=True,
                reason=(
                    f"entity '{entity_id}' is not part of investigation {view.case_id}"
                ),
            )
        profiles = [build_profile(view, entity_id)]
    else:
        profiles = [temporal_profiles(view)[node] for node in view.node_ids]

    usable = [profile for profile in profiles if not profile.insufficient_data]
    profiles.sort(key=lambda item: (-item.event_count, item.entity_id))

    return TemporalResponse(
        case_id=view.case_id,
        bucket_size=BUCKET_SIZE,
        profiles=profiles,
        count=len(profiles),
        insufficient_data=not usable,
        reason=(
            None
            if usable
            else "no entity in this case has enough timestamped relationships to profile"
        ),
    )
