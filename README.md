# road-reachpath

ReachPath est un SaaS de prospection relationnelle : il combine recherche
multi-source, analyse des personnes et entreprises, chemins de mise en relation
et génération de rapports sourcés.

## État du projet

La release R0 contient le socle FastAPI, les runs persistants et multi-workspace,
l'orchestrateur LangGraph, les clients HTTP vers SearchSwarm/ARGUS/ReportForge,
un worker durable, une CLI et un mode `dry_run` local.
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
  --objective "Obtenir un rendez-vous commercial" \
  --workspace-id local
```

La CLI attend par défaut la fin du dossier et affiche le résultat. Utiliser
`--no-wait` pour obtenir uniquement le `run_id`, ou `--live` pour désactiver le
mode de simulation.

Le mode local ne consulte aucun service externe. Pour activer les appels réels,
configurer `REACHPATH_DRY_RUN=false`, les URL des trois services et leurs clés
d'API. Les données doivent rester publiques, professionnelles ou explicitement
autorisées.

En production, `REACHPATH_REQUIRE_AUTH=true` active les clés API ReachPath. Le
format est `token=workspace` (plusieurs entrées séparées par des virgules). Le
token peut être envoyé avec `Authorization: Bearer <token>` ou `X-API-Key` ; un
workspace différent de celui associé à la clé est refusé.

## Worker et Docker

En local, l'API exécute les tâches en arrière-plan. En production, désactiver
`REACHPATH_AUTO_EXECUTE` et lancer un worker séparé :

```bash
cp .env.example .env
# renseigner le mot de passe PostgreSQL et les trois clés de service
make compose-config
make compose-up
```

Le compose démarre PostgreSQL, l'API sur `127.0.0.1:8020` et un worker. La base
n'est jamais publiée directement. Caddy ou Nginx doit rester le seul point
d'entrée Internet.
