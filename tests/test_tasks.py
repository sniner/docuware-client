from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from docuware.tasks import MyTasks
from docuware.types import OrganizationP

_TASKS_ENDPOINT = {"Links": [{"rel": "myTasks", "href": "/DocuWare/Platform/MyTasks"}]}


def _make_tasks(task_list, count=None, timestamp="/Date(1705276800000)/"):
    mock_org = MagicMock(spec=OrganizationP)
    mock_client = MagicMock()
    mock_conn = MagicMock()
    mock_org.client = mock_client
    mock_client.conn = mock_conn
    mock_conn.get_json.return_value = {
        "Task": task_list,
        "Count": count if count is not None else len(task_list),
        "TimeStamp": timestamp,
        "Links": [{"rel": "myTasks", "href": "/DocuWare/Platform/MyTasks"}],
    }
    return MyTasks(_TASKS_ENDPOINT, mock_org), mock_conn


class TestMyTasks(unittest.TestCase):
    def test_init_calls_refresh(self):
        _, mock_conn = _make_tasks([])
        mock_conn.get_json.assert_called_once()

    def test_count_from_response(self):
        tasks, _ = _make_tasks([{"Id": "t1"}, {"Id": "t2"}], count=42)
        self.assertEqual(tasks.count, 42)

    def test_timestamp_set(self):
        tasks, _ = _make_tasks([])
        self.assertIsNotNone(tasks.timestamp)

    def test_iteration_yields_all_tasks(self):
        task_data = [{"Id": "t1", "Subject": "A"}, {"Id": "t2", "Subject": "B"}]
        tasks, _ = _make_tasks(task_data)
        result = list(tasks)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["Id"], "t1")

    def test_iteration_empty(self):
        tasks, _ = _make_tasks([])
        self.assertEqual(list(tasks), [])

    def test_stop_iteration_when_exhausted(self):
        tasks, _ = _make_tasks([{"Id": "t1"}])
        next(tasks)
        with self.assertRaises(StopIteration):
            next(tasks)

    def test_refresh_reloads_tasks(self):
        tasks, mock_conn = _make_tasks([{"Id": "t1"}])
        mock_conn.get_json.return_value = {
            "Task": [{"Id": "t2"}, {"Id": "t3"}],
            "Count": 2,
            "TimeStamp": "/Date(1705276800000)/",
            "Links": [{"rel": "myTasks", "href": "/DocuWare/Platform/MyTasks"}],
        }
        tasks.refresh()
        result = list(tasks)
        self.assertEqual(len(result), 2)
        self.assertEqual(mock_conn.get_json.call_count, 2)


if __name__ == "__main__":
    unittest.main()
