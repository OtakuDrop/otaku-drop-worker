from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from curl_cffi import requests

from .models import MerchandiseDrop

LOGGER = logging.getLogger(__name__)


class ApifyError(RuntimeError):
    """Raised when Apify cannot provide a usable task result."""


class ApifyTaskClient:
    def __init__(self, token: str, session: Any | None = None) -> None:
        if not token:
            raise ValueError("APIFY_API_TOKEN is required")
        self._session = session or requests.Session(impersonate="chrome")
        self._owns_session = session is None
        self.headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def latest_successful_items(self, task_id: str) -> list[MerchandiseDrop]:
        if not task_id:
            raise ValueError("APIFY_TASK_ID is required")
        response = self._session.get(
            f"https://api.apify.com/v2/actor-tasks/{task_id}/runs",
            headers=self.headers,
            params={"limit": 20, "desc": "true"},
            timeout=30,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise ApifyError(f"Apify runs query failed with HTTP {response.status_code}")
        payload = response.json()
        runs = payload.get("data", {}).get("items", []) if isinstance(payload, dict) else []
        successful = next((run for run in runs if run.get("status") == "SUCCEEDED" and run.get("defaultDatasetId")), None)
        if not successful:
            raise ApifyError("No successful Apify Task run with a default dataset was found")

        dataset_id = successful["defaultDatasetId"]
        dataset_response = self._session.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            headers=self.headers,
            params={"clean": "true", "format": "json"},
            timeout=60,
        )
        if dataset_response.status_code < 200 or dataset_response.status_code >= 300:
            raise ApifyError(f"Apify dataset query failed with HTTP {dataset_response.status_code}")
        records = dataset_response.json()
        if not isinstance(records, list):
            raise ApifyError("Apify dataset response was not a JSON array")
        return [drop for record in records if (drop := self._normalize(record)) is not None]

    @staticmethod
    def _normalize(record: Any) -> MerchandiseDrop | None:
        if not isinstance(record, dict):
            return None
        status = str(record.get("status") or record.get("availability") or "").lower()
        if any(term in status for term in ("sold out", "out of stock", "closed", "ended", "unavailable", "完売", "売り切れ")):
            return None
        source = str(record.get("source") or record.get("retailer") or "managed-apify")
        source_id = str(record.get("source_id") or record.get("id") or record.get("product_id") or "")
        title = str(record.get("title") or record.get("name") or "").strip()
        if not source_id or not title:
            return None
        raw_price = record.get("price_jpy", record.get("price"))
        try:
            price = int(float(str(raw_price).replace(",", "").replace("¥", ""))) if raw_price is not None else None
        except ValueError:
            price = None
        return MerchandiseDrop(
            source=source,
            source_id=source_id,
            title=title,
            price_jpy=price,
            release_date=record.get("release_date") or record.get("releaseDate"),
            image_url=record.get("image_url") or record.get("imageUrl"),
            product_url=record.get("product_url") or record.get("url"),
            status="active",
            raw=record,
            fetched_at=datetime.now(timezone.utc),
        )
