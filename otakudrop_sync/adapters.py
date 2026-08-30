from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .http import get_json, get_text
from .models import MerchandiseDrop, SourceAdapter

LOGGER = logging.getLogger(__name__)

_TITLE_KEYS = ("title", "name", "productName", "product_title")
_ID_KEYS = ("id", "itemId", "productId", "item_id", "sku", "code")
_PRICE_KEYS = ("priceJPY", "price_jpy", "price", "amount", "value")
_RELEASE_KEYS = ("releaseDate", "release_date", "発売日", "availableDate", "datePublished")
_IMAGE_KEYS = ("imageUrl", "image_url", "image", "thumbnail", "thumbnailUrl")
_URL_KEYS = ("productUrl", "product_url", "url", "link", "canonicalUrl")
_STATUS_KEYS = ("status", "availability", "stockStatus", "stock", "inventory", "quantity")
_LIST_KEYS = ("items", "products", "results", "data", "records")
_SOLD_MARKERS = ("sold out", "soldout", "out of stock", "outofstock", "closed", "ended", "unavailable", "完売", "売り切れ", "在庫なし")


def _first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return value
    return None


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    item_list = payload.get("itemListElement")
    if isinstance(item_list, list):
        return [item.get("item", item) if isinstance(item, dict) else item for item in item_list if isinstance(item, dict)]
    for key in _LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _records(value)
            if nested:
                return nested
    return [dict(payload)] if _first(payload, _TITLE_KEYS) else []


def _number(value: Any) -> int | None:
    if isinstance(value, Mapping):
        value = _first(value, ("amount", "value", "price"))
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("¥", "").replace("JPY", "").strip()
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        return _text(_first(value, ("name", "label", "value", "text")))
    return None


def _url(value: Any, base_url: str) -> str | None:
    if isinstance(value, list):
        for item in value:
            result = _url(item, base_url)
            if result:
                return result
        return None
    if isinstance(value, Mapping):
        value = _first(value, ("url", "contentUrl", "src", "href"))
    if not isinstance(value, str) or not value.strip():
        return None
    return urljoin(base_url, value.strip())


def _is_active(record: Mapping[str, Any]) -> bool:
    for key in _STATUS_KEYS:
        if key not in record:
            continue
        value = record[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value > 0
        text = str(value).strip().lower()
        if text in {"0", "false", "none", "null"} or any(marker in text for marker in _SOLD_MARKERS):
            return False
    return True


def normalize_record(source: str, record: Mapping[str, Any], base_url: str) -> MerchandiseDrop | None:
    if not _is_active(record):
        return None
    title = _text(_first(record, _TITLE_KEYS))
    source_id = _text(_first(record, _ID_KEYS))
    if not title or not source_id:
        LOGGER.warning("Skipping %s record without title or stable ID", source)
        return None
    return MerchandiseDrop(
        source=source,
        source_id=source_id,
        title=title,
        price_jpy=_number(_first(record, _PRICE_KEYS)),
        release_date=_text(_first(record, _RELEASE_KEYS)),
        image_url=_url(_first(record, _IMAGE_KEYS), base_url),
        product_url=_url(_first(record, _URL_KEYS), base_url),
        status="active",
        raw=dict(record),
        fetched_at=datetime.now(timezone.utc),
    )


def _html_records(html: str) -> list[dict[str, Any]]:
    """Extract public JSON-LD or explicit data attributes from a result document."""
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, Any]] = []

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        records.extend(_records(payload))

    for node in soup.select("[data-item-id], [data-product-id], [data-sku]"):
        source_id = node.get("data-item-id") or node.get("data-product-id") or node.get("data-sku")
        title_node = node.select_one("[data-title], .title, .product-title, .item-title, h2, h3")
        image_node = node.select_one("img")
        link_node = node.select_one("a[href]")
        records.append(
            {
                "id": source_id,
                "title": node.get("data-title") or (title_node.get_text(" ", strip=True) if title_node else None),
                "price": node.get("data-price") or node.get("data-price-jpy"),
                "image": image_node.get("src") if image_node else None,
                "url": link_node.get("href") if link_node else None,
                "status": node.get("data-status") or node.get("data-availability"),
            }
        )
    return records


