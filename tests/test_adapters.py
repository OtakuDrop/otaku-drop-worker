import unittest

from otakudrop_sync.adapters import normalize_record


class AdapterTests(unittest.TestCase):
    def test_normalizes_active_record(self):
        item = normalize_record(
            "AmiAmi",
            {
                "itemId": "A-100",
                "name": "Limited Figure",
                "price": "12,800",
                "releaseDate": "2026-10-01",
                "image": "/images/a.jpg",
                "url": "/item/A-100",
                "stockStatus": "In Stock",
            },
            "https://example.test/",
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.source_id, "A-100")
        self.assertEqual(item.price_jpy, 12800)
        self.assertEqual(item.image_url, "https://example.test/images/a.jpg")
        self.assertEqual(item.product_url, "https://example.test/item/A-100")

    def test_filters_sold_out_record(self):
        item = normalize_record(
            "Suruga-ya",
            {"id": "S-1", "title": "Sold Item", "availability": "Sold Out"},
            "https://example.test/",
        )
        self.assertIsNone(item)

    def test_skips_record_without_stable_id(self):
        item = normalize_record("Mandarake", {"name": "No ID"}, "https://example.test/")
        self.assertIsNone(item)


if __name__ == "__main__":
    unittest.main()
