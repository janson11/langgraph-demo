"""用真实 LangGraph 和可记录输入的替身模型验证消息历史，无需联网。"""

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph.message import add_messages

from day02.demo import SYSTEM_PROMPT, ChatSession, build_graph, create_model


class Day02GraphTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def reply(messages):
            self.calls.append(messages)
            return AIMessage(content=f"回复 {len(self.calls)}")

        self.graph = build_graph(RunnableLambda(reply))

    def test_second_turn_receives_history_and_accumulates_four_messages(self):
        session = ChatSession(self.graph)
        session.send("项目代号是小星")
        response = session.send("项目代号是什么？")

        self.assertEqual(response.content, "回复 2")
        self.assertEqual(
            [message.type for message in session.state["messages"]],
            ["human", "ai", "human", "ai"],
        )
        self.assertEqual(
            [message.content for message in self.calls[1]],
            [SYSTEM_PROMPT, "项目代号是小星", "回复 1", "项目代号是什么？"],
        )
        self.assertEqual(sum(m.type == "system" for m in self.calls[1]), 1)

    def test_separate_sessions_and_clear_do_not_leak_history(self):
        first = ChatSession(self.graph)
        first.send("第一份需求")
        second = ChatSession(self.graph)
        second.send("另一份需求")
        self.assertEqual(len(second.state["messages"]), 2)
        self.assertEqual([m.content for m in self.calls[1]], [SYSTEM_PROMPT, "另一份需求"])
        first.clear()
        first.send("重新开始")
        self.assertEqual([m.content for m in self.calls[2]], [SYSTEM_PROMPT, "重新开始"])

    def test_direct_invocations_do_not_automatically_share_history(self):
        self.graph.invoke({"messages": [HumanMessage(content="第一次调用")]})
        self.graph.invoke({"messages": [HumanMessage(content="第二次调用")]})
        self.assertEqual([m.content for m in self.calls[1]], [SYSTEM_PROMPT, "第二次调用"])

    def test_failed_turn_preserves_previous_history(self):
        def reply(messages):
            if messages[-1].content == "触发失败":
                raise RuntimeError("模拟模型失败")
            return AIMessage(content="成功")

        session = ChatSession(build_graph(RunnableLambda(reply)))
        session.send("已成功的一轮")
        previous = list(session.state["messages"])
        with self.assertRaises(RuntimeError):
            session.send("触发失败")
        self.assertEqual(session.state["messages"], previous)

    def test_blank_input_does_not_call_model(self):
        session = ChatSession(self.graph)
        for text in ("", " \n\t "):
            with self.subTest(text=text), self.assertRaises(ValueError):
                session.send(text)
        self.assertEqual(self.calls, [])

    def test_same_message_id_updates_instead_of_appending(self):
        old = AIMessage(content="原回复", id="reply-1")
        replacement = AIMessage(content="修正回复", id="reply-1")
        merged = add_messages([old], [replacement])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].content, "修正回复")


class Day02ModelConfigTests(unittest.TestCase):
    def test_invalid_headers_are_rejected_without_exposing_values(self):
        for name, invalid_value in (
            ("ARK_API_KEY", "中文密钥占位值"),
            ("ARK_API_KEY", "test-key\ninjected"),
            ("OPENAI_API_KEY", "中文备用密钥"),
            ("OPENAI_ORG_ID", "中文组织"),
            ("OPENAI_PROJECT_ID", "test project"),
        ):
            env = {"ARK_API_KEY": "local-config-check", name: invalid_value}
            if name == "OPENAI_API_KEY":
                env.pop("ARK_API_KEY")
            with self.subTest(name=name), patch.dict("os.environ", env, clear=True), patch(
                "dotenv.load_dotenv",
            ), patch("langchain_openai.ChatOpenAI") as constructor:
                with self.assertRaises(ValueError) as caught:
                    create_model()
                self.assertIn(name, str(caught.exception))
                self.assertNotIn(invalid_value, str(caught.exception))
                constructor.assert_not_called()

    def test_valid_config_keeps_volcano_parameters(self):
        with patch.dict(
            "os.environ", {"ARK_API_KEY": "local-config-check", "MODEL_THINKING": "enabled"},
            clear=True,
        ), patch("dotenv.load_dotenv"), patch("langchain_openai.ChatOpenAI") as constructor:
            create_model()
            self.assertEqual(constructor.call_args.kwargs["model"], "deepseek-v4-1-flash-261017")
            self.assertEqual(
                constructor.call_args.kwargs["base_url"],
                "https://ark.cn-beijing.volces.com/api/v3",
            )
            self.assertEqual(constructor.call_args.kwargs["extra_body"], {"thinking": {"type": "enabled"}})


if __name__ == "__main__":
    unittest.main()
