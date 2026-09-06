from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _report(**overrides) -> dict:
    report = {
        "case_id": "case_api4-001",
        "report_id": "rpt_api4-001",
        "source_record_id": "src_api4-001",
        "observed_at": "2026-01-10T08:00:00Z",
        "text": (
            "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone "
            "+1 (555) 010-2040. Avery drove vehicle ST-2040 at Demo Market and met Blair Keene."
        ),
    }
    report.update(overrides)
    return report


def test_process_report_api_returns_extraction_and_graph_counts() -> None:
    response = client.post("/api/nlp/process", json=_report())

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["source_record_id"] == "src_api4-001"
    assert body["case_id"] == "case_api4-001"
    assert body["resolved_entity_count"] == body["graph_node_count"]
    assert body["graph_node_count"] >= 4
    assert body["graph_edge_count"] >= 2


def test_extract_api_rejects_empty_report() -> None:
    response = client.post("/api/nlp/extract", json=_report(text=""))

    assert response.status_code == 422


def test_extract_api_rejects_a_report_without_a_case() -> None:
    report = _report()
    del report["case_id"]

    assert client.post("/api/nlp/extract", json=report).status_code == 422


def test_batch_extraction_keeps_reports_in_their_own_cases() -> None:
    response = client.post(
        "/api/nlp/extract/batch",
        json={
            "reports": [
                _report(case_id="case_batch-a", source_record_id="src_batch-a"),
                _report(case_id="case_batch-b", source_record_id="src_batch-b"),
            ]
        },
    )

    assert response.status_code == 200
    first, second = response.json()
    assert first["case_id"] == "case_batch-a"
    assert second["case_id"] == "case_batch-b"
    first_ids = {entity["entity_id"] for entity in first["extracted_entities"]}
    second_ids = {entity["entity_id"] for entity in second["extracted_entities"]}
    assert not (first_ids & second_ids)
