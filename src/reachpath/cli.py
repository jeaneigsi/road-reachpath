import json

import httpx
import typer

app = typer.Typer(help="ReachPath CLI")


@app.command()
def research(
    person: str = typer.Option(..., help="Nom de la personne cible"),
    objective: str = typer.Option(..., help="Objectif de prospection"),
    company: str | None = typer.Option(None),
    api_url: str = typer.Option("http://127.0.0.1:8020"),
    dry_run: bool = typer.Option(True, help="Utiliser la simulation locale"),
) -> None:
    payload = {"person": person, "company": company, "objective": objective, "dry_run": dry_run}
    response = httpx.post(f"{api_url.rstrip('/')}/v1/research/runs", json=payload, timeout=30)
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2, ensure_ascii=False))


def main() -> None:
    app()
