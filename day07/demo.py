"""生成需求分析报告，支持跨进程审核通过或退回修改。"""

import argparse
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from day03.demo import lookup_requirement_note


DEFAULT_DB = Path(__file__).with_name("checkpoints.sqlite")


class ReportState(TypedDict, total=False):
    requirement: str
    source_note: str
    draft: str
    revision: int
    feedback: str
    status: Literal["pending_review", "revision_requested", "approved"]
    final_report: str


def build_graph(checkpointer):
    def research(state: ReportState) -> ReportState:
        note = lookup_requirement_note.invoke({"topic": state["requirement"]})
        return {"source_note": note}

    def draft(state: ReportState) -> ReportState:
        revision = state.get("revision", 0) + 1
        feedback = state.get("feedback", "")
        questions = "具体范围和验收标准是什么？"
        advice = "先确认范围与验收标准，再安排实现和审核。"
        if feedback:
            questions += f"；审核补充要求：{feedback}"
            advice += f"针对审核意见“{feedback}”补充对应依据并复核。"
        report = (
            f"需求分析报告（第 {revision} 版）\n"
            f"需求摘要：{state['requirement']}\n"
            f"关键约束：{state['source_note']}\n"
            f"待澄清问题：{questions}\n"
            f"分析建议：{advice}"
        )
        return {"draft": report, "revision": revision, "status": "pending_review"}

    def review(state: ReportState) -> Command:
        decision = interrupt({"draft": state["draft"], "revision": state["revision"]})
        if not isinstance(decision, dict):
            raise ValueError("审核决定必须包含 action")
        if decision.get("action") == "approve":
            return Command(update={"status": "approved"}, goto="finalize")
        if decision.get("action") == "reject":
            feedback = decision.get("feedback")
            if not isinstance(feedback, str) or not feedback.strip():
                raise ValueError("退回时必须提供修改意见")
            return Command(
                update={"feedback": feedback.strip(), "status": "revision_requested"},
                goto="draft",
            )
        raise ValueError("action 必须是 approve 或 reject")

    def finalize(state: ReportState) -> ReportState:
        return {"final_report": state["draft"]}

    builder = StateGraph(ReportState)
    builder.add_node("research", research)
    builder.add_node("draft", draft)
    builder.add_node("review", review, destinations=("draft", "finalize"))
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "research")
    builder.add_edge("research", "draft")
    builder.add_edge("draft", "review")
    return builder.compile(checkpointer=checkpointer)


def print_state(graph, config) -> None:
    snapshot = graph.get_state(config)
    state = snapshot.values
    print(f"当前状态：{state.get('status', '未开始')}")
    print(f"报告版本：{state.get('revision', 0)}")
    print(f"下一节点：{', '.join(snapshot.next) if snapshot.next else '结束'}")
    if state.get("feedback"):
        print(f"最近修改意见：{state['feedback']}")
    if state.get("draft"):
        print(f"\n{state['draft']}")
    if state.get("final_report"):
        print("\n最终报告已审核通过。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--thread-id", default="demo", help="每份报告使用独立的会话 ID")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--requirement", help="创建报告，生成第 1 版草稿")
    mode.add_argument("--resume", choices=("approve", "reject"), help="恢复待审核的报告")
    mode.add_argument("--show", action="store_true", help="只查看当前状态")
    parser.add_argument("--feedback", help="退回时必填的修改意见")
    args = parser.parse_args()
    if not args.thread_id.strip():
        parser.error("thread_id 不能为空")
    if args.requirement is not None and not args.requirement.strip():
        parser.error("需求内容不能为空")
    if args.resume == "reject" and (not args.feedback or not args.feedback.strip()):
        parser.error("退回时必须用 --feedback 提供修改意见")
    if args.feedback and args.resume != "reject":
        parser.error("--feedback 仅用于 --resume reject")
    if args.show or args.resume:
        if not args.db.is_file():
            parser.error(f"数据库不存在：{args.db}")
    else:
        args.db.parent.mkdir(parents=True, exist_ok=True)

    config = {"configurable": {"thread_id": args.thread_id}}
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        graph = build_graph(saver)
        existing = saver.get_tuple(config) is not None
        if args.requirement is not None:
            if existing:
                parser.error("该 thread_id 已有报告；请审核现有草稿或使用新的 thread_id")
            graph.invoke({"requirement": args.requirement.strip()}, config=config)
        elif args.resume:
            if not existing or "review" not in graph.get_state(config).next:
                parser.error("当前会话没有待审核的报告")
            decision = {"action": args.resume}
            if args.resume == "reject":
                decision["feedback"] = args.feedback.strip()
            graph.invoke(Command(resume=decision), config=config)
        elif not existing:
            parser.error("该会话没有保存的报告")

        print(f"数据库：{args.db.resolve()}")
        print(f"会话 ID：{args.thread_id}")
        print_state(graph, config)


if __name__ == "__main__":
    main()
