from __future__ import annotations

import logging
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

from curl_cffi import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


class FetchError(RuntimeError):
    """Raised when a source feed cannot be fetched safely."""


class BlockedSourceError(FetchError):
    """Raised when a retailer rejects the request or presents a challenge page."""


def retry_after_seconds(response: Any, fallback: float, maximum: float) -> float:
    value = response.headers.get("Retry-After")
    if not value:
        return min(fallback, maximum)
    try:
        return min(max(float(value), 0.0), maximum)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            return min(max(retry_at.timestamp() - time.time(), 0.0), maximum)
        except (TypeError, ValueError, OverflowError):
            return min(fallback, maximum)


def _validate_retry_config(max_attempts: int, delay_min_seconds: float, delay_max_seconds: float) -> None:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay_min_seconds < 0 or delay_max_seconds < delay_min_seconds:
        raise ValueError("Invalid delay range")


def _headers(headers: Mapping[str, str] | None, *, json_only: bool) -> dict[str, str]:
    defaults = dict(DEFAULT_HEADERS)
    if json_only:
        defaults["Accept"] = "application/json"
    defaults.update(headers or {})
    return defaults


def _sleep_before_retry(url: str, response: Any | None, attempt: int, delay_min_seconds: float, delay_max_seconds: float, max_retry_delay_seconds: float) -> None:
    exponential = delay_min_seconds * (2 ** (attempt - 1))
    delay = retry_after_seconds(response, exponential, max_retry_delay_seconds) if response is not None else exponential
    delay = max(delay, random.uniform(delay_min_seconds, delay_max_seconds))
    LOGGER.warning("Retrying %s in %.2fs", url, delay)
    time.sleep(delay)


def _request_with_retries(url: str, *, headers: Mapping[str, str], params: Mapping[str, Any] | None, timeout_seconds: float, max_attempts: int, delay_min_seconds: float, delay_max_seconds: float, max_retry_delay_seconds: float, session: Any | None) -> Any:
    if not url:
        raise FetchError("Source endpoint is not configured")
    _validate_retry_config(max_attempts, delay_min_seconds, delay_max_seconds)
    client = session or requests.Session()
    owns_session = session is None
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.get(url, params=params, headers=headers, timeout=timeout_seconds)
            except requests.errors.RequestsError as exc:
                if attempt == max_attempts:
                    raise FetchError(f"Network error after {attempt} attempts: {exc}") from exc
                _sleep_before_retry(url, None, attempt, delay_min_seconds, delay_max_seconds, max_retry_delay_seconds)
                continue
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt == max_attempts:
                    raise FetchError(f"Retryable HTTP {response.status_code} after {attempt} attempts")
                _sleep_before_retry(url, response, attempt, delay_min_seconds, delay_max_seconds, max_retry_delay_seconds)
                continue
            if response.status_code in {401, 403}:
                raise BlockedSourceError(
                    f"HTTP {response.status_code} from {url}; source access is unauthorized or blocked. "
                    "Use an approved API/feed or retailer allowlisting; no challenge bypass is attempted."
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise FetchError(f"HTTP {response.status_code} from {url}: {response.text[:200]}")
            return response
    finally:
        if owns_session:
            client.close()
    raise FetchError(f"Unable to fetch {url}")


def get_text(url: str, *, headers: Mapping[str, str] | None = None, params: Mapping[str, Any] | None = None, timeout_seconds: float = 20.0, max_attempts: int = 3, delay_min_seconds: float = 1.0, delay_max_seconds: float = 3.0, max_retry_delay_seconds: float = 30.0, session: Any | None = None) -> str:
    response = _request_with_retries(url, headers=_headers(headers, json_only=False), params=params, timeout_seconds=timeout_seconds, max_attempts=max_attempts, delay_min_seconds=delay_min_seconds, delay_max_seconds=delay_max_seconds, max_retry_delay_seconds=max_retry_delay_seconds, session=session)
    return response.text


def get_json(url: str, *, headers: Mapping[str, str] | None = None, params: Mapping[str, Any] | None = None, timeout_seconds: float = 20.0, max_attempts: int = 3, delay_min_seconds: float = 1.0, delay_max_seconds: float = 3.0, max_retry_delay_seconds: float = 30.0, session: Any | None = None) -> Any:
    """Fetch JSON with standard negotiation and bounded retries, never challenge bypass."""
    response = _request_with_retries(url, headers=_headers(headers, json_only=True), params=params, timeout_seconds=timeout_seconds, max_attempts=max_attempts, delay_min_seconds=delay_min_seconds, delay_max_seconds=delay_max_seconds, max_retry_delay_seconds=max_retry_delay_seconds, session=session)
    try:
        return response.json()
    except ValueError as exc:
        raise FetchError(f"Invalid JSON from {url}") from exc
