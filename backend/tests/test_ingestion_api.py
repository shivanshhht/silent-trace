from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ingestion_api_accepts_valid_dataset() -> None:
    response = client.post(
        "/api/ingestion",
        json={
            "dataset": {
                "dataset_id": "set_api-001",
                "description": "Synthetic API test dataset",
                "records": [
                    {
                        "record_id": "src_api-001",
                        "record_type": "evidence_source",
                        "source_record_id": "src_api-001",
                        "observed_at": "2026-01-01T00:00:00Z",
                        "payload": {
                            "record_id": "src_api-001",
                            "source_type": "synthetic_log",
                            "title": "API test source",
                            "collected_at": "2026-01-01T00:00:00Z",
                            "reliability": "medium",
                            "content": "Fictional API test content.",
                        },
                    }
                ],
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1
    assert response.json()["accepted_records"][0]["provenance"] == ["src_api-001"]
