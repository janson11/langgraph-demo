"""验证真实图的状态传递、执行顺序和输入边界，不调用任何模型。"""

import unittest

from day01.demo import build_graph


class Day01GraphTests(unittest.TestCase):
    def test_complete_graph_preserves_input_and_generates_report(self):
        initial = {"requirement": "  做一个助手，\n  支持审核。  "}
        result = build_graph().invoke(initial)

        self.assertEqual(result["requirement"], initial["requirement"])
        self.assertEqual(result["normalized_requirement"], "做一个助手， 支持审核。")
        self.assertEqual(result["character_count"], 12)
        self.assertIn("需求内容：做一个助手， 支持审核。", result["report"])
        self.assertIn("字符数量：12（包含空格）", result["report"])
        self.assertEqual(initial, {"requirement": "  做一个助手，\n  支持审核。  "})

    def test_snapshots_show_each_nodes_updates_in_order(self):
        snapshots = list(
            build_graph().stream({"requirement": "  ABC  "}, stream_mode="values"),
        )

        # 输入 → 整理需求 → 统计字符 → 生成摘要。
        self.assertEqual(len(snapshots), 4)
        self.assertEqual(set(snapshots[0]), {"requirement"})
        self.assertEqual(snapshots[1]["normalized_requirement"], "ABC")
        self.assertNotIn("character_count", snapshots[1])
        self.assertEqual(snapshots[2]["character_count"], 3)
        self.assertNotIn("report", snapshots[2])
        self.assertIn("report", snapshots[3])

    def test_independent_invocations_do_not_keep_previous_state(self):
        graph = build_graph()
        graph.invoke({"requirement": "第一份需求"})
        second = graph.invoke({"requirement": "ABC"})

        self.assertEqual(second["character_count"], 3)
        self.assertNotIn("第一份需求", second["report"])

    def test_blank_requirement_is_rejected(self):
        for text in ("", " \n\t "):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "需求内容不能为空"):
                    build_graph().invoke({"requirement": text})


if __name__ == "__main__":
    unittest.main()