@dataclass
class JSONSourceAdapter(SourceAdapter):
    name: str
    endpoint: str
    base_url: str
    headers: Mapping[str, str] | None = None
    params: Mapping[str, Any] | None = None

    def fetch_active(self) -> list[MerchandiseDrop]:
        payload = get_json(self.endpoint, headers=self.headers, params=self.params)
        return [item for record in _records(payload) if (item := normalize_record(self.name, record, self.base_url))]


@dataclass
class HTMLSourceAdapter(SourceAdapter):
    name: str
    endpoint: str
    base_url: str
    headers: Mapping[str, str] | None = None
    params: Mapping[str, Any] | None = None

    def fetch_active(self) -> list[MerchandiseDrop]:
        html = get_text(self.endpoint, headers=self.headers, params=self.params)
        return [item for record in _html_records(html) if (item := normalize_record(self.name, record, self.base_url))]


def _browser_origin_headers(origin: str, referer: str) -> dict[str, str]:
    """Use ordinary documented navigation headers; this is not fingerprint spoofing."""
    return {"Origin": origin, "Referer": referer}


def configured_adapters(env: Mapping[str, str]) -> list[SourceAdapter]:
    """Build adapters from configured, authorized/public feeds only.

    AmiAmi is JSON. Mandarake and Suruga-ya use their public search document
    structure when enabled; hidden JSON endpoints are intentionally not used.
    """
    adapters: list[SourceAdapter] = []

    amiami_endpoint = env.get("AMIAMI_ENDPOINT", "https://api.amiami.com/api/v1.0/items")
    if env.get("AMIAMI_ENABLED", "false").lower() == "true":
        adapters.append(
            JSONSourceAdapter(
                name="AmiAmi",
                endpoint=amiami_endpoint,
                base_url="https://www.amiami.com/",
                headers=_browser_origin_headers("https://www.amiami.com", "https://www.amiami.com/"),
                params={
                    "s_keywords": env.get("AMIAMI_KEYWORDS", ""),
                    "pagecnt": "1",
                    "pagemax": "10",
                },
            )
        )

    mandarake_endpoint = env.get("MANDARAKE_ENDPOINT", "https://search.mandarake.co.jp/search/search-results")
    if env.get("MANDARAKE_ENABLED", "false").lower() == "true":
        params: dict[str, str] = {"sort": env.get("MANDARAKE_SORT", "bid")}
        if env.get("MANDARAKE_KEYWORDS"):
            params["q"] = env["MANDARAKE_KEYWORDS"]
        if env.get("MANDARAKE_CATEGORY"):
            params["category"] = env["MANDARAKE_CATEGORY"]
        adapters.append(
            HTMLSourceAdapter(
                name="Mandarake",
                endpoint=mandarake_endpoint,
                base_url=env.get("MANDARAKE_BASE_URL", "https://search.mandarake.co.jp/"),
                headers=_browser_origin_headers("https://search.mandarake.co.jp", "https://search.mandarake.co.jp/"),
                params=params,
            )
        )

    surugaya_endpoint = env.get("SURUGAYA_ENDPOINT", "https://www.suruga-ya.jp/search")
    if env.get("SURUGAYA_ENABLED", "false").lower() == "true":
        adapters.append(
            HTMLSourceAdapter(
                name="Suruga-ya",
                endpoint=surugaya_endpoint,
                base_url=env.get("SURUGAYA_BASE_URL", "https://www.suruga-ya.jp/"),
                headers=_browser_origin_headers("https://www.suruga-ya.jp", "https://www.suruga-ya.jp/"),
                params={
                    "category": env.get("SURUGAYA_CATEGORY", ""),
                    "search_word": env.get("SURUGAYA_KEYWORDS", ""),
                },
            )
        )
    return adapters
