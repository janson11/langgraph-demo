"""验证报告审核通过、退回修改和 SQLite 中断恢复。"""

import tempfile
import unittest
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from day07.demo import build_graph


class Day07ReviewTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / "reports.sqlite")
        self.config = {"configurable": {"thread_id": "report-a"}}

    def start_report(self):
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = build_graph(saver)
            result = graph.invoke({"requirement": "输出报告前需要审核"}, config=self.config)
            self.assertEqual(result["status"], "pending_review")
            self.assertEqual(result["revision"], 1)
            self.assertNotIn("final_report", result)
            self.assertEqual(graph.get_state(self.config).next, ("review",))

    def test_approve_after_reopening_database(self):
        self.start_report()
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = build_graph(saver)
            draft = graph.get_state(self.config).values["draft"]
            result = graph.invoke(Command(resume={"action": "approve"}), config=self.config)
            self.assertEqual(result["final_report"], draft)
            self.assertEqual(result["status"], "approved")
            self.assertEqual(result["revision"], 1)
            self.assertEqual(graph.get_state(self.config).next, ())

    def test_reject_with_feedback_revises_then_waits_for_approval(self):
        self.start_report()
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = build_graph(saver)
            first_draft = graph.get_state(self.config).values["draft"]
            result = graph.invoke(
                Command(resume={"action": "reject", "feedback": "补充验收标准"}),
                config=self.config,
            )
            self.assertEqual(result["revision"], 2)
            self.assertIn("补充验收标准", result["draft"])
            self.assertNotEqual(result["draft"], first_draft)
            self.assertEqual(result["status"], "pending_review")
            self.assertNotIn("final_report", result)
            self.assertEqual(graph.get_state(self.config).next, ("review",))

        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = build_graph(saver)
            result = graph.invoke(Command(resume={"action": "approve"}), config=self.config)
            self.assertEqual(result["final_report"], result["draft"])
            self.assertIn("补充验收标准", result["final_report"])
            self.assertEqual(result["status"], "approved")

    def test_blank_feedback_cannot_approve_or_revise(self):
        self.start_report()
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = build_graph(saver)
            with self.assertRaisesRegex(ValueError, "修改意见"):
                graph.invoke(
                    Command(resume={"action": "reject", "feedback": "  "}),
                    config=self.config,
                )
            self.assertEqual(graph.get_state(self.config).values["revision"], 1)
            self.assertEqual(graph.get_state(self.config).next, ("review",))


if __name__ == "__main__":
    unittest.main()
