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
  --source-person "Alex Martin" \
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

Les clés dédiées peuvent ensuite être gérées par un bootstrap admin configuré
dans `REACHPATH_ADMIN_API_KEYS` :

- `POST /v1/admin/api-keys` — créer une clé ; le secret n’est retourné qu’une fois ;
- `POST /v1/admin/api-keys/{key_id}/rotate` — révoquer et remplacer une clé ;
- `DELETE /v1/admin/api-keys/{key_id}` — révoquer une clé.

Une clé persistante porte aussi un rôle : `reader` (lecture), `operator`
(recherche, clarification, annulation et import CRM) ou `admin` (gestion des
clés). Exemple :

```json
{"name": "sales-console", "role": "operator"}
```

Les clés `reader` restent limitées aux endpoints de consultation et de quota.

## Import CRM autorisé

Le backend accepte un export CSV professionnel sur
`POST /v1/connectors/crm/import` en multipart, avec les champs
`source_id`, `owner_person_id`, `owner_name` et `file`. La colonne
`full_name` est obligatoire ; les autres colonnes suivent le format documenté
dans [l’exemple CRM](https://github.com/jeaneigsi/road-10K/blob/main/services/argus/backend/examples/crm_contacts.csv).
Les contacts sont stockés par workspace et projetés dans le graphe ARGUS avec
un statut `authorized`. La lecture se fait via
`GET /v1/connectors/crm/contacts`.

### Connexions CRM OAuth

ReachPath peut connecter un workspace à HubSpot, Salesforce ou Pipedrive. Les
tokens d'accès et de rafraîchissement sont chiffrés avec
`REACHPATH_OAUTH_ENCRYPTION_KEY` (clé Fernet fournie par le gestionnaire de
secrets du déploiement) et ne sont jamais retournés par l'API. Configurer les
identifiants et l'URL de callback du fournisseur dans `.env`, puis :

1. une clé `operator` appelle `GET /v1/connectors/crm/{provider}/oauth/start` ;
2. l'utilisateur autorise l'application chez le fournisseur ;
3. le fournisseur redirige vers l'URL de callback avec `code` et `state` ;
4. ReachPath échange le code, enregistre la connexion et permet le
   rafraîchissement via `POST /v1/connectors/crm/connections/{id}/refresh`.

Les connexions du workspace sont listées par
`GET /v1/connectors/crm/connections` et supprimées par
`DELETE /v1/connectors/crm/connections/{id}`. L'état OAuth est opaque, lié au
workspace, à usage unique et expire après `REACHPATH_OAUTH_STATE_TTL_SECONDS`.
Cette première tranche couvre l'autorisation et le stockage sûr ; la
synchronisation périodique des contacts et les webhooks restent une étape
distincte.

Après une recherche terminée, ReachPath expose aussi :

- `GET /v1/research/runs?limit=50`
- `GET /v1/research/runs/{run_id}/dossier`
- `GET /v1/research/runs/{run_id}/strategy`
- `GET /v1/research/runs/{run_id}/report`
- `GET /v1/usage/quota`
- `GET /v1/audit/events?limit=200`
- `GET /v1/audit/export`

Pour la conformité, un workspace peut exporter puis supprimer les données
ReachPath d'une personne :

- `GET /v1/privacy/people/{person_name}/export`
- `DELETE /v1/privacy/people/{person_name}`

Ces opérations sont limitées au workspace authentifié et inscrites dans le
journal d'audit. L'opt-out ARGUS devra être synchronisé séparément lors de la
prochaine intégration de gouvernance.

La stratégie contient trois scénarios éditables (introduction, pertinence
directe, insight d'abord), les formulations proposées et les limites qui
imposent une validation humaine.

Chaque run conserve aussi `usage` (agrégé) et `usage_breakdown` par connecteur
dans le résultat, afin de suivre les coûts réels plutôt qu'une estimation
globale.

Pour rechercher les chemins relationnels, fournir `--source-person` (ou
`source_person` dans l'API). ReachPath appelle alors ARGUS pour les chemins de
profondeur 1 à 3 et la stratégie de contact. Si ARGUS signale une identité
ambiguë, le run passe à `needs_clarification` et peut être relancé avec :

```http
POST /v1/research/runs/{run_id}/clarify
```

Le corps reprend une requête de recherche complète après ajout du contexte
manquant. Aucune prise de contact n'est envoyée automatiquement.

## Worker et Docker

En local, l'API exécute les tâches en arrière-plan. En production, désactiver
`REACHPATH_AUTO_EXECUTE` et lancer un worker séparé :

```bash
cp .env.example .env
# renseigner le mot de passe PostgreSQL et les trois clés de service
make compose-config
make compose-up
# sauvegarde PostgreSQL vers ./backups
make backup
```

Le compose démarre PostgreSQL, l'API sur `127.0.0.1:8020`, un worker, le
frontend et Caddy. La base, l'API et le frontend ne sont pas publiés directement
sur Internet ; Caddy est le seul point d'entrée public. Définir
`REACHPATH_DOMAIN` avec le domaine DNS du VPS pour activer HTTPS automatique.
La commande `make backup` crée un dump PostgreSQL horodaté et conserve les
quatorze derniers jours dans `REACHPATH_BACKUP_DIR`.

Les appels vers SearchSwarm, ARGUS et ReportForge utilisent des retries bornés
sur les erreurs transitoires (`429`, `5xx`, réseau). Les paramètres sont
`REACHPATH_SERVICE_MAX_RETRIES` et `REACHPATH_SERVICE_RETRY_BACKOFF_SECONDS`.

Chaque push sur `main` exécute la CI GitHub (`.github/workflows/ci.yml`) : tests
et lint Python, migrations Alembic et typecheck frontend Node 22.

## Interface web

Le frontend Next.js se trouve dans `frontend/`. Il utilise un proxy serveur
pour que la clé ReachPath ne soit jamais exposée au navigateur :

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Ouvrir `http://localhost:3000`. En local, laisser `REACHPATH_DRY_RUN=true` sur
l'API pour obtenir un dossier simulé sans dépendre des trois services externes.
En compose, renseigner `REACHPATH_FRONTEND_API_KEY` avec une clé du workspace
créée par l'endpoint admin, puis configurer `REACHPATH_CORS_ORIGINS` avec
l'origine publique du frontend.
