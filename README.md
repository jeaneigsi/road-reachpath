# road-reachpath

ReachPath est un SaaS de prospection relationnelle : il combine recherche
multi-source, analyse des personnes et entreprises, chemins de mise en relation
et génération de rapports sourcés.

## État du projet

La release R0 contient le socle FastAPI, l'orchestrateur LangGraph, les clients
HTTP vers SearchSwarm/ARGUS/ReportForge, une CLI et un mode `dry_run` local.
Le backlog complet se trouve dans [`BACKLOG.md`](BACKLOG.md).

## Démarrage local

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn reachpath.api:app --app-dir src --port 8020
```

Dans un autre terminal :

```bash
. .venv/bin/activate
reachpath research \
  --person "Nadia Karim" \
  --objective "Obtenir un rendez-vous commercial"
```

Le mode local ne consulte aucun service externe. Pour activer les appels réels,
configurer `REACHPATH_DRY_RUN=false`, les URL des trois services et leurs clés
d'API. Les données doivent rester publiques, professionnelles ou explicitement
autorisées.
