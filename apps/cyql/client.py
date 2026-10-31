"""Verbinding met de Cyql GraphQL-API (https://api.cyql.app/api/docs/).

De API-sleutel komt enkel uit de omgevingsvariabele CYQL_API_KEY en bepaalt
meteen de club. Elke vraag kost "complexiteit" van een wekelijks budget, dus
vraag enkel de velden op die je nodig hebt.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
TIMEOUT = 30


class CyqlError(Exception):
    def __init__(self, message, code=None, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class CyqlClient:
    def __init__(self, api_key=None, url=None):
        self.api_key = api_key if api_key is not None else settings.CYQL_API_KEY
        self.url = url or settings.CYQL_API_URL
        # Resterend weekbudget van de club, zoals Cyql het bij elk antwoord meegeeft.
        self.remaining = None

    @property
    def configured(self):
        return bool(self.api_key)

    def query(self, query, variables=None):
        if not self.configured:
            raise CyqlError("CYQL_API_KEY ontbreekt", code="NoApiKey")
        try:
            response = requests.post(
                self.url,
                json={"query": query, "variables": variables or {}},
                headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CyqlError(f"Cyql niet bereikbaar: {exc.__class__.__name__}", code="Network") from exc

        remaining = response.headers.get("X-RateLimit-Remaining-Club")
        if remaining not in (None, "-1"):
            self.remaining = int(remaining)
        try:
            body = response.json()
        except ValueError as exc:
            raise CyqlError(f"Onverwacht antwoord van Cyql (HTTP {response.status_code})", code="BadResponse") from exc

        errors = body.get("errors") or []
        if errors:
            first = errors[0]
            code = (first.get("extensions") or {}).get("code") or first.get("message")
            retry_after = response.headers.get("Retry-After")
            raise CyqlError(first.get("message", "Onbekende fout"), code=code, retry_after=retry_after)
        if response.status_code >= 400:
            raise CyqlError(f"HTTP {response.status_code}", code=f"HTTP{response.status_code}")
        return body.get("data") or {}
