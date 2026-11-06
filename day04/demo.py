"""运行 python -m day04.demo --offline --steps，观察 SQLite 会话持久化。"""

import argparse
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver

from day02.demo import create_model
from day03.demo import build_graph, lookup_requirement_note, offline_reply


DEFAULT_DB = Path(__file__).with_name("checkpoints.sqlite")


def print_state(graph, config) -> None:
    messages = graph.get_state(config).values.get("messages", [])
    print(f"消息状态（共 {len(messages)} 条）：")
    for index, message in enumerate(messages, start=1):
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = ", ".join(call["name"] for call in message.tool_calls)
            print(f"  {index}. ai: 请求工具 {calls}")
        else:
            print(f"  {index}. {message.type}: {message.content}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="用固定规则模拟模型，不访问 API")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--thread-id", default="demo", help="会话 ID；相同 ID 恢复历史")
    parser.add_argument("--steps", action="store_true", help="每轮后打印 checkpoint 中的完整消息状态")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true", help="交互聊天；/exit 退出")
    mode.add_argument("--message", action="append", help="本次发送的消息，可重复指定")
    args = parser.parse_args()
    if not args.thread_id.strip():
        parser.error("thread_id 不能为空")
    if args.message and any(not value.strip() for value in args.message):
        parser.error("消息不能为空或只有空白字符")

    try:
        model = RunnableLambda(offline_reply) if args.offline else create_model().bind_tools(
            [lookup_requirement_note],
        )
    except (ValueError, ImportError) as exc:
        parser.exit(1, f"初始化失败：{exc}\n请检查依赖与模型配置，或使用 --offline。\n")

    args.db.parent.mkdi r(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": args.thread_id}}
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        graph = build_graph(model, checkpointer=saver)
        print(f"数据库：{args.db.resolve()}")
        print(f"会话 ID：{args.thread_id}")
        print("模式：离线固定规则" if args.offline else "模式：真实模型（会产生 API 调用）")
        if args.steps:
            print("\n启动时已保存的状态：")
            print_state(graph, config)

        def send_and_print(text: str) -> bool:
            try:
                result = graph.invoke({"messages": [HumanMessage(content=text)]}, config=config)
            except Exception as exc:
                print(f"本轮调用失败（{type(exc).__name__}）；请检查配置和 checkpoint 状态。")
                return False
            print(f"助手：{result['messages'][-1].content}")
            if args.steps:
                print_state(graph, config)
            return True

        if args.interactive:
            print("输入消息开始聊天；/exit 退出。")
            while True:
                try:
                    text = input("\n你：").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n会话结束。")
                    break
                if text == "/exit":
                    break
                if text:
                    send_and_print(text)
        else:
            for text in args.message or ["请查资料，输出报告前有什么审核要求？"]:
                print(f"\n你：{text}")
                if not send_and_print(text):
                    parser.exit(1)


if __name__ == "__main__":
    main()
