import json
import time

import httpx
import typer

from .worker import worker_app

app = typer.Typer(help="ReachPath CLI")
app.add_typer(worker_app, name="worker")


@app.command()
def research(
    person: str = typer.Option(..., help="Nom de la personne cible"),
    objective: str = typer.Option(..., help="Objectif de prospection"),
    company: str | None = typer.Option(None),
    api_url: str = typer.Option("http://127.0.0.1:8020"),
    workspace_id: str = typer.Option("local", help="Organisation ReachPath"),
    api_key: str | None = typer.Option(None, help="Clé API ReachPath (Bearer)"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Simuler ou appeler les services"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Attendre le dossier final"),
    timeout_seconds: int = typer.Option(300, min=1, max=86_400),
) -> None:
    payload = {"person": person, "company": company, "objective": objective, "dry_run": dry_run}
    headers = {"X-Workspace-ID": workspace_id}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(base_url=api_url.rstrip("/"), headers=headers, timeout=30) as client:
        response = client.post("/v1/research/runs", json=payload)
        response.raise_for_status()
        body = response.json()
        if wait and body["status"] not in {"completed", "failed", "cancelled"}:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(1)
                response = client.get(f"/v1/research/runs/{body['run_id']}")
                response.raise_for_status()
                body = response.json()
                if body["status"] in {"completed", "failed", "cancelled"}:
                    break
            else:
                raise typer.BadParameter("La recherche n'est pas terminée dans le délai demandé")
        typer.echo(json.dumps(body, indent=2, ensure_ascii=False))


def main() -> None:
    app()
