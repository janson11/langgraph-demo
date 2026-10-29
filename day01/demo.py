"""运行 python -m day01.demo --steps，观察状态经过三个节点的变化。"""

import argparse
from pprint import pprint

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class RequirementState(TypedDict, total=False):
    """State 是节点之间传递的数据；字段会在执行过程中逐步补齐。"""

    requirement: str
    normalized_requirement: str
    character_count: int
    report: str


def normalize_requirement(state: RequirementState) -> RequirementState:
    """节点一：合并多余空白，返回本节点更新的字段。"""
    normalized = " ".join(state["requirement"].split())
    if not normalized:
        raise ValueError("需求内容不能为空或只有空白字符")
    # 无需返回整个 State，也不要直接修改传入的 state。
    return {"normalized_requirement": normalized}


def count_characters(state: RequirementState) -> RequirementState:
    """节点二：读取上一个节点写入的字段，统计字符数（包含空格）。"""
    return {"character_count": len(state["normalized_requirement"])}


def generate_report(state: RequirementState) -> RequirementState:
    """节点三：读取前两个节点的结果，用固定模板生成摘要。"""
    return {
        "report": (
            "需求摘要\n"
            f"需求内容：{state['normalized_requirement']}\n"
            f"字符数量：{state['character_count']}（包含空格）\n"
            "处理方式：普通 Python 函数与固定模板"
        ),
    }


def build_graph():
    """注册节点、连接边，再将图编译成可以执行的对象。"""
    builder = StateGraph(RequirementState)

    # Node：字符串是节点名，函数是该节点要执行的逻辑。
    builder.add_node("normalize", normalize_requirement)
    builder.add_node("count", count_characters)
    builder.add_node("report", generate_report)

    # Edge：指定执行顺序。START 和 END 是框架提供的起止标记。
    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "count")
    builder.add_edge("count", "report")
    builder.add_edge("report", END)

    # compile 只构建可执行图；invoke 或 stream 才会开始执行节点。
    return builder.compile()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirement",
        default="  做一个需求分析助手，   支持人工审核。  ",
        help="待处理的需求文本",
    )
    parser.add_argument("--steps", action="store_true", help="逐步打印完整状态快照")
    args = parser.parse_args()
    if not args.requirement.strip():
        parser.error("需求内容不能为空或只有空白字符")

    graph = build_graph()
    initial_state: RequirementState = {"requirement": args.requirement}

    if args.steps:
        # values 包含输入状态和每个执行步骤完成后的完整状态。
        # 这条路径只运行一次图，不会先 stream 再重复 invoke。
        for index, snapshot in enumerate(graph.stream(initial_state, stream_mode="values")):
            label = "输入状态" if index == 0 else f"第 {index} 个节点执行后的状态"
            print(f"\n--- {label} ---")
            pprint(snapshot, sort_dicts=False)
        result = snapshot
    else:
        # invoke 一次执行完整张图，返回最终状态。
        result = graph.invoke(initial_state)
        print("最终状态：")
        pprint(result, sort_dicts=False)

    print(f"\n{result['report']}")


if __name__ == "__main__":
    main()
