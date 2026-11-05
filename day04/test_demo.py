"""用真实 SQLite 文件验证会话恢复和 thread_id 隔离。"""

import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver

from day03.demo import build_graph, offline_reply


class Day04CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / "state.sqlite")

    def graph(self, saver):
        return build_graph(RunnableLambda(offline_reply), checkpointer=saver)

    def test_same_thread_recovers_history_after_reopening_database(self):
        config = {"configurable": {"thread_id": "project-a"}}
        with SqliteSaver.from_conn_string(self.database) as saver:
            first = self.graph(saver).invoke(
                {"messages": [HumanMessage(content="请查资料，审核要求是什么？")]}, config=config,
            )
            self.assertEqual([m.type for m in first["messages"]], ["human", "ai", "tool", "ai"])

        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            restored = graph.get_state(config).values["messages"]
            self.assertEqual(len(restored), 4)
            second = graph.invoke(
                {"messages": [HumanMessage(content="你好")]}, config=config,
            )
            self.assertEqual([m.type for m in second["messages"]], ["human", "ai", "tool", "ai", "human", "ai"])

        with SqliteSaver.from_conn_string(self.database) as saver:
            self.assertEqual(len(self.graph(saver).get_state(config).values["messages"]), 6)

    def test_different_thread_id_starts_with_empty_state(self):
        first_config = {"configurable": {"thread_id": "project-a"}}
        other_config = {"configurable": {"thread_id": "project-b"}}
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            graph.invoke({"messages": [HumanMessage(content="你好")]}, config=first_config)
            self.assertEqual(graph.get_state(other_config).values, {})
            other = graph.invoke({"messages": [HumanMessage(content="请描述问题")]}, config=other_config)
            self.assertEqual(len(other["messages"]), 2)
            self.assertEqual(len(graph.get_state(first_config).values["messages"]), 2)


if __name__ == "__main__":
    unittest.main()
