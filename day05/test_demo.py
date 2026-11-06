"""验证工具调用前的人工确认与跨进程中断恢复。"""

import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from day03.demo import offline_reply
from day05.demo import build_graph, pending_calls


class Day05InterruptTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / "state.sqlite")
        self.config = {"configurable": {"thread_id": "project-a"}}
        self.tool_calls = []

        @tool("lookup_requirement_note")
        def counted_lookup(topic: str) -> str:
            """查询固定资料。"""
            self.tool_calls.append(topic)
            return "资料：报告输出前必须人工审核。"

        self.lookup = counted_lookup

    def graph(self, saver):
        return build_graph(RunnableLambda(offline_reply), saver, tools=[self.lookup])

    def pause(self):
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            result = graph.invoke(
                {"messages": [HumanMessage(content="请查资料，审核要求是什么？")]},
                config=self.config,
            )
            self.assertEqual([m.type for m in result["messages"]], ["human", "ai"])
            self.assertEqual(graph.get_state(self.config).next, ("review",))
            self.assertEqual(len(pending_calls(graph, self.config)), 1)
            self.assertEqual(self.tool_calls, [])

    def test_approval_after_reopening_database_executes_tool_once(self):
        self.pause()
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            result = graph.invoke(Command(resume=True), config=self.config)
            self.assertEqual([m.type for m in result["messages"]], ["human", "ai", "tool", "ai"])
            self.assertEqual(len(self.tool_calls), 1)
            self.assertEqual(graph.get_state(self.config).next, ())

    def test_rejection_after_reopening_database_skips_tool(self):
        self.pause()
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            result = graph.invoke(Command(resume=False), config=self.config)
            self.assertEqual([m.type for m in result["messages"]], ["human", "ai", "tool", "ai"])
            self.assertIn("未查询资料", result["messages"][-2].content)
            self.assertEqual(result["messages"][-1].content, "已取消资料查询；本次未执行工具。")
            self.assertEqual(self.tool_calls, [])
            self.assertEqual(graph.get_state(self.config).next, ())

    def test_direct_answer_does_not_pause(self):
        with SqliteSaver.from_conn_string(self.database) as saver:
            graph = self.graph(saver)
            result = graph.invoke({"messages": [HumanMessage(content="你好")]}, config=self.config)
            self.assertEqual([m.type for m in result["messages"]], ["human", "ai"])
            self.assertEqual(pending_calls(graph, self.config), [])
            self.assertEqual(self.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
