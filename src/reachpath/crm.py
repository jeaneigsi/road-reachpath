from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Any

from .domain import CrmContact

REQUIRED_COLUMNS = {"full_name"}


def parse_csv(content: bytes, *, max_bytes: int = 5_000_000, max_rows: int = 2_000) -> list[CrmContact]:
    if len(content) > max_bytes:
        raise ValueError(f"CRM CSV exceeds the {max_bytes} byte limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CRM CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"Missing CRM columns: {sorted(missing)}")
    contacts: list[CrmContact] = []
    for row_number, row in enumerate(reader, start=2):
        if row_number > max_rows + 1:
            raise ValueError(f"CRM CSV exceeds the {max_rows} row limit")
        full_name = (row.get("full_name") or "").strip()
        if not full_name:
            continue
        raw_strength = (row.get("relationship_strength") or "").strip()
        try:
            strength = float(raw_strength) if raw_strength else 0.7
        except ValueError as exc:
            raise ValueError(f"Invalid relationship_strength on row {row_number}") from exc
        contacts.append(
            CrmContact(
                contact_id=(row.get("contact_id") or "").strip() or None,
                full_name=full_name,
                email=(row.get("email") or "").strip() or None,
                company_name=(row.get("company_name") or "").strip() or None,
                company_domain=(row.get("company_domain") or "").strip() or None,
                job_title=(row.get("job_title") or "").strip() or None,
                location=(row.get("location") or "").strip() or None,
                relationship_strength=min(1.0, max(0.0, strength)),
            )
        )
    return contacts


def stable_id(prefix: str, *values: str) -> str:
    raw = "|".join(value.strip().casefold() for value in values)
    return f"{prefix}-{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def build_argus_bundle(
    contacts: list[CrmContact], source_id: str, owner_person_id: str, owner_name: str
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    evidence: list[dict[str, Any]] = []
    people = [{"id": owner_person_id, "canonical_name": owner_name, "aliases": [], "evidence_ids": []}]
    companies: dict[str, dict[str, Any]] = {}
    employments: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    output_contacts: list[dict[str, Any]] = []
    for row_number, contact in enumerate(contacts, start=2):
        person_id = stable_id("crm-person", source_id, contact.contact_id or contact.full_name)
        evidence_id = stable_id("crm-evidence", source_id, str(row_number))
        evidence.append(
            {
                "id": evidence_id,
                "source_url": f"urn:reachpath:authorized-crm:{source_id}:row:{row_number}",
                "source_title": f"Authorized CRM export {source_id}",
                "source_type": "authorized_crm",
                "retrieved_at": now,
                "quote": f"Authorized professional record for {contact.full_name}.",
                "confidence": 0.9,
                "purpose": "b2b_sales",
                "legal_basis": "legitimate_interest",
                "consent_status": "authorized",
            }
        )
        people.append(
            {
                "id": person_id,
                "canonical_name": contact.full_name,
                "aliases": [],
                "headline": contact.job_title,
                "location": contact.location,
                "evidence_ids": [evidence_id],
            }
        )
        relationships.append(
            {
                "id": stable_id("crm-rel", owner_person_id, person_id),
                "source_person_id": owner_person_id,
                "target_person_id": person_id,
                "relationship_type": "professional",
                "confidence": 0.9,
                "strength": contact.relationship_strength,
                "evidence_ids": [evidence_id],
            }
        )
        if contact.email:
            output_contacts.append(
                {
                    "id": stable_id("crm-contact", person_id, contact.email),
                    "person_id": person_id,
                    "kind": "email",
                    "value": contact.email,
                    "status": "authorized",
                    "confidence": 0.9,
                    "evidence_ids": [evidence_id],
                }
            )
        if contact.company_name:
            company_id = stable_id("crm-company", contact.company_name)
            companies.setdefault(
                company_id,
                {
                    "id": company_id,
                    "legal_name": contact.company_name,
                    "aliases": [],
                    "domains": [contact.company_domain] if contact.company_domain else [],
                    "evidence_ids": [evidence_id],
                },
            )
            if contact.job_title:
                employments.append(
                    {
                        "id": stable_id("crm-job", person_id, company_id, contact.job_title),
                        "person_id": person_id,
                        "company_id": company_id,
                        "title": contact.job_title,
                        "state": "uncertain",
                        "confidence": 0.75,
                        "evidence_ids": [evidence_id],
                    }
                )
    return {
        "evidence": evidence,
        "people": people,
        "companies": list(companies.values()),
        "employments": employments,
        "relationships": relationships,
        "contacts": output_contacts,
    }
