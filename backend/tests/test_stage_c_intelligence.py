"""Stage C: the intelligence layer.

The most important tests in this file are the three-population comparisons. The
dense legitimate network carries far more relationships than the coordinated one
(a hospital department where everyone knows everyone), so if the engine were
treating connectedness as suspicion it would rank the hospital *above* the
coordinated network. It must not, and nothing in the engine knows which case is
which.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.intelligence.community_detection import (
    detect_communities,
    partition_modularity,
)
from app.services.intelligence.engine import IntelligenceEngine
from app.services.pipeline import InvestigationPipeline
from app.services.synthetic_populations import (
    COORDINATED_CASE,
    DENSE_CASE,
    NORMAL_CASE,
    all_populations,
    coordinated_population,
    dense_legitimate_population,
    normal_population,
)

client = TestClient(app)
engine = IntelligenceEngine()

FIXED_TIME = datetime(2026, 6, 1, tzinfo=timezone.utc)

# Words that must never appear in any analytical output. The engine describes
# structure; it does not characterise people.
FORBIDDEN_LANGUAGE = {
    "criminal",
    "guilt",
    "guilty",
    "offender",
    "perpetrator",
    "suspect",
    "culprit",
    "probability of crime",
    "likely involved in crime",
}


def _seed(session, dataset) -> str:
    InvestigationPipeline().ingest_dataset(session, dataset)
    return dataset.case_id


@pytest.fixture
def normal(session) -> str:
    return _seed(session, normal_population())


@pytest.fixture
def coordinated(session) -> str:
    return _seed(session, coordinated_population())


@pytest.fixture
def dense(session) -> str:
    return _seed(session, dense_legitimate_population())


@pytest.fixture
def every_population(session) -> list[str]:
    return [_seed(session, dataset) for dataset in all_populations()]


def _entity_by_label(session, case_id: str, label: str) -> str:
    view = engine.view(session, case_id)
    for entity_id, entity in view.entities.items():
        if entity.label == label:
            return entity_id
    raise AssertionError(f"no entity labelled {label!r} in {case_id}")


# ---------------------------------------------------------------------------
# 1  Centrality
# ---------------------------------------------------------------------------


def test_centrality_ranks_entities_with_explanations(session, coordinated) -> None:
    response = engine.centrality(session, coordinated, "degree")

    assert response.count > 0
    assert response.scores[0].rank == 1
    ranks = [score.rank for score in response.scores]
    assert ranks == sorted(ranks), "ranks must be non-decreasing down the list"
    values = [score.value for score in response.scores]
    assert values == sorted(values, reverse=True)
    for score in response.scores:
        assert score.explanation
        assert score.case_id == coordinated


def test_every_centrality_metric_is_available(session, coordinated) -> None:
    for metric in ("degree", "weighted_degree", "betweenness", "closeness"):
        response = engine.centrality(session, coordinated, metric)
        assert response.metric == metric
        assert response.method
        assert not response.insufficient_data


def test_betweenness_finds_the_intermediaries(session, coordinated) -> None:
    """The two people joining the cells should outrank the cell members."""
    response = engine.centrality(session, coordinated, "betweenness")
    by_label = {score.label: score.value for score in response.scores}

    assert by_label["Ines Havel"] > by_label["Quill Ashby"]
    assert by_label["Ovid Strand"] > by_label["Sable Nkemi"]


def test_centrality_reports_insufficient_data_rather_than_zeros(session) -> None:
    from app.db.repositories import CaseRepository

    CaseRepository(session).ensure("case_bare-c001", "Bare")
    session.commit()

    response = engine.centrality(session, "case_bare-c001", "degree")
    assert response.insufficient_data
    assert response.reason
    assert response.scores == []


# ---------------------------------------------------------------------------
# 2  Communities and bridges
# ---------------------------------------------------------------------------


def test_community_detection_groups_the_two_cells(session, coordinated) -> None:
    response = engine.communities(session, coordinated)

    assert response.count >= 2
    assert response.modularity > 0
    for community in response.communities:
        assert community.explanation
        assert community.size == len(community.member_entity_ids)
        assert community.case_id == coordinated

    assignments = detect_communities(engine.view(session, coordinated))
    pax = _entity_by_label(session, coordinated, "Pax Renn")
    quill = _entity_by_label(session, coordinated, "Quill Ashby")
    rune = _entity_by_label(session, coordinated, "Rune Petrov")
    assert assignments[pax] == assignments[quill], "one cell must stay together"
    assert assignments[pax] != assignments[rune], "the two cells must not merge"


def test_bridge_detection_identifies_the_connecting_entities(session, coordinated) -> None:
    response = engine.bridges(session, coordinated)

    assert response.count > 0
    labels = {bridge.label for bridge in response.bridges}
    assert {"Ines Havel", "Ovid Strand"} & labels

    for bridge in response.bridges:
        assert bridge.community_count >= 2
        assert bridge.cross_community_relationship_ids
        assert bridge.explanation
        assert 0 <= bridge.confidence <= 1


def test_a_cohesive_network_yields_no_bridges_and_says_why(session, dense) -> None:
    """The hospital is one blob; nobody in it is bridging anything."""
    view = engine.view(session, dense)
    modularity = partition_modularity(view, detect_communities(view))
    assert modularity < 0.2, "the control population must be one cohesive cluster"

    response = engine.bridges(session, dense)
    assert response.count == 0
    assert response.insufficient_data
    assert "cohesive" in response.reason


# ---------------------------------------------------------------------------
# 3  Paths
# ---------------------------------------------------------------------------


def test_second_degree_path_is_found(session, coordinated) -> None:
    marek = _entity_by_label(session, coordinated, "Marek Idris")
    pax = _entity_by_label(session, coordinated, "Pax Renn")

    response = engine.paths(session, coordinated, marek, pax, max_depth=2)

    assert response.count > 0
    shortest = response.paths[0]
    assert shortest.length == 2
    assert shortest.edges[0].from_entity_id == marek
    assert shortest.edges[-1].to_entity_id == pax


def test_third_degree_path_is_found(session, coordinated) -> None:
    marek = _entity_by_label(session, coordinated, "Marek Idris")
    quill = _entity_by_label(session, coordinated, "Quill Ashby")

    shallow = engine.paths(session, coordinated, marek, quill, max_depth=1)
    assert shallow.count == 0 and shallow.insufficient_data

    deep = engine.paths(session, coordinated, marek, quill, max_depth=3)
    assert deep.count > 0
    assert any(path.length == 3 for path in deep.paths)
    assert all(path.length <= 3 for path in deep.paths)


def test_every_path_hop_carries_its_evidence(session, coordinated) -> None:
    """The whole point: an investigator can justify each hop without a score."""
    marek = _entity_by_label(session, coordinated, "Marek Idris")
    quill = _entity_by_label(session, coordinated, "Quill Ashby")

    response = engine.paths(session, coordinated, marek, quill, max_depth=3)
    assert response.count > 0

    for path in response.paths:
        assert path.explanation
        assert path.evidence_ids
        for edge in path.edges:
            assert edge.relationship_type
            assert edge.assertion_type in {"observed", "inferred", "unknown"}
            assert 0 <= edge.confidence <= 1
            assert edge.evidence_ids, "a hop with no evidence would be a guess"
            assert edge.source_record_ids
            assert edge.from_label and edge.to_label


def test_paths_never_span_investigations(session, every_population) -> None:
    marek = _entity_by_label(session, COORDINATED_CASE, "Marek Idris")
    rhea = _entity_by_label(session, NORMAL_CASE, "Rhea Alcott")

    response = engine.paths(session, COORDINATED_CASE, marek, rhea, max_depth=3)

    assert response.count == 0
    assert response.insufficient_data
    assert "never spans investigations" in response.reason


def test_unconnected_entities_report_no_path_rather_than_failing(session, normal) -> None:
    wren = _entity_by_label(session, normal, "Wren Dabiri")
    vik = _entity_by_label(session, normal, "Vik Oyelaran")

    response = engine.paths(session, normal, wren, vik, max_depth=1)
    assert response.count == 0
    assert response.reason


# ---------------------------------------------------------------------------
# 4  Temporal
# ---------------------------------------------------------------------------


def test_temporal_profile_summarises_recorded_activity(session, coordinated) -> None:
    response = engine.temporal(session, coordinated)

    assert response.count > 0
    profiled = [item for item in response.profiles if not item.insufficient_data]
    assert profiled
    for profile in profiled:
        assert profile.first_event_at <= profile.last_event_at
        assert profile.event_count == sum(b.event_count for b in profile.buckets)
        assert profile.explanation


def test_temporal_analysis_admits_insufficient_data(session, normal) -> None:
    """A thinly recorded entity must say so, not be given an invented pattern."""
    response = engine.temporal(session, normal)
    thin = [item for item in response.profiles if item.insufficient_data]

    assert thin, "this population contains entities with too few timestamps"
    for profile in thin:
        assert profile.reason
        assert profile.buckets == []
        assert "No temporal claim is made" in profile.explanation


def test_temporal_analysis_rejects_an_entity_from_another_case(session, every_population) -> None:
    rhea = _entity_by_label(session, NORMAL_CASE, "Rhea Alcott")

    response = engine.temporal(session, COORDINATED_CASE, rhea)
    assert response.insufficient_data
    assert "not part of investigation" in response.reason


# ---------------------------------------------------------------------------
# 5  Anomalies
# ---------------------------------------------------------------------------


def test_anomaly_signals_share_one_structure(session, coordinated) -> None:
    response = engine.anomalies(session, coordinated)

    assert response.count > 0
    for signal in response.signals:
        assert signal.case_id == coordinated
        assert signal.anomaly_type
        assert signal.category
        assert 0 <= signal.signal_strength <= 1
        assert 0 <= signal.confidence <= 1
        assert signal.explanation
        assert signal.assertion_type in {"observed", "inferred", "unknown"}


def test_financial_chain_detector_finds_the_pass_through(session, coordinated) -> None:
    response = engine.anomalies(session, coordinated)
    chain = [s for s in response.signals if s.anomaly_type == "financial_chain_participation"]

    assert chain, "a multi-step transaction sequence must be detected"
    labels = {signal.label for signal in chain}
    assert "Ines Havel" in labels
    for signal in chain:
        assert signal.relationship_ids
        assert signal.evidence_ids


def test_detectors_that_cannot_run_report_why(session, normal) -> None:
    """Absence of a finding must be distinguishable from absence of a check."""
    response = engine.anomalies(session, normal)

    assert "financial_chain_participation" in response.detectors_skipped
    assert "no recorded financial transactions" in (
        response.detectors_skipped["financial_chain_participation"]
    )
    assert response.detectors_run


def test_cross_case_recurrence_is_off_by_default(session, every_population) -> None:
    response = engine.anomalies(session, COORDINATED_CASE)

    assert "cross_case_recurrence" in response.detectors_skipped
    assert "disabled by default" in response.detectors_skipped["cross_case_recurrence"]
    assert all(s.anomaly_type != "cross_case_recurrence" for s in response.signals)


def test_enabled_cross_case_recurrence_leaks_no_other_case_data(session) -> None:
    """Opt-in recurrence may report that a match exists, never what it is."""
    pipeline = InvestigationPipeline()
    first = normal_population()
    pipeline.ingest_dataset(session, first)

    twin = normal_population().model_dump(mode="json")
    twin["case_id"] = "case_normaltwin-001"
    twin["dataset_id"] = "set_normaltwin-001"
    for record in twin["records"]:
        record["case_id"] = "case_normaltwin-001"
    from app.schemas.investigation import SyntheticDataset

    pipeline.ingest_dataset(session, SyntheticDataset.model_validate(twin))

    response = engine.anomalies(session, NORMAL_CASE, include_cross_case=True)
    recurrence = [s for s in response.signals if s.anomaly_type == "cross_case_recurrence"]

    assert recurrence, "identical entities in two cases should be flagged"
    for signal in recurrence:
        assert signal.case_id == NORMAL_CASE
        assert "case_normaltwin-001" not in signal.explanation
        assert all("normaltwin" not in evidence_id for evidence_id in signal.evidence_ids)


# ---------------------------------------------------------------------------
# 6  Context-aware relationships
# ---------------------------------------------------------------------------


def test_stated_context_is_observed_and_derived_context_is_inferred(session, normal) -> None:
    response = engine.relationship_context(session, normal)

    stated = [item for item in response.relationships if item.context_assertion == "observed"]
    derived = [item for item in response.relationships if item.context_assertion == "inferred"]

    assert stated, "the source states family and business contexts in this population"
    assert derived, "communications carry a derived context"
    assert {item.context for item in stated} & {"family", "business", "community"}
    for item in response.relationships:
        assert item.analytical_note


def test_unstated_links_are_not_given_a_context(session, coordinated) -> None:
    """No context is stated anywhere in this population, so none may be invented."""
    response = engine.relationship_context(session, coordinated)

    assert all(item.context_assertion == "inferred" for item in response.relationships)
    associations = [
        item for item in response.relationships if item.relationship_type == "associated_with"
    ]
    assert associations
    assert all(item.context == "unknown" for item in associations)


def test_ordinary_settings_dampen_signals_and_explain_it(session, normal) -> None:
    response = engine.leads(session, normal, generated_at=FIXED_TIME)
    assert response.count > 0

    dampened = [
        signal
        for lead in response.leads
        for signal in lead.contributing_signals
        if "Weighted down" in signal.explanation
    ]
    assert dampened, "family and workplace patterns must be weighted down"
    assert any("ordinary" in signal.explanation for signal in dampened)


# ---------------------------------------------------------------------------
# 7  Indicators
# ---------------------------------------------------------------------------


def test_indicators_carry_evidence_and_the_not_proof_caveat(session, coordinated) -> None:
    response = engine.indicators(session, coordinated)

    assert response.count > 0
    assert "not proof" in response.caveat.lower()
    for indicator in response.indicators:
        assert indicator.entity_ids
        assert indicator.explanation
        assert "not proof" in indicator.caveat.lower()
        assert 0 <= indicator.confidence <= 1
        assert indicator.case_id == coordinated


def test_financial_chain_structure_indicator_is_produced(session, coordinated) -> None:
    response = engine.indicators(session, coordinated)
    chains = [i for i in response.indicators if i.indicator_type == "financial_chain_structure"]

    assert chains
    chain = chains[0]
    assert len(chain.entity_ids) >= 3
    assert chain.relationship_ids
    assert chain.evidence_ids


def test_no_organised_activity_score_is_exposed(session, coordinated) -> None:
    """Indicators are named patterns, never a single aggregate verdict."""
    payload = engine.indicators(session, coordinated).model_dump()
    assert "organised_crime_score" not in payload
    assert "organized_crime_score" not in payload
    for indicator in payload["indicators"]:
        assert "score" not in " ".join(indicator.keys())


# ---------------------------------------------------------------------------
# 8  Leads and the three populations
# ---------------------------------------------------------------------------


def test_leads_aggregate_multiple_signals_but_retain_each_one(session, coordinated) -> None:
    response = engine.leads(session, coordinated, generated_at=FIXED_TIME)

    assert response.count > 0
    multi = [lead for lead in response.leads if lead.signal_count > 1]
    assert multi, "weak signals must be able to combine into a stronger lead"

    for lead in response.leads:
        assert lead.contributing_signals, "a lead must never lose its signals"
        assert lead.signal_count == len(lead.contributing_signals)
        assert lead.independent_category_count == len(
            {signal.category for signal in lead.contributing_signals}
        )
        assert lead.explanation
        assert lead.network_priority in {"low", "medium", "high"}
        for signal in lead.contributing_signals:
            assert signal.explanation
            assert 0 <= signal.signal_strength <= 1


def test_coordinated_population_produces_high_priority_leads(session, coordinated) -> None:
    response = engine.leads(session, coordinated, generated_at=FIXED_TIME)
    high = [lead for lead in response.leads if lead.network_priority == "high"]

    assert high, "a hub-and-cell structure with a payment chain should be surfaced"
    top = high[0]
    assert top.independent_category_count >= 3
    assert top.evidence_ids
    assert top.lead_type in {"potential_bridge_entity", "coordinated_activity_pattern"}


def test_dense_legitimate_network_produces_no_high_priority_lead(session, dense) -> None:
    """The false-positive control, and the point of the whole exercise."""
    response = engine.leads(session, dense, generated_at=FIXED_TIME)

    assert all(lead.network_priority != "high" for lead in response.leads), (
        "a densely connected legitimate organisation must not be escalated"
    )


def test_ordinary_network_produces_no_high_priority_lead(session, normal) -> None:
    response = engine.leads(session, normal, generated_at=FIXED_TIME)

    assert all(lead.network_priority != "high" for lead in response.leads)


def test_density_alone_does_not_drive_priority(session, every_population) -> None:
    """The decisive comparison: the densest case must not rank the highest."""
    dense_view = engine.view(session, DENSE_CASE)
    coordinated_view = engine.view(session, COORDINATED_CASE)
    assert dense_view.edge_count > coordinated_view.edge_count, (
        "the control must genuinely be the denser network, or this proves nothing"
    )

    dense_high = [
        lead
        for lead in engine.leads(session, DENSE_CASE, generated_at=FIXED_TIME).leads
        if lead.network_priority == "high"
    ]
    coordinated_high = [
        lead
        for lead in engine.leads(session, COORDINATED_CASE, generated_at=FIXED_TIME).leads
        if lead.network_priority == "high"
    ]

    assert not dense_high
    assert coordinated_high


def test_no_analytical_output_characterises_a_person(session, every_population) -> None:
    for case_id in every_population:
        payloads = [
            engine.leads(session, case_id, generated_at=FIXED_TIME).model_dump_json(),
            engine.indicators(session, case_id).model_dump_json(),
            engine.anomalies(session, case_id).model_dump_json(),
            engine.bridges(session, case_id).model_dump_json(),
        ]
        for payload in payloads:
            lowered = payload.lower()
            for word in FORBIDDEN_LANGUAGE:
                assert word not in lowered, f"{word!r} appeared in {case_id} output"


# ---------------------------------------------------------------------------
# 9  Determinism and case isolation
# ---------------------------------------------------------------------------


def test_analysis_is_deterministic(session, coordinated) -> None:
    first = engine.leads(session, coordinated, generated_at=FIXED_TIME).model_dump()
    second = engine.leads(session, coordinated, generated_at=FIXED_TIME).model_dump()
    assert first == second

    assert (
        engine.communities(session, coordinated).model_dump()
        == engine.communities(session, coordinated).model_dump()
    )
    assert (
        engine.centrality(session, coordinated, "betweenness").model_dump()
        == engine.centrality(session, coordinated, "betweenness").model_dump()
    )


def test_analysis_of_one_case_never_includes_another(session, every_population) -> None:
    normal_ids = set(engine.view(session, NORMAL_CASE).entities)
    coordinated_ids = set(engine.view(session, COORDINATED_CASE).entities)
    assert not (normal_ids & coordinated_ids)

    for case_id, own_ids in (
        (NORMAL_CASE, normal_ids),
        (COORDINATED_CASE, coordinated_ids),
    ):
        centrality = engine.centrality(session, case_id, "degree")
        assert {score.entity_id for score in centrality.scores} <= own_ids
        assert all(score.case_id == case_id for score in centrality.scores)

        for community in engine.communities(session, case_id).communities:
            assert set(community.member_entity_ids) <= own_ids

        for lead in engine.leads(session, case_id, generated_at=FIXED_TIME).leads:
            assert lead.case_id == case_id
            assert set(lead.subject_entity_ids) <= own_ids


def test_evidence_on_findings_belongs_to_the_same_case(session, every_population) -> None:
    from app.db.repositories import RecordRepository

    for case_id in every_population:
        known = {
            row.provenance_id for row, _, _ in RecordRepository(session).list_evidence(case_id)
        }
        for lead in engine.leads(session, case_id, generated_at=FIXED_TIME).leads:
            assert set(lead.evidence_ids) <= known, "a lead cited evidence from elsewhere"
        for signal in engine.anomalies(session, case_id).signals:
            assert set(signal.evidence_ids) <= known


# ---------------------------------------------------------------------------
# 10  API surface
# ---------------------------------------------------------------------------


def test_analytics_endpoints_serve_the_persisted_case(session, coordinated) -> None:
    for path in (
        "centrality",
        "communities",
        "bridges",
        "temporal",
        "relationship-context",
        "anomalies",
        "indicators",
        "leads",
    ):
        response = client.get(f"/api/analytics/{coordinated}/{path}")
        assert response.status_code == 200, f"{path}: {response.text}"
        assert response.json()["case_id"] == coordinated


def test_analytics_paths_endpoint_requires_both_endpoints(session, coordinated) -> None:
    marek = _entity_by_label(session, coordinated, "Marek Idris")
    pax = _entity_by_label(session, coordinated, "Pax Renn")

    response = client.get(
        f"/api/analytics/{coordinated}/paths",
        params={"source": marek, "target": pax, "max_depth": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] > 0
    assert body["paths"][0]["edges"][0]["evidence_ids"]

    assert client.get(f"/api/analytics/{coordinated}/paths").status_code == 422


def test_analytics_endpoints_404_on_an_unknown_case() -> None:
    for path in ("centrality", "communities", "bridges", "anomalies", "indicators", "leads"):
        response = client.get(f"/api/analytics/case_absent-c001/{path}")
        assert response.status_code == 404
        assert "case_absent-c001" in response.json()["detail"]


def test_centrality_endpoint_rejects_an_unknown_metric(session, coordinated) -> None:
    response = client.get(
        f"/api/analytics/{coordinated}/centrality", params={"metric": "pagerank"}
    )
    assert response.status_code == 422
