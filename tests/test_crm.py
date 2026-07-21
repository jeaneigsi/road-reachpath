from fastapi.testclient import TestClient

from reachpath.api import create_app
from reachpath.crm import build_argus_bundle, parse_csv
from reachpath.settings import Settings


def test_parse_and_project_authorized_crm_csv() -> None:
    contacts = parse_csv(
        b"contact_id,full_name,email,company_name,job_title,relationship_strength\n"
        b"crm-1,Nadia Karim,nadia@example.org,Example Labs,CTO,1.4\n"
    )
    assert contacts[0].relationship_strength == 1
    bundle = build_argus_bundle(contacts, "acme", "owner-1", "Jean Morel")
    assert len(bundle["people"]) == 2
    assert bundle["contacts"][0]["status"] == "authorized"
    assert bundle["relationships"][0]["relationship_type"] == "professional"


def test_crm_import_is_workspace_scoped(tmp_path) -> None:
    api = TestClient(
        create_app(Settings(database_url=f"sqlite:///{tmp_path / 'crm.db'}", dry_run=True))
    )
    csv_content = (
        "contact_id,full_name,email,company_name,job_title\n"
        "crm-1,Nadia Karim,nadia@example.org,Example Labs,CTO\n"
    )
    response = api.post(
        "/v1/connectors/crm/import",
        files={"file": ("contacts.csv", csv_content, "text/csv")},
        data={"source_id": "acme", "owner_person_id": "me", "owner_name": "Jean Morel"},
        headers={"X-Workspace-ID": "workspace-a"},
    )
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert api.get(
        "/v1/connectors/crm/contacts", headers={"X-Workspace-ID": "workspace-a"}
    ).json()["items"][0]["full_name"] == "Nadia Karim"
    assert api.get(
        "/v1/connectors/crm/contacts", headers={"X-Workspace-ID": "workspace-b"}
    ).json()["items"] == []


def test_crm_import_rejects_missing_required_column(tmp_path) -> None:
    api = TestClient(
        create_app(Settings(database_url=f"sqlite:///{tmp_path / 'invalid-crm.db'}", dry_run=True))
    )
    response = api.post(
        "/v1/connectors/crm/import",
        files={"file": ("contacts.csv", "email,email2\na@example.org,b@example.org\n", "text/csv")},
        data={"source_id": "acme", "owner_person_id": "me", "owner_name": "Jean Morel"},
    )
    assert response.status_code == 400
