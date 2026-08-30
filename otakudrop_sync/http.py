from __future__ import annotations

import logging
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

from curl_cffi import requests

LOGGER = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """Raised when a source feed cannot be fetched safely."""


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


def get_text(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout_seconds: float = 20.0,
    max_attempts: int = 3,
    delay_min_seconds: float = 1.0,
    delay_max_seconds: float = 3.0,
    max_retry_delay_seconds: float = 30.0,
    session: Any | None = None,
) -> str:
    """Fetch an authorized/public HTML or text feed without browser evasion."""
    response = _request_with_retries(
        url,
        headers=headers,
        params=params,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        delay_min_seconds=delay_min_seconds,
        delay_max_seconds=delay_max_seconds,
        max_retry_delay_seconds=max_retry_delay_seconds,
        session=session,
    )
    return response.text


def _request_with_retries(
    url: str,
    *,
    headers: Mapping[str, str] | None,
    params: Mapping[str, Any] | None,
    timeout_seconds: float,
    max_attempts: int,
    delay_min_seconds: float,
    delay_max_seconds: float,
    max_retry_delay_seconds: float,
    session: Any | None,
) -> Any:
    if not url:
        raise FetchError("Source endpoint is not configured")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay_min_seconds < 0 or delay_max_seconds < delay_min_seconds:
        raise ValueError("Invalid delay range")

    client = session or requests.Session()
    owns_session = session is None
    request_headers = {"Accept": "application/json, text/html;q=0.9", **(headers or {})}

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.get(url, params=params, headers=request_headers, timeout=timeout_seconds)
            except requests.errors.RequestsError as exc:
                if attempt == max_attempts:
                    raise FetchError(f"Network error after {attempt} attempts: {exc}") from exc
                delay = random.uniform(delay_min_seconds, delay_max_seconds)
                LOGGER.warning("Network error for %s; retrying in %.2fs", url, delay)
                time.sleep(delay)
                continue

            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt == max_attempts:
                    raise FetchError(f"Retryable HTTP {response.status_code} after {attempt} attempts")
                exponential = delay_min_seconds * (2 ** (attempt - 1))
                delay = retry_after_seconds(response, exponential, max_retry_delay_seconds)
                delay = max(delay, random.uniform(delay_min_seconds, delay_max_seconds))
                LOGGER.warning("HTTP %d for %s; retrying in %.2fs", response.status_code, url, delay)
                time.sleep(delay)
                continue

            if response.status_code < 200 or response.status_code >= 300:
                raise FetchError(f"HTTP {response.status_code} from {url}: {response.text[:200]}")
            return response
    finally:
        if owns_session:
            client.close()

    raise FetchError(f"Unable to fetch {url}")


def get_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout_seconds: float = 20.0,
    max_attempts: int = 3,
    delay_min_seconds: float = 1.0,
    delay_max_seconds: float = 3.0,
    max_retry_delay_seconds: float = 30.0,
    session: Any | None = None,
) -> Any:
    """Fetch JSON from an authorized/public endpoint with conservative retries.

    This intentionally does not rotate proxies or spoof browser fingerprints.
    The session uses curl_cffi for a compatible HTTP client, while request
    identity remains transparent to the source service.
    """
    if not url:
        raise FetchError("Source endpoint is not configured")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay_min_seconds < 0 or delay_max_seconds < delay_min_seconds:
        raise ValueError("Invalid delay range")

    client = session or requests.Session()
    owns_session = session is None
    request_headers = {"Accept": "application/json", **(headers or {})}

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.get(url, params=params, headers=request_headers, timeout=timeout_seconds)
            except requests.errors.RequestsError as exc:
                if attempt == max_attempts:
                    raise FetchError(f"Network error after {attempt} attempts: {exc}") from exc
                delay = random.uniform(delay_min_seconds, delay_max_seconds)
                LOGGER.warning("Network error for %s; retrying in %.2fs", url, delay)
                time.sleep(delay)
                continue

            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt == max_attempts:
                    raise FetchError(f"Retryable HTTP {response.status_code} after {attempt} attempts")
                exponential = delay_min_seconds * (2 ** (attempt - 1))
                delay = retry_after_seconds(response, exponential, max_retry_delay_seconds)
                delay = max(delay, random.uniform(delay_min_seconds, delay_max_seconds))
                LOGGER.warning("HTTP %d for %s; retrying in %.2fs", response.status_code, url, delay)
                time.sleep(delay)
                continue

            if response.status_code < 200 or response.status_code >= 300:
                raise FetchError(f"HTTP {response.status_code} from {url}: {response.text[:200]}")

            try:
                return response.json()
            except ValueError as exc:
                raise FetchError(f"Invalid JSON from {url}") from exc
    finally:
        if owns_session:
            client.close()

    raise FetchError(f"Unable to fetch {url}")
