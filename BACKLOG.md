# ReachPath — backlog produit complet

## Vision

ReachPath aide un utilisateur à identifier une personne professionnelle, comprendre son contexte, trouver des chemins de mise en relation autorisés et produire un plan de prospection sourcé. Le produit utilise uniquement des données publiques, professionnelles ou explicitement importées par l'organisation.

## Critères de livraison

- Chaque affirmation importante possède une source, une date et un niveau de confiance.
- Une recherche longue est asynchrone, reprenable, annulable et idempotente.
- Les données et les clés sont isolées par organisation.
- Aucun contact privé ou contournement d'accès n'est recherché.
- Le parcours complet est testable en CLI avant l'interface web.
- Les trois services existants restent consommables par API versionnée.

## P0 — socle produit et backend

- [x] Écrire le contrat de recherche : cible, contexte, objectif, contraintes et limites.
- [x] Définir les états d'une recherche : `queued`, `running`, `needs_clarification`, `completed`, `failed`, `cancelled`.
- [x] Créer le backend FastAPI et sa configuration par environnement.
- [x] Ajouter PostgreSQL, migrations et séparation par organisation.
- [x] Créer les modèles R0 de `ResearchRun`, `Evidence`, `RelationshipPath` et `ReportArtifact` ; les entités commerciales restantes suivent avec l'authentification.
- [x] Ajouter les endpoints de création, suivi, annulation et readiness d'une recherche.
- [x] Ajouter idempotency keys, scoping workspace et erreurs HTTP bornées.
- [x] Créer les clients HTTP typés de SearchSwarm, ARGUS et ReportForge.
- [x] Créer l'orchestrateur LangGraph avec état persistant du run.
- [x] Implémenter le parcours CLI réel de bout en bout.
- [x] Ajouter tests unitaires, contrats HTTP et un scénario E2E local avec services simulés.

## P1 — intelligence de prospection

- [x] Résoudre les homonymes et demander une clarification si nécessaire.
- [ ] Rechercher personne, entreprise, dirigeants, collègues et signaux professionnels.
- [x] Fusionner les données CRM autorisées avec le graphe ARGUS.
- [x] Calculer les chemins relationnels de niveaux 1, 2 et 3 via ARGUS lorsque `source_person` est fourni.
- [x] Classer les intermédiaires selon proximité, confiance, pertinence et fraîcheur via le score ARGUS.
- [x] Identifier les points de contact professionnels disponibles et leur provenance.
- [ ] Détecter contradictions, doublons et données obsolètes.
- [x] Générer plusieurs stratégies : introduction chaude, approche directe et approche contenu/événement.
- [x] Générer des e-mails et messages personnalisables, sans envoi automatique.
- [x] Produire un dossier avec preuves, limites et recommandations de prospection versionnées.

## P1 — sécurité, conformité et exploitation

- [x] Authentification, workspace, rôles de clé (`reader`, `operator`, `admin`) et permissions de mutation.
- [x] Chiffrement des tokens CRM OAuth au repos ; rotation des clés de service reste à livrer.
- [x] Journal d'audit et export des traitements par workspace.
- [x] Suppression et export des recherches/contacts d'une personne par workspace ; opt-out externe reste à synchroniser avec ARGUS.
- [x] Quotas par organisation, estimation des coûts et arrêt sur budget.
- [x] Timeouts, retries bornés et circuit breakers sur les appels interservices ; rate limiting distribué reste à livrer.
- [x] Logs structurés, métriques, traces et corrélation interservices.
- [x] Rétention configurable des runs terminés via endpoint admin ; suppression des artefacts temporaires externes reste à livrer.

## P1 — intégrations et API commerciale

- [x] Import CSV CRM autorisé documenté, validé et projeté vers ARGUS.
- [x] Connecteur OAuth HubSpot (connexion, refresh, révocation et sync read-only).
- [x] Connecteur OAuth Salesforce (connexion, refresh, révocation et sync read-only).
- [x] Connecteur OAuth Pipedrive (connexion, refresh, révocation et sync read-only).
- [x] Synchronisation CRM read-only à la demande et mapping vers les contacts autorisés.
- [ ] Synchronisation périodique et webhooks entrants.
- [x] API publique versionnée, clés d'API et scopes RBAC de base.
- [x] Webhooks ReachPath signés pour fin de recherche ; webhooks entrants CRM restent à livrer.
- [ ] SDK Python et TypeScript générés depuis OpenAPI.

## P2 — frontend web

- [ ] Authentification et onboarding organisation.
- [x] Formulaire de nouvelle recherche initiale.
- [x] Clarification guidée avec reprise d'une recherche `needs_clarification` via l'API.
- [x] Vue temps réel de progression de la recherche.
- [x] Vue dossier personne/entreprise avec preuves et niveaux de confiance.
- [x] Vue relationnelle avec chemins classés par profondeur et confiance.
- [ ] Éditeur de stratégie et de messages.
- [ ] Export et partage sécurisé du rapport.
- [x] Historique paginé et récupération séparée du dossier, de la stratégie et du rapport.
- [ ] Gestion des intégrations CRM et des permissions.

## P2 — monétisation et qualité

- [ ] Plans, crédits, facturation et limites par fonctionnalité.
- [ ] Stripe ou fournisseur équivalent en environnement de test puis production.
- [x] Tableau de coûts réel par recherche et ventilation SearchSwarm/ARGUS/ReportForge.
- [ ] Jeux de données anonymisés et benchmarks de précision.
- [ ] Tests de charge, reprise après panne et tests de sécurité.
- [ ] Documentation utilisateur, API, exploitation et support.
- [x] Packaging Docker/Compose VPS, reverse proxy Caddy et sauvegarde PostgreSQL ; rollback applicatif reste à livrer.
- [x] CI backend/frontend et migrations contrôlées ; procédure de rollback applicatif reste à formaliser.
- [ ] Préparation commerciale : DPA, politique de confidentialité, CGU et limites d'usage.

## Découpage des premières releases

### R0 — fondation vérifiable

Backend, modèles, clients de services, orchestration simulée, CLI et tests E2E.

### R1 — recherche exploitable

Appels réels aux trois services, clarification, graphe relationnel, preuves et rapport.

### R2 — produit web

Frontend, comptes, organisations, historique et partage sécurisé.

### R3 — produit commercial

CRM OAuth, quotas, facturation, observabilité, sécurité et déploiement production.

## Hors périmètre permanent

- Scraping de zones privées ou contournement de protections.
- Collecte de données personnelles non nécessaires à l'objectif professionnel.
- Envoi automatique de messages sans validation humaine.
- Promesse d'une relation réelle lorsque seules des inférences sont disponibles.
