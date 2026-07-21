import asyncio

from fastapi.testclient import TestClient

from reachpath.api import create_app
from reachpath.domain import UsageMetrics
from reachpath.settings import Settings
from reachpath.worker import drain_once


def client(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", dry_run=True)
    return TestClient(create_app(settings))


def test_health(tmp_path) -> None:
    response = client(tmp_path).get("/health", headers={"X-Request-ID": "req-test"})
    assert response.status_code == 200
    assert response.json()["service"] == "reachpath"
    assert response.headers["X-Request-ID"] == "req-test"
    assert response.headers["X-Correlation-ID"] == "req-test"


def test_frontend_origin_is_allowed_by_cors(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cors.db'}",
        dry_run=True,
        cors_origins="http://localhost:3000",
    )
    api = TestClient(create_app(settings))
    response = api.options(
        "/v1/research/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,x-workspace-id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


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
    assert len(body["result"]["strategies"]["scenarios"]) == 3
    assert api.get(f"/v1/research/runs/{run_id}/strategy", headers=headers).status_code == 200
    listed = api.get("/v1/research/runs", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["run_id"] == run_id

    replay = api.post(
        "/v1/research/runs",
        json={"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True},
        headers=headers,
    )
    assert replay.status_code == 202
    assert replay.json()["run_id"] == run_id

    conflict = api.post(
        "/v1/research/runs",
        json={"person": "Different Person", "objective": "Different objective", "dry_run": True},
        headers=headers,
    )
    assert conflict.status_code == 409

    cross_workspace = api.get(
        f"/v1/research/runs/{run_id}", headers={"X-Workspace-ID": "other"}
    )
    assert cross_workspace.status_code == 404

    restarted = client(tmp_path)
    durable = restarted.get(f"/v1/research/runs/{run_id}", headers=headers)
    assert durable.status_code == 200
    assert durable.json()["status"] == "completed"
    quota = restarted.get("/v1/usage/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["workspace_id"] == "acme"
    audit = restarted.get("/v1/audit/events", headers=headers)
    assert audit.status_code == 200
    assert {event["action"] for event in audit.json()} >= {
        "research.created",
        "research.status_changed",
    }


def test_worker_drains_queued_run(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        dry_run=True,
        auto_execute=False,
    )
    application = create_app(settings)
    api = TestClient(application)
    response = api.post(
        "/v1/research/runs",
        json={"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True},
    )
    run_id = response.json()["run_id"]
    assert response.json()["status"] == "queued"
    assert asyncio.run(drain_once(application)) == 1
    assert api.get(f"/v1/research/runs/{run_id}").json()["status"] == "completed"


def test_ambiguous_run_can_be_clarified_and_restarted(tmp_path) -> None:
    class FakeOrchestrator:
        calls = 0

        async def execute(self, _request, *, workspace_id, run_id):
            self.calls += 1
            return {
                "evidence": {"usage": {}},
                "dossier": {"status": "ambiguous"} if self.calls == 1 else {"status": "resolved"},
                "strategies": {"scenarios": []},
                "report": {},
            }

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'clarify.db'}", dry_run=True)
    application = create_app(settings)
    application.state.orchestrator = FakeOrchestrator()
    api = TestClient(application)
    payload = {"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True}
    created = api.post("/v1/research/runs", json=payload)
    run_id = created.json()["run_id"]
    assert api.get(f"/v1/research/runs/{run_id}").json()["status"] == "needs_clarification"

    clarified = api.post(
        f"/v1/research/runs/{run_id}/clarify",
        json={**payload, "location": "Casablanca", "source_person": "Alex Martin"},
    )
    assert clarified.status_code == 202
    assert api.get(f"/v1/research/runs/{run_id}").json()["status"] == "completed"


def test_research_is_rejected_when_workspace_budget_is_exhausted(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'budget.db'}",
        dry_run=True,
        monthly_budget_usd=0.10,
    )
    application = create_app(settings)
    api = TestClient(application)
    first = api.post(
        "/v1/research/runs",
        json={
            "person": "Nadia Karim",
            "objective": "Obtenir un rendez-vous",
            "max_cost_usd": 0.10,
            "dry_run": True,
        },
    )
    run_id = first.json()["run_id"]
    application.state.store.update(
        "local", run_id, usage=UsageMetrics(cost_usd=0.10)
    )
    blocked = api.post(
        "/v1/research/runs",
        json={
            "person": "Alex Martin",
            "objective": "Obtenir un rendez-vous",
            "max_cost_usd": 0.01,
            "dry_run": True,
        },
    )
    assert blocked.status_code == 402
    assert blocked.json()["detail"]["code"] == "monthly_budget_exceeded"


def test_privacy_export_and_delete_are_workspace_scoped(tmp_path) -> None:
    api = client(tmp_path)
    created = api.post(
        "/v1/research/runs",
        json={"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True},
        headers={"X-Workspace-ID": "acme"},
    )
    run_id = created.json()["run_id"]
    exported = api.get(
        "/v1/privacy/people/Nadia%20Karim/export",
        headers={"X-Workspace-ID": "acme"},
    )
    assert exported.status_code == 200
    assert exported.json()["research_runs"][0]["run_id"] == run_id
    assert api.get(
        "/v1/privacy/people/Nadia%20Karim/export",
        headers={"X-Workspace-ID": "other"},
    ).json()["research_runs"] == []

    deleted = api.delete(
        "/v1/privacy/people/Nadia%20Karim",
        headers={"X-Workspace-ID": "acme"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["research_runs"] == 1
    assert api.get(
        f"/v1/research/runs/{run_id}", headers={"X-Workspace-ID": "acme"}
    ).status_code == 404


def test_production_auth_scopes_workspace(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        dry_run=True,
        require_auth=True,
        api_keys="secret-acme=acme",
        admin_api_keys="secret-acme",
    )
    api = TestClient(create_app(settings))
    payload = {"person": "Nadia Karim", "objective": "Obtenir un rendez-vous", "dry_run": True}
    assert api.post("/v1/research/runs", json=payload).status_code == 401
    headers = {"Authorization": "Bearer secret-acme", "X-Workspace-ID": "acme"}
    response = api.post("/v1/research/runs", json=payload, headers=headers)
    assert response.status_code == 202
    mismatch = api.post(
        "/v1/research/runs", json=payload, headers={**headers, "X-Workspace-ID": "other"}
    )
    assert mismatch.status_code == 403

    created = api.post("/v1/admin/api-keys", json={"name": "frontend"}, headers=headers)
    assert created.status_code == 201
    generated = created.json()
    assert generated["key"].startswith("rp_")
    generated_headers = {
        "Authorization": f"Bearer {generated['key']}",
        "X-Workspace-ID": "acme",
    }
    assert api.get("/v1/usage/quota", headers=generated_headers).status_code == 200
    rotated = api.post(
        f"/v1/admin/api-keys/{generated['key_id']}/rotate", headers=headers
    )
    assert rotated.status_code == 200
    assert api.get("/v1/usage/quota", headers=generated_headers).status_code == 401
    replacement_headers = {
        "Authorization": f"Bearer {rotated.json()['key']}",
        "X-Workspace-ID": "acme",
    }
    assert api.get("/v1/usage/quota", headers=replacement_headers).status_code == 200

    reader = api.post(
        "/v1/admin/api-keys",
        json={"name": "report-reader", "role": "reader"},
        headers=headers,
    )
    assert reader.status_code == 201
    reader_headers = {
        "Authorization": f"Bearer {reader.json()['key']}",
        "X-Workspace-ID": "acme",
    }
    assert api.get("/v1/usage/quota", headers=reader_headers).status_code == 200
    assert api.post("/v1/research/runs", json=payload, headers=reader_headers).status_code == 403

    generated_admin = api.post(
        "/v1/admin/api-keys",
        json={"name": "workspace-admin", "role": "admin"},
        headers=headers,
    )
    assert generated_admin.status_code == 201
    generated_admin_headers = {
        "Authorization": f"Bearer {generated_admin.json()['key']}",
        "X-Workspace-ID": "acme",
    }
    assert api.post(
        "/v1/admin/api-keys", json={"name": "created-by-admin"}, headers=generated_admin_headers
    ).status_code == 201
