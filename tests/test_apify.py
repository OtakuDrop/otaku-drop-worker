import unittest
from unittest.mock import Mock

from otakudrop_sync.apify import ApifyTaskClient


class ApifyTaskTests(unittest.TestCase):
    def test_selects_latest_successful_dataset_and_filters_inactive(self):
        session = Mock()
        runs = Mock(status_code=200)
        runs.json.return_value = {
            "data": {
                "items": [
                    {"status": "RUNNING", "defaultDatasetId": "ignored"},
                    {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"},
                ]
            }
        }
        dataset = Mock(status_code=200)
        dataset.json.return_value = [
            {"source": "managed", "source_id": "active-1", "title": "Figure", "price_jpy": "5,000"},
            {"source": "managed", "source_id": "sold-1", "title": "Sold Figure", "status": "sold out"},
        ]
        session.get.side_effect = [runs, dataset]

        client = ApifyTaskClient("token", session=session)
        drops = client.latest_successful_items("task-1")

        self.assertEqual([drop.source_id for drop in drops], ["active-1"])
        self.assertEqual(session.get.call_count, 2)
        self.assertIn("actor-tasks/task-1/runs", session.get.call_args_list[0].args[0])
        self.assertIn("datasets/dataset-1/items", session.get.call_args_list[1].args[0])

    def test_requires_a_successful_run(self):
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"items": []}}
        session.get.return_value = response
        client = ApifyTaskClient("token", session=session)
        with self.assertRaisesRegex(RuntimeError, "No successful Apify Task run"):
            client.latest_successful_items("task-1")


if __name__ == "__main__":
    unittest.main()
