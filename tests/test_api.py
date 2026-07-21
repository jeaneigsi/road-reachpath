from fastapi.testclient import TestClient

from reachpath.api import create_app
from reachpath.settings import Settings


def client(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", dry_run=True)
    return TestClient(create_app(settings))


def test_health(tmp_path) -> None:
    response = client(tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "reachpath"


def test_create_research_is_durable_and_scoped(tmp_path) -> None:
    api = client(tmp_path)
    headers = {"X-Workspace-ID": "acme", "Idempotency-Key": "research-001"}
    response = api.post(
        "/v1/research/runs",
        json={"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True},
        headers=headers,
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert response.json()["workspace_id"] == "acme"

    result = api.get(f"/v1/research/runs/{run_id}", headers=headers)
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "completed"
    assert body["result"]["report"]["title"] == "Dossier de prospection — Nadia Karim"

    replay = api.post(
        "/v1/research/runs",
        json={"person": "Different Person", "objective": "Different objective", "dry_run": True},
        headers=headers,
    )
    assert replay.status_code == 202
    assert replay.json()["run_id"] == run_id

    cross_workspace = api.get(
        f"/v1/research/runs/{run_id}", headers={"X-Workspace-ID": "other"}
    )
    assert cross_workspace.status_code == 404

    restarted = client(tmp_path)
    durable = restarted.get(f"/v1/research/runs/{run_id}", headers=headers)
    assert durable.status_code == 200
    assert durable.json()["status"] == "completed"
