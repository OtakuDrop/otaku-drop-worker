from __future__ import annotations

import hashlib
from typing import Any, Mapping

from curl_cffi import requests

from .models import MerchandiseDrop


class DatabaseError(RuntimeError):
    """Raised when the external inventory database rejects an operation."""


class SupabaseStore:
    """PostgREST client for the deployed merchandise_drops table."""

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
        response = self._session.post(
            f"{self.endpoint}?on_conflict=id",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise DatabaseError(f"Supabase upsert failed with HTTP {response.status_code}: {response.text[:300]}")
        return len(drops)

    @staticmethod
    def stable_id(drop: MerchandiseDrop) -> int:
        digest = hashlib.sha256(f"{drop.source}:{drop.source_id}".encode("utf-8")).hexdigest()
        return max(1, int(digest[:15], 16))

    @classmethod
    def _row(cls, drop: MerchandiseDrop) -> Mapping[str, Any]:
        return {
            "id": cls.stable_id(drop),
            "title": drop.title,
            "retailer": drop.source,
            "price": drop.price_jpy,
            "url": drop.product_url,
            "image_url": drop.image_url,
            "release_date": drop.release_date,
            "created_at": drop.fetched_at.isoformat(),
        }
