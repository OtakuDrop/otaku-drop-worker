import unittest
from datetime import datetime, timezone

from otakudrop_sync.models import MerchandiseDrop
from otakudrop_sync.supabase import SupabaseStore


class FakeResponse:
    status_code = 201
    text = ""


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return FakeResponse()


class SupabaseStoreTests(unittest.TestCase):
    def test_upsert_uses_deployed_table_payload(self):
        session = FakeSession()
        store = SupabaseStore("https://demo.supabase.co", "server-only-key", session=session)
        drop = MerchandiseDrop(
            source="AmiAmi",
            source_id="A-1",
            title="Figure",
            price_jpy=5000,
            release_date="2026-09-01",
            image_url="https://cdn.example/figure.jpg",
            product_url="https://example/figure",
            status="active",
            raw={"id": "A-1"},
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(store.upsert_drops([drop]), 1)
        args, kwargs = session.calls[0]
        payload = kwargs["json"][0]
        self.assertEqual(payload["title"], "Figure")
        self.assertEqual(payload["retailer"], "AmiAmi")
        self.assertEqual(payload["price"], 5000)
        self.assertEqual(payload["created_at"], "2026-01-01T00:00:00+00:00")
        self.assertIn("on_conflict=id", args[0])
        self.assertIn("resolution=merge-duplicates", kwargs["headers"]["Prefer"])


if __name__ == "__main__":
    unittest.main()
