from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class MerchandiseDrop:
    source: str
    source_id: str
    title: str
    price_jpy: int | None
    release_date: str | None
    image_url: str | None
    product_url: str | None
    status: str
    raw: dict[str, Any]
    fetched_at: datetime


class SourceAdapter(Protocol):
    name: str

    def fetch_active(self) -> list[MerchandiseDrop]:
        """Fetch and normalize active products from an authorized source feed."""
