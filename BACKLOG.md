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
- [ ] Ajouter PostgreSQL, migrations et séparation par organisation.
- [x] Créer les modèles R0 de `ResearchRun`, `Evidence`, `RelationshipPath` et `ReportArtifact` ; les entités commerciales restantes suivent avec l'authentification.
- [x] Ajouter les endpoints de création, suivi, annulation et readiness d'une recherche.
- [x] Ajouter idempotency keys, scoping workspace et erreurs HTTP bornées.
- [x] Créer les clients HTTP typés de SearchSwarm, ARGUS et ReportForge.
- [x] Créer l'orchestrateur LangGraph avec état persistant du run.
- [x] Implémenter le parcours CLI réel de bout en bout.
- [x] Ajouter tests unitaires, contrats HTTP et un scénario E2E local avec services simulés.

## P1 — intelligence de prospection

- [ ] Résoudre les homonymes et demander une clarification si nécessaire.
- [ ] Rechercher personne, entreprise, dirigeants, collègues et signaux professionnels.
- [ ] Fusionner les données CRM autorisées avec le graphe ARGUS.
- [ ] Calculer les chemins relationnels de niveaux 1, 2 et 3.
- [ ] Classer les intermédiaires selon proximité, confiance, pertinence et fraîcheur.
- [ ] Identifier les points de contact professionnels disponibles et leur provenance.
- [ ] Détecter contradictions, doublons et données obsolètes.
- [ ] Générer plusieurs stratégies : introduction chaude, approche directe et approche contenu/événement.
- [ ] Générer des e-mails et messages personnalisables, sans envoi automatique.
- [ ] Produire un dossier avec résumé, graphe, preuves, limites et recommandations.

## P1 — sécurité, conformité et exploitation

- [ ] Authentification, organisations, rôles et permissions.
- [ ] Chiffrement des secrets et rotation des clés de service.
- [ ] Journal d'audit et export des traitements.
- [ ] Opt-out, suppression et export des données d'une personne.
- [ ] Quotas par organisation, estimation des coûts et arrêt sur budget.
- [ ] Rate limiting, timeouts, retries bornés et circuit breakers.
- [ ] Logs structurés, métriques, traces et corrélation interservices.
- [ ] Rétention configurable et suppression des artefacts temporaires.

## P1 — intégrations et API commerciale

- [x] Import CSV CRM autorisé documenté, validé et projeté vers ARGUS.
- [ ] Connecteur OAuth HubSpot.
- [ ] Connecteur OAuth Salesforce.
- [ ] Connecteur OAuth Pipedrive.
- [ ] Synchronisation périodique et webhooks entrants.
- [ ] API publique versionnée, clés d'API et scopes.
- [ ] Webhooks ReachPath pour fin de recherche et rapport disponible.
- [ ] SDK Python et TypeScript générés depuis OpenAPI.

## P2 — frontend web

- [ ] Authentification et onboarding organisation.
- [ ] Formulaire de nouvelle recherche avec clarification guidée.
- [ ] Vue temps réel de progression et consommation du budget.
- [ ] Vue dossier personne/entreprise avec preuves et niveaux de confiance.
- [ ] Carte des relations et filtres par profondeur.
- [ ] Éditeur de stratégie et de messages.
- [ ] Export et partage sécurisé du rapport.
- [ ] Historique, recherche et archivage des dossiers.
- [ ] Gestion des intégrations CRM et des permissions.

## P2 — monétisation et qualité

- [ ] Plans, crédits, facturation et limites par fonctionnalité.
- [ ] Stripe ou fournisseur équivalent en environnement de test puis production.
- [ ] Tableau de coûts réel par recherche et par connecteur.
- [ ] Jeux de données anonymisés et benchmarks de précision.
- [ ] Tests de charge, reprise après panne et tests de sécurité.
- [ ] Documentation utilisateur, API, exploitation et support.
- [ ] Déploiement Docker/Caddy sur VPS avec sauvegardes et rollback.
- [ ] CI/CD, migrations contrôlées et procédure de release.
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
