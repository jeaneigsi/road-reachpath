from __future__ import annotations

import asyncio

import typer

from .api import _execute, app

worker_app = typer.Typer(help="ReachPath durable research worker", invoke_without_command=True)


async def drain_once(application=app) -> int:
    jobs = application.state.store.queued()
    for workspace_id, run_id in jobs:
        await _execute(application, run_id, workspace_id)
    return len(jobs)


async def run_forever(poll_interval: float = 1.0, application=app) -> None:
    while True:
        await drain_once(application)
        await asyncio.sleep(poll_interval)


@worker_app.callback()
def run_worker_command(
    once: bool = typer.Option(False, help="Traiter la file disponible puis quitter"),
    poll_interval: float = typer.Option(1.0, min=0.1, max=60),
) -> None:
    if once:
        asyncio.run(drain_once())
    else:
        asyncio.run(run_forever(poll_interval))


def main() -> None:
    worker_app()
