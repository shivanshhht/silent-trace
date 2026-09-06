"""Analytics API over the persisted investigation.

These endpoints read; they never write, and they never build a graph of their
own - they consume the same persisted projection the investigations API serves,
so an analytical answer can always be traced back to the graph the investigator
is looking at.

Case isolation is enforced twice: the case must exist (404 otherwise), and the
analysis view is constructed for that case alone, so there is no query here that
could return another investigation's data even if a filter were forgotten.

Every response carries its own caveat text explaining what its numbers mean and
what they do not. That text is part of the contract, not decoration.
"""

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import SessionDep
from app.db.repositories import CaseRepository
from app.schemas.intelligence import (
    AnomalyResponse,
    BridgeResponse,
    CentralityResponse,
    CommunityResponse,
    IndicatorResponse,
    LeadResponse,
    PathResponse,
    RelationshipContextResponse,
    TemporalResponse,
)
from app.services.intelligence.engine import IntelligenceEngine
from app.services.intelligence.path_analysis import DEFAULT_MAX_DEPTH

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

engine = IntelligenceEngine()


def _require_case(session, case_id: str) -> None:
    if CaseRepository(session).get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"investigation '{case_id}' not found")


@router.get("/{case_id}/centrality", response_model=CentralityResponse)
def centrality(
    case_id: str,
    session: SessionDep,
    metric: str = Query(
        "degree",
        pattern="^(degree|weighted_degree|betweenness|closeness)$",
        description="which centrality to compute",
    ),
    limit: int | None = Query(None, ge=1, le=500),
) -> CentralityResponse:
    _require_case(session, case_id)
    return engine.centrality(session, case_id, metric, limit)


@router.get("/{case_id}/communities", response_model=CommunityResponse)
def communities(case_id: str, session: SessionDep) -> CommunityResponse:
    _require_case(session, case_id)
    return engine.communities(session, case_id)


@router.get("/{case_id}/bridges", response_model=BridgeResponse)
def bridges(case_id: str, session: SessionDep) -> BridgeResponse:
    _require_case(session, case_id)
    return engine.bridges(session, case_id)


@router.get("/{case_id}/paths", response_model=PathResponse)
def paths(
    case_id: str,
    session: SessionDep,
    source: str = Query(..., min_length=1, description="source entity canonical id"),
    target: str = Query(..., min_length=1, description="target entity canonical id"),
    max_depth: int = Query(DEFAULT_MAX_DEPTH, ge=1, le=6),
) -> PathResponse:
    _require_case(session, case_id)
    return engine.paths(session, case_id, source, target, max_depth)


@router.get("/{case_id}/temporal", response_model=TemporalResponse)
def temporal(
    case_id: str,
    session: SessionDep,
    entity_id: str | None = Query(None, min_length=1),
) -> TemporalResponse:
    _require_case(session, case_id)
    return engine.temporal(session, case_id, entity_id)


@router.get("/{case_id}/relationship-context", response_model=RelationshipContextResponse)
def relationship_context(case_id: str, session: SessionDep) -> RelationshipContextResponse:
    _require_case(session, case_id)
    return engine.relationship_context(session, case_id)


@router.get("/{case_id}/anomalies", response_model=AnomalyResponse)
def anomalies(
    case_id: str,
    session: SessionDep,
    include_cross_case: bool = Query(
        False,
        description=(
            "opt in to cross-investigation recurrence checks; off by default "
            "because answering them requires reading outside this case"
        ),
    ),
) -> AnomalyResponse:
    _require_case(session, case_id)
    return engine.anomalies(session, case_id, include_cross_case=include_cross_case)


@router.get("/{case_id}/indicators", response_model=IndicatorResponse)
def indicators(case_id: str, session: SessionDep) -> IndicatorResponse:
    _require_case(session, case_id)
    return engine.indicators(session, case_id)


@router.get("/{case_id}/leads", response_model=LeadResponse)
def leads(
    case_id: str,
    session: SessionDep,
    include_cross_case: bool = Query(False),
) -> LeadResponse:
    _require_case(session, case_id)
    return engine.leads(session, case_id, include_cross_case=include_cross_case)
