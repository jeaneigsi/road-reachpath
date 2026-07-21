from fastapi.testclient import TestClient

from reachpath.api import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "reachpath"


def test_create_research_dry_run() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/research/runs",
        json={"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True},
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    result = client.get(f"/v1/research/runs/{run_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "completed"
    assert body["result"]["report"]["title"] == "Dossier de prospection — Nadia Karim"
