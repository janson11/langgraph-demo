"""验证真实 LangGraph 图的两条分支，不访问模型服务。"""

import unittest

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from day02.demo import ChatSession
from day03.demo import build_graph, offline_reply


class Day03GraphTests(unittest.TestCase):
    def setUp(self):
        self.session = ChatSession(build_graph(RunnableLambda(offline_reply)))

    def test_tool_branch_returns_tool_result_and_final_answer(self):
        answer = self.session.send("请查资料，输出报告前有什么审核要求？")
        messages = self.session.state["messages"]
        self.assertEqual([m.type for m in messages], ["human", "ai", "tool", "ai"])
        self.assertEqual(messages[1].tool_calls[0]["name"], "lookup_requirement_note")
        self.assertIsInstance(messages[2], ToolMessage)
        self.assertIn("人工审核", messages[2].content)
        self.assertEqual(answer, messages[-1])
        self.assertIn("人工审核", answer.content)

    def test_direct_answer_skips_tool(self):
        answer = self.session.send("你好，请直接回答一句问候。")
        self.assertEqual([m.type for m in self.session.state["messages"]], ["human", "ai"])
        self.assertEqual(answer.content, "你好，我是需求分析助手。")

    def test_history_is_preserved_across_both_branches(self):
        self.session.send("请查资料，输出报告前有什么审核要求？")
        self.session.send("你好，请直接回答一句问候。")
        self.assertEqual(
            [m.type for m in self.session.state["messages"]],
            ["human", "ai", "tool", "ai", "human", "ai"],
        )

    def test_unknown_topic_returns_clarification(self):
        answer = self.session.send("请查资料，预算是多少？")
        self.assertIn("没有找到", answer.content)

    def test_project_code_uses_tool(self):
        answer = self.session.send("项目代号是什么？")
        self.assertEqual([m.type for m in self.session.state["messages"]], ["human", "ai", "tool", "ai"])
        self.assertIn("小星", answer.content)

    def test_failed_tool_does_not_replace_session_history(self):
        def reply(messages):
            if messages[-1].type == "tool":
                raise RuntimeError("模拟模型失败")
            return AIMessage(content="", tool_calls=[{
                "name": "lookup_requirement_note", "args": {"topic": "审核"}, "id": "call-1",
            }])

        session = ChatSession(build_graph(RunnableLambda(reply)))
        with self.assertRaises(RuntimeError):
            session.send("请查资料")
        self.assertEqual(session.state["messages"], [])


if __name__ == "__main__":
    unittest.main()
