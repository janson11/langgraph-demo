"""验证 SQLite 中的历史快照、重启恢复和会话隔离。"""

import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from day03.demo import offline_reply
from day05.demo import build_graph
from day06.demo import thread_counts


class Day06HistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / "history.sqlite")
        self.first = {"configurable": {"thread_id": "review-a"}}
        self.second = {"configurable": {"thread_id": "review-b"}}

    def graph(self, saver):
        return build_graph(RunnableLambda(offline_reply), checkpointer=saver)

    def test_historical_snapshot_survives_reopen_without_changing_latest(self):
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            graph.invoke(
                {"messages": [HumanMessage(content="请查资料，审核要求是什么？")]},
                config=self.first,
            )
            paused_id = graph.get_state(self.first).config["configurable"]["checkpoint_id"]
            self.assertEqual(graph.get_state(self.first).next, ("review",))

        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            self.assertEqual(graph.get_state(self.first).next, ("review",))
            graph.invoke(Command(resume=True), config=self.first)

        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            history = list(graph.get_state_history(self.first))
            self.assertGreater(len(history), 2)
            self.assertEqual(history[0].next, ())
            self.assertIn(paused_id, [item.config["configurable"]["checkpoint_id"] for item in history])
            selected = {"configurable": {"thread_id": "review-a", "checkpoint_id": paused_id}}
            old = graph.get_state(selected)
            self.assertEqual(old.next, ("review",))
            self.assertEqual(len(old.values["messages"]), 2)
            self.assertEqual(len(graph.get_state(self.first).values["messages"]), 4)
            self.assertEqual(graph.get_state(self.first).next, ())
            other_thread = {"configurable": {"thread_id": "review-b", "checkpoint_id": paused_id}}
            self.assertIsNone(saver.get_tuple(other_thread))

    def test_thread_ids_keep_independent_history(self):
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            graph.invoke({"messages": [HumanMessage(content="你好，A 会话")]}, config=self.first)
            graph.invoke({"messages": [HumanMessage(content="请描述问题，B 会话")]}, config=self.second)

        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            first_history = list(graph.get_state_history(self.first))
            second_history = list(graph.get_state_history(self.second))
            self.assertTrue(first_history)
            self.assertTrue(second_history)
            self.assertEqual(len(first_history), thread_counts(saver)["review-a"])
            self.assertEqual(len(second_history), thread_counts(saver)["review-b"])
            self.assertTrue(all(item.config["configurable"]["thread_id"] == "review-a" for item in first_history))
            self.assertTrue(all(item.config["configurable"]["thread_id"] == "review-b" for item in second_history))
            self.assertEqual(first_history[0].values["messages"][0].content, "你好，A 会话")
            self.assertEqual(second_history[0].values["messages"][0].content, "请描述问题，B 会话")
            self.assertEqual(list(graph.get_state_history({"configurable": {"thread_id": "unknown"}})), [])


if __name__ == "__main__":
    unittest.main()
