"""在工具调用前人工确认，并用 SQLite 恢复中断的会话。"""

import argparse
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt

from day02.demo import create_model
from day03.demo import SYSTEM_PROMPT, lookup_requirement_note, offline_reply


DEFAULT_DB = Path(__file__).with_name("checkpoints.sqlite")
DENIED_MESSAGE = "用户拒绝了本次工具调用；未查询资料。"


def build_graph(model, checkpointer, tools=None):
    """工具调用必须先通过 review 节点。"""
    tools = tools or [lookup_requirement_note]

    def assistant(state: MessagesState):
        if isinstance(state["messages"][-1], ToolMessage) and state["messages"][-1].content == DENIED_MESSAGE:
            return {"messages": [AIMessage(content="已取消资料查询；本次未执行工具。")]}
        response = model.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        if not isinstance(response, AIMessage):
            raise TypeError("聊天模型必须返回 AIMessage")
        return {"messages": [response]}

    def review(state: MessagesState) -> Command:
        calls = state["messages"][-1].tool_calls
        approved = interrupt({"tool_calls": calls})
        if approved is True:
            return Command(goto="tools")
        denied = [
            ToolMessage(
                content=DENIED_MESSAGE,
                tool_call_id=call["id"],
                name=call["name"],
            )
            for call in calls
        ]
        return Command(update={"messages": denied}, goto="assistant")

    def after_assistant(state: MessagesState) -> str:
        return "review" if tools_condition(state) == "tools" else "__end__"

    builder = StateGraph(MessagesState)
    builder.add_node("assistant", assistant)
    builder.add_node("review", review, destinations=("tools", "assistant"))
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", after_assistant)
    builder.add_edge("tools", "assistant")
    return builder.compile(checkpointer=checkpointer)


def pending_calls(graph, config) -> list[dict]:
    state = graph.get_state(config)
    if "review" not in state.next:
        return []
    return state.values["messages"][-1].tool_calls


def print_state(graph, config) -> None:
    state = graph.get_state(config)
    messages = state.values.get("messages", [])
    print(f"消息状态（共 {len(messages)} 条）：")
    for index, message in enumerate(messages, start=1):
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = ", ".join(call["name"] for call in message.tool_calls)
            print(f"  {index}. ai: 请求工具 {calls}")
        else:
            print(f"  {index}. {message.type}: {message.content}")
    print(f"下一节点：{', '.join(state.next) if state.next else '结束'}")


def print_result(graph, config, result, steps: bool) -> None:
    calls = pending_calls(graph, config)
    if calls:
        print("等待人工确认，工具尚未执行：")
        for call in calls:
            print(f"  {call['name']}({call['args']})")
        print("使用相同 --db 和 --thread-id，运行 --resume approve 或 --resume reject。")
    else:
        print(f"助手：{result['messages'][-1].content}")
    if steps:
        print_state(graph, config)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="固定规则模拟模型，不访问 API")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--thread-id", default="demo", help="会话 ID；相同 ID 恢复中断")
    parser.add_argument("--steps", action="store_true", help="打印 checkpoint 中的消息和下一节点")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--message", action="append", help="发送新消息，可重复指定")
    mode.add_argument("--resume", choices=("approve", "reject"), help="恢复当前待确认的工具调用")
    mode.add_argument("--interactive", action="store_true", help="交互聊天；/exit 退出")
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

    args.db.parent.mkdir(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": args.thread_id}}
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        graph = build_graph(model, checkpointer=saver)
        print(f"数据库：{args.db.resolve()}")
        print(f"会话 ID：{args.thread_id}")
        if args.steps:
            print_state(graph, config)

        def run(value) -> None:
            result = graph.invoke(value, config=config)
            print_result(graph, config, result, args.steps)

        if args.resume:
            if not pending_calls(graph, config):
                parser.error("当前会话没有待确认的工具调用")
            run(Command(resume=args.resume == "approve"))
        elif args.interactive:
            print("输入消息开始聊天；工具确认输入 approve/reject，/exit 可稍后恢复。")
            while True:
                try:
                    calls = pending_calls(graph, config)
                    if calls:
                        print("待确认工具：" + ", ".join(call["name"] for call in calls))
                    text = input("确认 [approve/reject]：" if calls else "\n你：").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n会话结束。")
                    break
                if text == "/exit":
                    break
                if calls:
                    if text in ("approve", "reject"):
                        run(Command(resume=text == "approve"))
                    else:
                        print("请输入 approve、reject 或 /exit。")
                elif text:
                    run({"messages": [HumanMessage(content=text)]})
        else:
            if pending_calls(graph, config):
                parser.error("当前会话仍待确认；请先使用 --resume approve 或 --resume reject")
            messages = args.message or ["请查资料，输出报告前有什么审核要求？"]
            for index, text in enumerate(messages):
                print(f"\n你：{text}")
                run({"messages": [HumanMessage(content=text)]})
                if pending_calls(graph, config):
                    if index + 1 < len(messages):
                        print("后续消息尚未发送；完成确认后请重新提交。")
                    break


if __name__ == "__main__":
    main()
