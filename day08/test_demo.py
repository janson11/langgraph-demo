"""验证工具失败、写入后失败及跨连接重试不会重复发布。"""

import tempfile
import unittest
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from day07.demo import build_graph as build_review_graph
from day08.demo import (
    approved_report,
    build_graph,
    ensure_publications_table,
    publish_config,
    published_rows,
)


class Day08RecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "demo.sqlite"
        self.thread_id = "report-a"
        self.config = publish_config(self.thread_id)
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            review = build_review_graph(saver)
            review.invoke({"requirement": "报告输出前审核"}, config={"configurable": {"thread_id": self.thread_id}})
            review.invoke(Command(resume={"action": "approve"}), config={"configurable": {"thread_id": self.thread_id}})
        ensure_publications_table(self.database)

    def start(self, fail_at):
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            initial = approved_report(saver, self.thread_id)
            graph = build_graph(saver, self.database, fail_at=fail_at)
            with self.assertRaises(RuntimeError):
                graph.invoke(initial, config=self.config)
            return graph.get_state(self.config)

    def test_tool_failure_retries_without_publishing_early(self):
        snapshot = self.start("tool")
        self.assertEqual(snapshot.next, ("check_source",))
        self.assertEqual(published_rows(self.database, self.thread_id), [])
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            graph = build_graph(saver, self.database)
            result = graph.invoke(None, config=self.config)
            self.assertTrue(result["published"])
            self.assertEqual(len(published_rows(self.database, self.thread_id)), 1)
            self.assertEqual(graph.get_state(self.config).next, ())

    def test_write_then_failure_retries_without_duplicate_record(self):
        snapshot = self.start("after-write")
        self.assertEqual(snapshot.next, ("publish",))
        self.assertFalse(snapshot.values.get("published", False))
        first_rows = published_rows(self.database, self.thread_id)
        self.assertEqual(len(first_rows), 1)
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            graph = build_graph(saver, self.database)
            result = graph.invoke(None, config=self.config)
            self.assertTrue(result["published"])
            self.assertEqual(published_rows(self.database, self.thread_id), first_rows)
            self.assertEqual(graph.get_state(self.config).next, ())


if __name__ == "__main__":
    unittest.main()
