from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_resolve_and_graph_retrieval_api() -> None:
    records = [
        {
            "record_id": "per_api3-001",
            "record_type": "person",
            "observed_at": "2026-01-01T00:00:00Z",
            "data": {"entity_id": "per_api3-001", "display_name": "Demo Person"},
            "provenance": [{"source_record_id": "src_api3-001", "record_id": "per_api3-001", "observed_at": "2026-01-01T00:00:00Z"}],
        },
        {
            "record_id": "loc_api3-001",
            "record_type": "location",
            "observed_at": "2026-01-01T00:00:00Z",
            "data": {"entity_id": "loc_api3-001", "label": "Demo Place", "locality": "Example City"},
            "provenance": [{"source_record_id": "src_api3-001", "record_id": "loc_api3-001", "observed_at": "2026-01-01T00:00:00Z"}],
        },
    ]
    resolved = client.post("/api/graph/resolve", json={"records": records})
    assert resolved.status_code == 200
    assert len(resolved.json()["entities"]) == 2

    graph = client.post("/api/graph", json={"graph_id": "graph_api3-001", "records": records})
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) == 2

    fetched = client.get("/api/graph/graph_api3-001")
    assert fetched.status_code == 200
    evidence = client.get("/api/graph/graph_api3-001/evidence/per_api3-001")
    assert evidence.status_code == 200
    assert evidence.json()["evidence"][0]["source_record_id"] == "src_api3-001"
