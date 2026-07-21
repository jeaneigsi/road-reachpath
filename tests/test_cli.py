import json

from typer.testing import CliRunner

from reachpath import cli


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[str, str]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, path: str, json: dict) -> FakeResponse:
        self.calls.append(("POST", path))
        return FakeResponse({"run_id": "run-1", "status": "queued", "workspace_id": "acme"})

    def get(self, path: str) -> FakeResponse:
        self.calls.append(("GET", path))
        return FakeResponse(
            {
                "run_id": "run-1",
                "status": "completed",
                "workspace_id": "acme",
                "result": {"report": {"title": "Dossier"}},
            }
        )


def test_cli_waits_for_final_dossier(monkeypatch) -> None:
    monkeypatch.setattr(cli.httpx, "Client", FakeClient)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    result = CliRunner().invoke(
        cli.app,
        [
            "research",
            "--person",
            "Nadia Karim",
            "--objective",
            "Obtenir un rendez-vous",
            "--workspace-id",
            "acme",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"
