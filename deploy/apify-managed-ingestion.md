# Managed Apify ingestion

The repository no longer runs direct retailer requests from GitHub Actions. The GitHub workflow only installs dependencies, runs offline tests, and compiles the worker on repository changes.

Configure the authorized Apify Actor or Task to run every two hours with the cron expression `0 */2 * * *`. Add a webhook for the `ACTOR.RUN.SUCCEEDED` event and point it to the deployed OtakuDrop server endpoint:

```text
POST https://<published-otakudrop-host>/api/webhooks/apify
```

Configure the webhook to send the shared value from `APIFY_WEBHOOK_SECRET` in the `x-apify-webhook-secret` header. The payload must include `actorRunId`; include `actorId` and `actorTaskId` when the corresponding allowlist variables are configured. The listener fetches the completed run’s default dataset using the server-only `APIFY_API_TOKEN`, filters closed or sold-out records, and upserts normalized rows into Supabase.

## Required server configuration

| Variable | Purpose |
|---|---|
| `APIFY_API_TOKEN` | Server-only token used to read the completed actor dataset. |
| `APIFY_WEBHOOK_SECRET` | Shared webhook authentication secret. |
| `APIFY_ACTOR_ID` | Optional allowlist for the expected Actor ID. |
| `APIFY_TASK_ID` | Optional allowlist for the expected Task ID. |
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only key used for the inventory upsert. |

Do not enable direct retailer scraping as a fallback after a webhook failure. The service does not bypass retailer access controls, WAFs, or Cloudflare challenges; use only actor sources and feeds that are authorized for the target catalogs.
