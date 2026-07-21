from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
import httpx

from fastapi.testclient import TestClient

from reachpath.api import create_app
from reachpath.crm_oauth import CrmOAuthClient, OAuthToken, TokenCipher
from reachpath.domain import CrmContact
from reachpath.settings import Settings


def oauth_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'oauth.db'}",
        oauth_encryption_key=Fernet.generate_key().decode(),
        hubspot_client_id="hubspot-client",
        hubspot_client_secret="hubspot-secret",
        hubspot_redirect_uri="https://reachpath.example.com/oauth/hubspot/callback",
    )
    application = create_app(settings)
    return application, TestClient(application)


def test_oauth_start_is_scoped_and_contains_provider_parameters(tmp_path) -> None:
    _application, api = oauth_client(tmp_path)
    response = api.get(
        "/v1/connectors/crm/hubspot/oauth/start",
        headers={"X-Workspace-ID": "acme"},
    )
    assert response.status_code == 200
    body = response.json()
    query = parse_qs(urlparse(body["authorization_url"]).query)
    assert query["client_id"] == ["hubspot-client"]
    assert query["scope"] == ["crm.objects.contacts.read"]
    assert query["state"][0]
    assert "hubspot-secret" not in body["authorization_url"]


async def test_oauth_exchange_uses_form_and_parses_provider_metadata(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'exchange.db'}",
        oauth_encryption_key=Fernet.generate_key().decode(),
        hubspot_client_id="client",
        hubspot_client_secret="secret",
        hubspot_redirect_uri="https://reachpath.example.com/callback",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.hubapi.com/oauth/v3/token"
        assert b"grant_type=authorization_code" in request.content
        assert b"code=one-time-code" in request.content
        return httpx.Response(
            200,
            json={
                "access_token": "access-live",
                "refresh_token": "refresh-live",
                "expires_in": 1800,
                "hub_id": 987,
                "scope": ["crm.objects.contacts.read"],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        token = await CrmOAuthClient(settings, http_client=http_client).exchange_code(
            "hubspot", "one-time-code"
        )
    assert token.access_token == "access-live"
    assert token.refresh_token == "refresh-live"
    assert token.external_account_id == "987"
    assert token.scope == "crm.objects.contacts.read"


async def test_hubspot_contacts_are_mapped_to_authorized_contact_model(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'contacts.db'}",
        oauth_encryption_key=Fernet.generate_key().decode(),
        hubspot_client_id="client",
        hubspot_client_secret="secret",
        hubspot_redirect_uri="https://reachpath.example.com/callback",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/crm/objects/2026-03/contacts"
        assert request.headers["Authorization"] == "Bearer access-live"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "42",
                        "properties": {
                            "firstname": "Ada",
                            "lastname": "Lovelace",
                            "email": "ada@example.com",
                            "company": "Analytical Engines",
                            "jobtitle": "Founder",
                            "city": "London",
                            "country": "GB",
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        contacts = await CrmOAuthClient(settings, http_client=http_client).fetch_contacts(
            "hubspot", "access-live"
        )
    assert contacts[0].model_dump(exclude_none=True) == {
        "contact_id": "42",
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "company_name": "Analytical Engines",
        "job_title": "Founder",
        "location": "London / GB",
        "relationship_strength": 0.7,
    }


def test_oauth_callback_encrypts_tokens_and_is_one_time(tmp_path, monkeypatch) -> None:
    application, api = oauth_client(tmp_path)
    start = api.get("/v1/connectors/crm/hubspot/oauth/start", headers={"X-Workspace-ID": "acme"})
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    async def exchange(_provider: str, _code: str) -> OAuthToken:
        return OAuthToken(
            access_token="access-live",
            refresh_token="refresh-live",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            external_account_id="123",
            api_domain="https://api.hubapi.com",
            scope="crm.objects.contacts.read",
        )

    monkeypatch.setattr(application.state.crm_oauth, "exchange_code", exchange)
    callback = api.get(
        "/v1/connectors/crm/hubspot/oauth/callback",
        params={"state": state, "code": "one-time-code"},
    )
    assert callback.status_code == 200
    connection_id = callback.json()["connection_id"]
    listed = api.get("/v1/connectors/crm/connections", headers={"X-Workspace-ID": "acme"})
    assert listed.status_code == 200
    assert listed.json()[0]["connection_id"] == connection_id
    encrypted = application.state.store.get_crm_connection_secret("acme", connection_id)
    assert encrypted is not None
    assert encrypted["access_token_enc"] != "access-live"
    assert TokenCipher(application.state.settings.oauth_encryption_key).decrypt(
        encrypted["access_token_enc"]
    ) == "access-live"

    async def fetch_contacts(_provider: str, _access_token: str, *, api_domain=None, limit=200):
        assert api_domain == "https://api.hubapi.com"
        assert limit == 200
        return [CrmContact(contact_id="contact-1", full_name="Contact One", email="one@example.com")]

    monkeypatch.setattr(application.state.crm_oauth, "fetch_contacts", fetch_contacts)
    synced = api.post(
        f"/v1/connectors/crm/connections/{connection_id}/sync",
        headers={"X-Workspace-ID": "acme"},
    )
    assert synced.status_code == 200
    assert synced.json()["imported"] == 1
    contacts = api.get(
        "/v1/connectors/crm/contacts", headers={"X-Workspace-ID": "acme"}
    ).json()["items"]
    assert contacts[0]["full_name"] == "Contact One"
    replay = api.get(
        "/v1/connectors/crm/hubspot/oauth/callback",
        params={"state": state, "code": "one-time-code"},
    )
    assert replay.status_code == 400


def test_oauth_connection_can_be_refreshed_and_disconnected(tmp_path, monkeypatch) -> None:
    application, api = oauth_client(tmp_path)
    start = api.get("/v1/connectors/crm/hubspot/oauth/start")
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    async def exchange(_provider: str, _code: str) -> OAuthToken:
        return OAuthToken("access-1", "refresh-1", None, None, None, None)

    async def refresh(_provider: str, _refresh: str) -> OAuthToken:
        return OAuthToken("access-2", "refresh-2", None, None, None, None)

    monkeypatch.setattr(application.state.crm_oauth, "exchange_code", exchange)
    connection_id = api.get(
        "/v1/connectors/crm/hubspot/oauth/callback",
        params={"state": state, "code": "code"},
    ).json()["connection_id"]
    monkeypatch.setattr(application.state.crm_oauth, "refresh", refresh)
    refreshed = api.post(f"/v1/connectors/crm/connections/{connection_id}/refresh")
    assert refreshed.status_code == 200
    assert api.delete(f"/v1/connectors/crm/connections/{connection_id}").json() == {"deleted": True}
    assert api.get("/v1/connectors/crm/connections").json() == []
