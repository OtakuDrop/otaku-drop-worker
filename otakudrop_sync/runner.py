from __future__ import annotations

import logging
import os
import random
import time
from typing import Mapping

from .adapters import configured_adapters
from .apify import ApifyTaskClient
from .supabase import SupabaseStore

LOGGER = logging.getLogger("otakudrop_sync")


def env_config() -> dict[str, str]:
    return dict(os.environ)


def sync_once(env: Mapping[str, str] | None = None) -> int:
    settings = env or env_config()
    use_apify = settings.get("APIFY_TASK_ID", "").strip() and settings.get("APIFY_API_TOKEN", "").strip()
    if not use_apify and not configured_adapters(settings):
        LOGGER.warning("No authorized Apify Task or source endpoints are configured; nothing to sync")
        return 0

    store = SupabaseStore(
        settings.get("SUPABASE_URL", ""),
        settings.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        settings.get("SUPABASE_TABLE", "merchandise_drops"),
    )
    total = 0
    successful_sources = 0
    failures: list[str] = []
    try:
        if use_apify:
            client = ApifyTaskClient(settings["APIFY_API_TOKEN"])
            try:
                drops = client.latest_successful_items(settings["APIFY_TASK_ID"])
                total = store.upsert_drops(drops)
                successful_sources = 1
                LOGGER.info("Apify Task %s: normalized %d active drops and upserted %d", settings["APIFY_TASK_ID"], len(drops), total)
            finally:
                client.close()
            return total

        adapters = configured_adapters(settings)
        for index, adapter in enumerate(adapters):
            try:
                drops = adapter.fetch_active()
                inserted_or_updated = store.upsert_drops(drops)
                total += inserted_or_updated
                successful_sources += 1
                LOGGER.info("%s: normalized %d active drops and upserted %d", adapter.name, len(drops), inserted_or_updated)
            except Exception as exc:
                failures.append(adapter.name)
                LOGGER.exception("%s sync failed; continuing with remaining sources: %s", adapter.name, exc)
            if index < len(adapters) - 1:
                delay = random.uniform(
                    float(settings.get("SOURCE_DELAY_MIN_SECONDS", "30")),
                    float(settings.get("SOURCE_DELAY_MAX_SECONDS", "90")),
                )
                time.sleep(delay)
    finally:
        store.close()

    if failures and successful_sources == 0:
        raise RuntimeError(f"All enabled source adapters failed: {', '.join(failures)}")
    if failures:
        LOGGER.warning("Partial sync: %d source(s) failed: %s", len(failures), ", ".join(failures))
    return total


def run_forever(interval_minutes: float = 120.0) -> None:
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    while True:
        started = time.monotonic()
        try:
            sync_once()
        except Exception:
            LOGGER.exception("Sync cycle failed")
        elapsed = time.monotonic() - started
        sleep_seconds = max(interval_minutes * 60 - elapsed, 0)
        LOGGER.info("Next sync in %.1f minutes", sleep_seconds / 60)
        time.sleep(sleep_seconds)


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if os.getenv("RUN_ONCE", "true").lower() in {"1", "true", "yes"}:
        sync_once()
        return 0
    run_forever(float(os.getenv("SYNC_INTERVAL_MINUTES", "120")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
