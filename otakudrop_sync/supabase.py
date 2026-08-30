from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Mapping

from curl_cffi import requests

from .models import MerchandiseDrop

LOGGER = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Raised when the external inventory database rejects an operation."""


class SupabaseStore:
    """Small PostgREST client for an external Supabase table.

    The service-role key must remain in the worker environment and must never
    be bundled into the React Native client or committed to source control.
    """

    def __init__(self, url: str, service_role_key: str, table: str = "merchandise_drops", session: Any | None = None) -> None:
        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        self.endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        self._session = session or requests.Session()
        self._owns_session = session is None

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def upsert_drops(self, drops: list[MerchandiseDrop]) -> int:
        if not drops:
            return 0
        payload = [self._row(drop) for drop in drops]
        response = self._session.post(self.endpoint, headers=self.headers, json=payload, timeout=30)
        if response.status_code < 200 or response.status_code >= 300:
            raise DatabaseError(f"Supabase upsert failed with HTTP {response.status_code}: {response.text[:300]}")
        return len(drops)

    @staticmethod
    def _row(drop: MerchandiseDrop) -> Mapping[str, Any]:
        row = asdict(drop)
        row["fetched_at"] = drop.fetched_at.isoformat()
        row["raw_payload"] = row.pop("raw")
        return row
