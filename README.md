# OtakuDrop Inventory Sync Worker

This standalone Python service normalizes merchandise feeds from explicitly authorized or documented retailer endpoints and upserts active drops into Supabase. It supports AmiAmi, Mandarake, and Suruga-ya through configurable JSON adapters. The adapters are deliberately disabled when their endpoints are not configured, so the worker never guesses undocumented URLs.

The worker uses `curl_cffi` for HTTP requests, bounded retries, `Retry-After`, and randomized delays between requests and sources. It does **not** rotate proxies or spoof browser fingerprints. Use only endpoints and credentials you are authorized to access, and comply with each retailer’s terms, robots policy, and rate limits.

## Setup

```bash
cd otakudrop-sync-worker
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Create the table in the Supabase SQL editor using [`supabase_schema.sql`](./supabase_schema.sql). Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the worker environment. The service-role key must remain server-side and must never be placed in the React Native bundle.

Configure only authorized JSON endpoints:

```dotenv
AMIAMI_ENDPOINT=https://authorized.example/amiami/feed
MANDARAKE_ENDPOINT=https://authorized.example/mandarake/feed
SURUGAYA_ENDPOINT=https://authorized.example/surugaya/feed
```

The supplied AmiAmi URL returned `Invalid access` without authorized access, and no general public inventory endpoints were confirmed for Mandarake or Suruga-ya in the reviewed official pages. Obtain written/API documentation or a partner feed before enabling each source.

## Run modes

Run one synchronization cycle from an external scheduler:

```bash
RUN_ONCE=true python -m otakudrop_sync.runner
```

A standard Unix cron entry for every two hours is:

```cron
0 */2 * * * cd /srv/otakudrop-sync-worker && .venv/bin/python -m otakudrop_sync.runner >> /var/log/otakudrop-sync.log 2>&1
```

Alternatively, run a single long-lived process with `RUN_ONCE=false` and `SYNC_INTERVAL_MINUTES=120`, supervised by a container platform or process manager. A managed external scheduler invoking the one-shot command is generally easier to observe and restart.

## Data behavior

Each normalized row is keyed by `(source, source_id)`, so repeating a cycle updates the existing record instead of creating duplicates. Records whose status or quantity indicates `sold out`, `out of stock`, `closed`, `ended`, `unavailable`, `完売`, `売り切れ`, or `在庫なし` are excluded. Records without a stable source ID or title are skipped and logged.

The table stores normalized fields (`title`, `price_jpy`, `release_date`, `image_url`, `product_url`, `status`, and `fetched_at`) plus the original source object in `raw_payload` for troubleshooting. Inventory can change between synchronization and checkout, so the frontend should show the last-synced timestamp and link back to the retailer.

## Tests

The test suite is fully offline:

```bash
python -m unittest discover -s tests -v
```

It verifies active-record normalization, sold-out filtering, stable-ID requirements, and URL resolution. No retailer endpoint is contacted by the tests.

## Files

| File | Purpose |
|---|---|
| `otakudrop_sync/adapters.py` | Configurable source adapters and active-item normalization. |
| `otakudrop_sync/http.py` | Conservative `curl_cffi` JSON client with retries and jitter. |
| `otakudrop_sync/supabase.py` | Server-side Supabase REST upsert client. |
| `otakudrop_sync/runner.py` | One-shot and interval-based execution. |
| `supabase_schema.sql` | Idempotent inventory table and indexes. |
| `.env.example` | Configuration template. |

## GitHub Actions deployment

The workflow at [`.github/workflows/otakudrop-sync.yml`](./.github/workflows/otakudrop-sync.yml) runs at minute 0 of every even UTC hour (`0 */2 * * *`) and can also be started manually with **Run workflow**. In the repository settings, add these **Actions secrets**:

| Secret | Value |
|---|---|
| `SUPABASE_URL` | The Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | The server-only service-role key. Never expose it to the mobile client. |

Add the source endpoints, enable flags, and query values as **Actions variables**, not secrets, unless a source separately requires authentication. Set `AMIAMI_ENABLED`, `MANDARAKE_ENABLED`, or `SURUGAYA_ENABLED` to `true` only after confirming the endpoint and access terms. The workflow does not use rotating proxies, browser-fingerprint spoofing, Cloudflare bypasses, or hidden JSON endpoints.

The GitHub-hosted runner only executes the adapter and database code; it does not make a source feed authorized. If an endpoint returns 401, 403, 429, a challenge page, or an undocumented response, the worker logs the failure and continues with the remaining sources.

## Verified source references

The supplied [AmiAmi items endpoint](https://api.amiami.com/api/v1.0/items) returned `Invalid access` when checked without authorized access [1]. Mandarake’s [official mail-order FAQ](https://earth.mandarake.co.jp/help/en/faq/faq-en.html) does not document a general public inventory API in the reviewed page [2]. Suruga-ya’s [official inventory Q&A](https://www.suruga-ya.com/en/qa-detail/46) cautions that stock may change by the time an order is placed [3].

## References

[1]: https://api.amiami.com/api/v1.0/items "AmiAmi items endpoint"
[2]: https://earth.mandarake.co.jp/help/en/faq/faq-en.html "Mandarake Mail Order FAQ"
[3]: https://www.suruga-ya.com/en/qa-detail/46 "Suruga-ya inventory Q&A"
