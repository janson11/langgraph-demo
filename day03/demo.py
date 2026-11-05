"""运行 python -m day03.demo --offline --steps，观察工具调用与直接回答。"""

import argparse

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from day02.demo import ChatSession, create_model


SYSTEM_PROMPT = (
    "你是需求分析助手。需要确认项目既有约束时，先调用 lookup_requirement_note 查询资料；"
    "普通问候或无需资料的问题直接回答。资料没有覆盖的问题不要编造。"
)
DEFAULT_MESSAGES = (
    "请查资料，输出报告前有什么审核要求？",
    "你好，请直接回答一句问候。",
)


@tool
def lookup_requirement_note(topic: str) -> str:
    """按主题查询需求分析项目的固定资料，返回已有约束或未找到提示。"""
    notes = {
        "审核": "资料：分析报告输出前必须人工审核；未经确认不能作为最终报告。",
        "代号": "资料：项目代号是小星。",
    }
    for keyword, note in notes.items():
        if keyword in topic:
            return note
    return "资料中没有找到该主题，请向用户澄清。"


def offline_reply(messages: list[BaseMessage]) -> AIMessage:
    """用固定规则模拟模型选择；不会向模型服务发送请求。"""
    if isinstance(messages[-1], ToolMessage):
        return AIMessage(content=f"根据查询结果：{messages[-1].content}")
    question = str(messages[-1].content)
    if any(keyword in question for keyword in ("资料", "审核要求", "代号")):
        return AIMessage(
            content="",
            tool_calls=[{
                "name": lookup_requirement_note.name,
                "args": {"topic": question},
                "id": "offline-lookup",
            }],
        )
    return AIMessage(content="你好，我是需求分析助手。" if "你好" in question else "请描述你的问题。")


def build_graph(model, checkpointer=None):
    """model 已绑定工具；可选 checkpointer 用于后续持久化示例。"""
    def assistant(state: MessagesState):
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = model.invoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("聊天模型必须返回 AIMessage")
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode([lookup_requirement_note]))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)
    builder.add_edge("tools", "assistant")
    return builder.compile(checkpointer=checkpointer)


def print_history(session: ChatSession) -> None:
    print(f"\n消息状态（共 {len(session.state['messages'])} 条）：")
    for index, message in enumerate(session.state["messages"], start=1):
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = ", ".join(f"{call['name']}({call['args']})" for call in message.tool_calls)
            print(f"  {index}. ai: 请求工具 {calls}")
        else:
            print(f"  {index}. {message.type}: {message.content}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="固定规则模拟工具选择，不调用模型")
    parser.add_argument("--steps", action="store_true", help="每轮结束后打印消息状态")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true", help="交互聊天；/clear 清空，/exit 退出")
    mode.add_argument("--message", action="append", help="自定义消息，可重复指定")
    args = parser.parse_args()
    if args.message and any(not value.strip() for value in args.message):
        parser.error("消息不能为空或只有空白字符")

    try:
        model = RunnableLambda(offline_reply) if args.offline else create_model().bind_tools(
            [lookup_requirement_note],
        )
    except (ValueError, ImportError) as exc:
        parser.exit(1, f"初始化失败：{exc}\n请检查依赖与模型配置，或使用 --offline。\n")
    session = ChatSession(build_graph(model))
    print("模式：离线固定规则" if args.offline else "模式：真实模型（会产生 API 调用）")

    def send_and_print(text: str) -> bool:
        try:
            response = session.send(text)
        except Exception as exc:
            print(f"本轮调用失败（{type(exc).__name__}），历史未更新；请检查模型配置与网络。")
            return False
        print(f"助手：{response.content}")
        if args.steps:
            print_history(session)
        return True

    if args.interactive:
        print("输入消息开始聊天；/clear 清空当前会话，/exit 退出。")
        while True:
            try:
                text = input("\n你：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n会话结束。")
                break
            if text == "/exit":
                break
            if text == "/clear":
                session.clear()
                print("当前会话已清空。")
            elif text:
                send_and_print(text)
    else:
        for text in args.message or DEFAULT_MESSAGES:
            print(f"\n你：{text}")
            if not send_and_print(text):
                parser.exit(1)


if __name__ == "__main__":
    main()
