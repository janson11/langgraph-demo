"""从第 7 天已批准的报告恢复失败任务，并验证发布写入幂等。"""

import argparse
import hashlib
import sqlite3
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.tools import tool
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from day03.demo import lookup_requirement_note
from day07.demo import build_graph as build_review_graph


DEFAULT_DB = Path(__file__).resolve().parents[1] / "day07" / "checkpoints.sqlite"


def publish_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": f"day08:{thread_id}"}}


class PublishState(TypedDict, total=False):
    thread_id: str
    requirement: str
    final_report: str
    publication_key: str
    checked_note: str
    published: bool


def publication_key(thread_id: str, report: str) -> str:
    digest = hashlib.sha256(report.encode("utf-8")).hexdigest()
    return f"{thread_id}:{digest}"


def ensure_publications_table(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS published_reports ("
            "publication_key TEXT PRIMARY KEY, thread_id TEXT NOT NULL, report TEXT NOT NULL)"
        )


def published_rows(database: Path, thread_id: str) -> list[tuple[str, str]]:
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT publication_key, report FROM published_reports WHERE thread_id = ? "
            "ORDER BY publication_key",
            (thread_id,),
        ).fetchall()


def build_graph(checkpointer, database: Path, *, fail_at: Literal["tool", "after-write"] | None = None):
    @tool("lookup_requirement_note")
    def failing_lookup(topic: str) -> str:
        """模拟资料服务在查询时抛出异常。"""
        raise RuntimeError("模拟资料工具异常")

    def check_source(state: PublishState) -> PublishState:
        lookup = failing_lookup if fail_at == "tool" else lookup_requirement_note
        note = lookup.invoke({"topic": state["requirement"]})
        return {"checked_note": note}

    def publish(state: PublishState) -> PublishState:
        with sqlite3.connect(database) as connection:
            cursor = connection.execute(
                "INSERT INTO published_reports (publication_key, thread_id, report) "
                "VALUES (?, ?, ?) ON CONFLICT(publication_key) DO NOTHING",
                (state["publication_key"], state["thread_id"], state["final_report"]),
            )
        print("publish 节点：" + ("新增发布记录" if cursor.rowcount else "命中幂等键，跳过重复写入"))
        if fail_at == "after-write":
            raise RuntimeError("模拟外部写入成功后节点失败")
        return {"published": True}

    builder = StateGraph(PublishState)
    builder.add_node("check_source", check_source)
    builder.add_node("publish", publish)
    builder.add_edge(START, "check_source")
    builder.add_edge("check_source", "publish")
    return builder.compile(checkpointer=checkpointer)


def approved_report(saver: SqliteSaver, thread_id: str) -> dict:
    state = build_review_graph(saver).get_state({"configurable": {"thread_id": thread_id}}).values
    if state.get("status") != "approved" or not state.get("final_report"):
        raise ValueError("第 7 天的该会话尚无已批准报告")
    return {
        "thread_id": thread_id,
        "requirement": state["requirement"],
        "final_report": state["final_report"],
        "publication_key": publication_key(thread_id, state["final_report"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="第 7 天的 SQLite 数据库")
    parser.add_argument("--thread-id", default="demo", help="已批准报告的会话 ID")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start", action="store_true", help="开始发布已批准的报告")
    mode.add_argument("--retry", action="store_true", help="从失败的节点继续")
    mode.add_argument("--show", action="store_true", help="查看状态和发布记录")
    parser.add_argument("--fail-at", choices=("tool", "after-write"), help="本次运行中模拟故障")
    args = parser.parse_args()
    if not args.thread_id.strip():
        parser.error("thread_id 不能为空")
    if args.fail_at and args.show:
        parser.error("--fail-at 只能与 --start 或 --retry 一起使用")
    if not args.db.is_file():
        parser.error(f"数据库不存在：{args.db}；请先运行 day07 示例")

    config = publish_config(args.thread_id)
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        graph = build_graph(saver, args.db, fail_at=args.fail_at)
        existing = saver.get_tuple(config) is not None
        if args.start:
            if existing:
                parser.error("发布流程已创建；请使用 --retry 或 --show")
            try:
                initial = approved_report(saver, args.thread_id)
            except ValueError as exc:
                parser.error(str(exc))
            ensure_publications_table(args.db)
            run_input = initial
        elif args.retry:
            if not existing or not graph.get_state(config).next:
                parser.error("当前会话没有待恢复的发布节点")
            run_input = None
        else:
            if not existing:
                parser.error("当前会话没有发布状态")
            run_input = None

        failed = False
        if args.start or args.retry:
            try:
                graph.invoke(run_input, config=config)
            except Exception as exc:
                failed = True
                print(f"本次执行失败：{exc}")

        snapshot = graph.get_state(config)
        print(f"会话 ID：{args.thread_id}")
        print(f"下一节点：{', '.join(snapshot.next) if snapshot.next else '结束'}")
        print(f"图状态 published：{snapshot.values.get('published', False)}")
        rows = published_rows(args.db, args.thread_id)
        print(f"发布记录：{len(rows)} 条")
        for key, _ in rows:
            print(f"  {key}")
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
