from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)

CASE = "case_api3-001"


def _records() -> list[dict]:
    return [
        {
            "case_id": CASE,
            "record_id": "per_api3-001",
            "record_type": "person",
            "observed_at": "2026-01-01T00:00:00Z",
            "data": {"entity_id": "per_api3-001", "display_name": "Demo Person"},
            "provenance": [
                {
                    "case_id": CASE,
                    "source_record_id": "src_api3-001",
                    "record_id": "per_api3-001",
                    "observed_at": "2026-01-01T00:00:00Z",
                }
            ],
        },
        {
            "case_id": CASE,
            "record_id": "loc_api3-001",
            "record_type": "location",
            "observed_at": "2026-01-01T00:00:00Z",
            "data": {"entity_id": "loc_api3-001", "label": "Demo Place", "locality": "Example City"},
            "provenance": [
                {
                    "case_id": CASE,
                    "source_record_id": "src_api3-001",
                    "record_id": "loc_api3-001",
                    "observed_at": "2026-01-01T00:00:00Z",
                }
            ],
        },
    ]


def test_resolve_and_graph_retrieval_api() -> None:
    records = _records()

    resolved = client.post("/api/graph/resolve", json={"case_id": CASE, "records": records})
    assert resolved.status_code == 200
    assert len(resolved.json()["entities"]) == 2
    assert resolved.json()["case_id"] == CASE

    graph = client.post("/api/graph", json={"graph_id": "graph_api3-001", "case_id": CASE, "records": records})
    assert graph.status_code == 200
    body = graph.json()
    assert len(body["nodes"]) == 2
    assert body["case_id"] == CASE

    fetched = client.get("/api/graph/graph_api3-001")
    assert fetched.status_code == 200

    node_id = body["nodes"][0]["node_id"]
    evidence = client.get(f"/api/graph/graph_api3-001/evidence/{node_id}")
    assert evidence.status_code == 200
    assert evidence.json()["evidence"][0]["source_record_id"] == "src_api3-001"
    assert evidence.json()["element_types"] == ["node"]


def test_unknown_graph_and_element_return_404() -> None:
    assert client.get("/api/graph/graph_missing-001").status_code == 404

    client.post("/api/graph", json={"graph_id": "graph_api3-002", "case_id": CASE, "records": _records()})
    assert client.get("/api/graph/graph_api3-002/evidence/per_nope-001").status_code == 404


def test_graph_api_rejects_records_from_another_case() -> None:
    records = _records()
    records[1]["case_id"] = "case_other-001"
    records[1]["provenance"][0]["case_id"] = "case_other-001"

    response = client.post(
        "/api/graph", json={"graph_id": "graph_api3-003", "case_id": CASE, "records": records}
    )

    assert response.status_code == 422
    assert "case_other-001" in response.json()["detail"]
