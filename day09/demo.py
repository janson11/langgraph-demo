"""沿 day07 报告审核图追踪节点更新、状态合并和执行入口。"""

import argparse

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from day07.demo import build_graph


def describe_value(key: str, value: object) -> str:
    if key in ("draft", "final_report") and isinstance(value, str):
        return value.splitlines()[0]
    return str(value)


def trace_run(graph, config: dict, value: dict | Command, previous: dict) -> dict:
    current = previous.copy()
    for mode, event in graph.stream(value, config=config, stream_mode=["updates", "values"]):
        if mode == "updates":
            for node, update in event.items():
                if node == "__interrupt__":
                    print("  review 调用 interrupt，等待人工审核")
                elif isinstance(update, dict):
                    print(f"  节点 {node} 返回字段：{', '.join(update)}")
        else:
            state = {key: item for key, item in event.items() if key != "__interrupt__"}
            changes = {key: item for key, item in state.items() if key not in current or current[key] != item}
            for key, item in changes.items():
                print(f"    合并后 {key} = {describe_value(key, item)}")
            current = state
    snapshot = graph.get_state(config)
    print(f"  checkpoint 下一节点：{', '.join(snapshot.next) if snapshot.next else '结束'}")
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement", default="报告输出前需要人工审核", help="待分析的需求")
    parser.add_argument("--feedback", default="补充验收标准", help="第一次审核的退回意见")
    args = parser.parse_args()
    if not args.requirement.strip() or not args.feedback.strip():
        parser.error("需求和退回意见不能为空")

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "day09-trace"}}
    print(f"编译结果：{type(graph).__name__}")

    print("\n第 1 次运行：提交需求")
    state = trace_run(graph, config, {"requirement": args.requirement.strip()}, {})

    print("\n第 2 次运行：退回草稿")
    state = trace_run(
        graph,
        config,
        Command(resume={"action": "reject", "feedback": args.feedback.strip()}),
        state,
    )

    print("\n第 3 次运行：通过新版草稿")
    state = trace_run(graph, config, Command(resume={"action": "approve"}), state)
    print(f"\n最终结果：第 {state['revision']} 版，状态 {state['status']}")
    print(f"最终报告与草稿一致：{state['final_report'] == state['draft']}")


if __name__ == "__main__":
    main()
