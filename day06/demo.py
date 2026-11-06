"""查看 SQLite 中的会话、最新状态和历史 checkpoint。"""

import argparse
from pathlib import Path

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver

from day03.demo import offline_reply
from day05.demo import build_graph


DEFAULT_DB = Path(__file__).resolve().parents[1] / "day05" / "checkpoints.sqlite"


def thread_counts(saver: SqliteSaver) -> dict[str, int]:
    counts: dict[str, int] = {}
    for checkpoint in saver.list(None):
        thread_id = checkpoint.config["configurable"]["thread_id"]
        counts[thread_id] = counts.get(thread_id, 0) + 1
    return counts


def print_snapshot(snapshot) -> None:
    info = snapshot.config["configurable"]
    parent_id = (
        snapshot.parent_config["configurable"]["checkpoint_id"]
        if snapshot.parent_config else None
    )
    print(f"checkpoint_id：{info['checkpoint_id']}")
    print(f"parent_checkpoint_id：{parent_id or '无'}")
    print(f"step：{snapshot.metadata.get('step', '未知')}；source：{snapshot.metadata.get('source', '未知')}")
    print(f"下一节点：{', '.join(snapshot.next) if snapshot.next else '结束'}")
    messages = snapshot.values.get("messages", [])
    print(f"消息状态（共 {len(messages)} 条）：")
    for index, message in enumerate(messages, start=1):
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = ", ".join(call["name"] for call in message.tool_calls)
            print(f"  {index}. ai: 请求工具 {calls}")
        else:
            print(f"  {index}. {message.type}: {message.content}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="要查看的 SQLite 数据库路径")
    parser.add_argument("--thread-id", default="demo", help="要查看的会话 ID")
    parser.add_argument("--limit", type=int, default=10, help="最多列出多少条历史 checkpoint")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--threads", action="store_true", help="列出数据库中的会话及 checkpoint 数量")
    mode.add_argument("--checkpoint-id", help="查看指定的历史 checkpoint")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit 必须大于 0")
    if not args.thread_id.strip():
        parser.error("thread_id 不能为空")
    if not args.db.is_file():
        parser.error(f"数据库不存在：{args.db}；请先运行 day05 示例")

    config = {"configurable": {"thread_id": args.thread_id}}
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        print(f"数据库：{args.db.resolve()}")
        if args.threads:
            counts = thread_counts(saver)
            if not counts:
                print("数据库中没有会话。")
            for thread_id, count in sorted(counts.items()):
                print(f"{thread_id}：{count} 条 checkpoint")
            return

        graph = build_graph(RunnableLambda(offline_reply), checkpointer=saver)
        print(f"会话 ID：{args.thread_id}")
        if args.checkpoint_id:
            selected = {
                "configurable": {"thread_id": args.thread_id, "checkpoint_id": args.checkpoint_id},
            }
            if saver.get_tuple(selected) is None:
                parser.error("指定会话中没有这个 checkpoint_id")
            print_snapshot(graph.get_state(selected))
            return

        if saver.get_tuple(config) is None:
            print("该会话没有保存的 checkpoint。")
            return
        print("\n最新状态：")
        print_snapshot(graph.get_state(config))
        print(f"\n最近 {args.limit} 条 checkpoint（新到旧）：")
        for snapshot in graph.get_state_history(config, limit=args.limit):
            checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
            step = snapshot.metadata.get("step", "未知")
            source = snapshot.metadata.get("source", "未知")
            next_nodes = ",".join(snapshot.next) if snapshot.next else "结束"
            message_count = len(snapshot.values.get("messages", []))
            print(f"  {checkpoint_id}  step={step}  source={source}  消息={message_count}  next={next_nodes}")


if __name__ == "__main__":
    main()
