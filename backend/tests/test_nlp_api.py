from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_process_report_api_returns_extraction_and_graph_counts() -> None:
    response = client.post(
        "/api/nlp/process",
        json={
            "report_id": "rpt_api4-001",
            "source_record_id": "src_api4-001",
            "observed_at": "2026-01-10T08:00:00Z",
            "text": "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone +1 (555) 010-2040. Avery drove vehicle ST-2040 at Demo Market and met Blair Keene.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["source_record_id"] == "src_api4-001"
    assert body["resolved_entity_count"] >= 4
    assert body["graph_node_count"] >= 4
    assert body["graph_edge_count"] >= 2


def test_extract_api_rejects_empty_report() -> None:
    response = client.post(
        "/api/nlp/extract",
        json={
            "report_id": "rpt_api4-002",
            "source_record_id": "src_api4-002",
            "observed_at": "2026-01-10T08:00:00Z",
            "text": "",
        },
    )
    assert response.status_code == 422
