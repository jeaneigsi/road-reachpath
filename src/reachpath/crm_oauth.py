from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from base64 import b64encode
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .domain import CrmProvider
from .settings import Settings


@dataclass(frozen=True)
class ProviderConfig:
    provider: CrmProvider
    authorization_endpoint: str
    token_endpoint: str
    scopes: tuple[str, ...]
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    external_account_id: str | None
    api_domain: str | None
    scope: str | None


class TokenCipher:
    """Encrypt CRM tokens at rest; the key must be supplied by the deployment secret store."""

    def __init__(self, key: str | None) -> None:
        if not key:
            raise ValueError("REACHPATH_OAUTH_ENCRYPTION_KEY must be configured")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("REACHPATH_OAUTH_ENCRYPTION_KEY must be a Fernet key") from exc

    def encrypt(self, value: str | None) -> str | None:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii") if value else None

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("Stored CRM token could not be decrypted") from exc


def provider_config(settings: Settings, provider: str) -> ProviderConfig:
    try:
        crm_provider = CrmProvider(provider.lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported CRM provider: {provider}") from exc

    prefix = crm_provider.value
    client_id = getattr(settings, f"{prefix}_client_id")
    client_secret = getattr(settings, f"{prefix}_client_secret")
    redirect_uri = getattr(settings, f"{prefix}_redirect_uri")
    if not client_id or not client_secret or not redirect_uri:
        raise ValueError(f"OAuth credentials are not configured for {crm_provider.value}")

    endpoints = {
        CrmProvider.HUBSPOT: (
            "https://app.hubspot.com/oauth/authorize",
            "https://api.hubapi.com/oauth/v3/token",
            ("crm.objects.contacts.read",),
        ),
        CrmProvider.SALESFORCE: (
            "https://login.salesforce.com/services/oauth2/authorize",
            "https://login.salesforce.com/services/oauth2/token",
            ("api", "refresh_token"),
        ),
        CrmProvider.PIPEDRIVE: (
            "https://oauth.pipedrive.com/oauth/authorize",
            "https://oauth.pipedrive.com/oauth/token",
            (),
        ),
    }
    authorization_endpoint, token_endpoint, scopes = endpoints[crm_provider]
    return ProviderConfig(
        provider=crm_provider,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        scopes=scopes,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )


class CrmOAuthClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client

    def security(self) -> TokenCipher:
        return TokenCipher(self.settings.oauth_encryption_key)

    def config(self, provider: str) -> ProviderConfig:
        return provider_config(self.settings, provider)

    def authorization_url(self, provider: str, state: str) -> str:
        config = self.config(provider)
        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "state": state,
        }
        if config.scopes:
            params["scope"] = " ".join(config.scopes)
        return f"{config.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, provider: str, code: str) -> OAuthToken:
        config = self.config(provider)
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
        }
        headers: dict[str, str] = {}
        if config.provider is CrmProvider.PIPEDRIVE:
            form.pop("redirect_uri", None)
            credentials = b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            form.update({"client_id": config.client_id, "client_secret": config.client_secret})
        payload = await self._post_token(config.token_endpoint, form, headers)
        return self._token_from_payload(config.provider, payload)

    async def refresh(self, provider: str, refresh_token: str) -> OAuthToken:
        config = self.config(provider)
        form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        headers: dict[str, str] = {}
        if config.provider is CrmProvider.PIPEDRIVE:
            credentials = b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            form.update({"client_id": config.client_id, "client_secret": config.client_secret})
        payload = await self._post_token(config.token_endpoint, form, headers)
        return self._token_from_payload(config.provider, payload, fallback_refresh_token=refresh_token)

    async def _post_token(
        self, endpoint: str, form: dict[str, str], headers: dict[str, str]
    ) -> dict[str, Any]:
        if self.http_client is not None:
            response = await self.http_client.post(endpoint, data=form, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(endpoint, data=form, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise ValueError("CRM OAuth provider returned no access token")
        return payload

    @staticmethod
    def _token_from_payload(
        provider: CrmProvider,
        payload: dict[str, Any],
        fallback_refresh_token: str | None = None,
    ) -> OAuthToken:
        expires_at = None
        if payload.get("expires_in") is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))
        external_account_id = payload.get("hub_id") or payload.get("id")
        api_domain = payload.get("api_domain") or payload.get("instance_url")
        refresh_token = payload.get("refresh_token") or fallback_refresh_token
        scope = payload.get("scope")
        if isinstance(scope, list):
            scope = " ".join(str(item) for item in scope)
        return OAuthToken(
            access_token=str(payload["access_token"]),
            refresh_token=str(refresh_token) if refresh_token else None,
            expires_at=expires_at,
            external_account_id=str(external_account_id) if external_account_id else None,
            api_domain=str(api_domain) if api_domain else None,
            scope=str(scope) if scope else None,
        )
