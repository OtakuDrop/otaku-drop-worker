from __future__ import annotations

import logging
import os
import random
import time
from typing import Mapping

from .adapters import configured_adapters
from .supabase import SupabaseStore

LOGGER = logging.getLogger("otakudrop_sync")


def env_config() -> dict[str, str]:
    return dict(os.environ)


def sync_once(env: Mapping[str, str] | None = None) -> int:
    settings = env or env_config()
    adapters = configured_adapters(settings)
    if not adapters:
        LOGGER.warning("No authorized source endpoints are configured; nothing to sync")
        return 0

    store = SupabaseStore(
        settings.get("SUPABASE_URL", ""),
        settings.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        settings.get("SUPABASE_TABLE", "merchandise_drops"),
    )
    total = 0
    try:
        for index, adapter in enumerate(adapters):
            try:
                drops = adapter.fetch_active()
                inserted_or_updated = store.upsert_drops(drops)
                total += inserted_or_updated
                LOGGER.info("%s: normalized %d active drops and upserted %d", adapter.name, len(drops), inserted_or_updated)
            except Exception:
                LOGGER.exception("%s sync failed; continuing with remaining sources", adapter.name)
            if index < len(adapters) - 1:
                delay = random.uniform(
                    float(settings.get("SOURCE_DELAY_MIN_SECONDS", "2")),
                    float(settings.get("SOURCE_DELAY_MAX_SECONDS", "5")),
                )
                time.sleep(delay)
    finally:
        store.close()
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
