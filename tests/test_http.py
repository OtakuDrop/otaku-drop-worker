import unittest

from otakudrop_sync.http import BlockedSourceError, get_json


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"ok": True}
        self.text = "challenge" if status_code == 403 else ""
        self.headers = {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class HttpTests(unittest.TestCase):
    def test_standard_headers_are_sent(self):
        session = FakeSession(FakeResponse())
        self.assertEqual(get_json("https://example.test/feed", session=session), {"ok": True})
        headers = session.calls[0][1]["headers"]
        self.assertIn("Chrome/124.0.0.0", headers["User-Agent"])
        self.assertIn("en-US", headers["Accept-Language"])
        self.assertEqual(headers["Accept"], "application/json")

    def test_forbidden_response_is_not_retried_or_bypassed(self):
        session = FakeSession(FakeResponse(status_code=403))
        with self.assertRaises(BlockedSourceError):
            get_json("https://example.test/feed", session=session, max_attempts=3)
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
