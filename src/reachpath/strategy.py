from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _target(dossier: dict[str, Any], request: dict[str, Any]) -> tuple[str, str | None, str | None]:
    subject = dossier.get("subject") or dossier.get("identity") or {}
    if not isinstance(subject, dict):
        subject = {}
    name = str(subject.get("name") or request["person"])
    company = subject.get("company") or request.get("company")
    title = subject.get("headline") or subject.get("title") or subject.get("job_title")
    return name, str(company) if company else None, str(title) if title else None


def generate_strategies(request: dict[str, Any], dossier: dict[str, Any]) -> dict[str, Any]:
    """Create safe, editable outreach hypotheses from verified dossier fields."""
    name, company, title = _target(dossier, request)
    relationships = dossier.get("relationships") or dossier.get("relationship_paths") or []
    evidence = dossier.get("evidence") or []
    contact_points = dossier.get("contact_points") or []
    company_label = f" chez {company}" if company else ""
    title_label = f" ({title})" if title else ""
    has_warm_path = bool(relationships)
    limitations = list(dossier.get("open_questions") or dossier.get("limitations") or [])
    if not relationships:
        limitations.append("Aucun chemin d'introduction confirmé dans les données disponibles.")
    if not contact_points:
        limitations.append("Aucun point de contact professionnel confirmé dans le dossier.")
    scenarios = [
        {
            "id": "warm-introduction",
            "label": "Introduction par une relation commune",
            "channel": "introduction",
            "priority": 1 if has_warm_path else 3,
            "premise": "Utiliser une relation professionnelle déjà autorisée et vérifiable."
            if has_warm_path
            else "Scénario à activer uniquement si une relation commune est confirmée.",
            "why_fit": f"Relier l'objectif « {request['objective']} » au contexte professionnel de {name}{company_label}.",
            "opening_message": f"Bonjour, pourriez-vous me présenter à {name}{title_label} ? Je souhaite échanger au sujet de {request['objective'].lower()}.",
            "next_step": "Demander une introduction courte, contextualisée et facilement transférable.",
            "requires_validation": not has_warm_path,
        },
        {
            "id": "direct-relevance",
            "label": "Approche directe par pertinence métier",
            "channel": "email_or_linkedin",
            "priority": 2,
            "premise": "Commencer par un problème professionnel observable, sans prétendre connaître un besoin privé.",
            "why_fit": f"Proposer un échange limité sur {request['objective'].lower()}, avec une hypothèse explicitement révisable.",
            "opening_message": f"Bonjour {name}, je travaille sur un sujet lié à {request['objective'].lower()}. Votre parcours{company_label} m’a semblé pertinent ; accepteriez-vous un échange de 15 minutes pour vérifier si le sujet vous concerne ?",
            "next_step": "Personnaliser une seule phrase à partir d'une preuve du dossier, puis demander un créneau court.",
            "requires_validation": not bool(evidence),
        },
        {
            "id": "insight-first",
            "label": "Approche par ressource ou insight",
            "channel": "email_or_content",
            "priority": 3,
            "premise": "Offrir d'abord une ressource utile et laisser la personne choisir la suite.",
            "why_fit": "Réduire la pression commerciale et tester l'intérêt avant de proposer une réunion.",
            "opening_message": f"Bonjour {name}, je vous partage une ressource courte sur {request['objective'].lower()}. Si le sujet est d'actualité pour vous{company_label}, je serais heureux de comparer nos observations.",
            "next_step": "Envoyer une ressource réellement pertinente, puis relancer une seule fois avec une question précise.",
            "requires_validation": True,
        },
    ]
    return {
        "schema_version": "1.0",
        "strategy_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {"name": name, "company": company, "title": title},
        "scenarios": scenarios,
        "contact_points": contact_points,
        "evidence_count": len(evidence),
        "limitations": sorted(set(limitations)),
        "human_review_required": True,
        "policy": "Professional, public or explicitly authorized data only; no automatic outreach.",
    }
