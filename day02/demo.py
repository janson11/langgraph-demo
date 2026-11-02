"""运行 python -m day02.demo --offline --steps，观察两轮对话的消息累积。"""

import argparse
import os
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, MessagesState, StateGraph


SYSTEM_PROMPT = (
    "你是一个需求分析学习助手，请用简洁中文回答。"
    "根据当前对话历史回答问题；没有提及的信息不要编造。"
)
DEFAULT_MODEL = "deepseek-v4-1-flash-261017"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MESSAGES = (
    "我要做一个需求分析助手，项目代号是小星，关键要求是输出前必须人工审核。",
    "我刚才说的项目代号和关键要求分别是什么？",
)


def offline_reply(messages: list[BaseMessage]) -> AIMessage:
    """回显传给节点的历史，用于离线观察；这里没有调用大模型。"""
    human_messages = [message.content for message in messages if message.type == "human"]
    history = "；".join(str(text) for text in human_messages[:-1]) or "（无）"
    return AIMessage(
        content=(
            f"[离线演示：仅回显历史，不做语义分析]\n"
            f"本轮输入：{human_messages[-1]}\n此前用户输入：{history}"
        ),
    )


def create_model():
    """读取项目根目录 .env，也支持直接设置环境变量。"""
    # 延迟导入：离线演示与验证只需要第 1 天已安装的依赖。
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    api_key = os.getenv("ARK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    model_name = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or DEFAULT_BASE_URL
    thinking = os.getenv("MODEL_THINKING", "disabled").strip()
    if not api_key:
        raise ValueError(
            "请在项目根目录 .env 中配置火山方舟 ARK_API_KEY（也兼容 OPENAI_API_KEY），"
            "或使用 --offline 先验证消息传递。",
        )
    # 这些值会进入 HTTP 请求头；中文或换行会在网络请求发出前触发编码错误。
    # 只报告字段名，避免在错误提示中泄露密钥或组织标识。
    key_name = "ARK_API_KEY" if os.getenv("ARK_API_KEY", "").strip() else "OPENAI_API_KEY"
    headers = {
        key_name: api_key,
        "OPENAI_ORG_ID": os.getenv("OPENAI_ORG_ID", ""),
        "OPENAI_PROJECT_ID": os.getenv("OPENAI_PROJECT_ID", ""),
    }
    for name, value in headers.items():
        if not value.isascii() or any(not 33 <= ord(char) <= 126 for char in value):
            raise ValueError(
                f"{name} 含非 ASCII 字符、空白或控制字符；"
                "请检查 .env 和终端/PyCharm 环境变量。密钥需填写真实值，不能保留中文占位文字。",
            )
    if thinking not in ("enabled", "disabled"):
        raise ValueError("MODEL_THINKING 只能填写 enabled 或 disabled")
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=1800,
        max_retries=1,
        extra_body={"thinking": {"type": thinking}},
    )


def build_graph(model):
    """model 可以是真实聊天模型，也可以是验证时注入的 Runnable。"""

    def chat(state: MessagesState):
        # 系统提示仅在调用时添加，不反复写入会话历史。
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = model.invoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("聊天模型必须返回 AIMessage")
        # MessagesState 内置 add_messages：只返回新增回复，框架负责合并。
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("chat", chat)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()


class ChatSession:
    """由调用方保存当前会话状态；不依赖 checkpoint。"""

    def __init__(self, graph):
        self.graph = graph
        self.state: MessagesState = {"messages": []}

    def send(self, text: str) -> AIMessage:
        if not text.strip():
            raise ValueError("消息不能为空或只有空白字符")
        # 两次 invoke 不会自动共享状态，必须把上一轮结果传回去。
        # 调用成功后才替换状态，失败不会留下半轮对话。
        result = self.graph.invoke(
            {"messages": [*self.state["messages"], HumanMessage(content=text)]},
        )
        self.state = result
        return result["messages"][-1]

    def clear(self) -> None:
        self.state = {"messages": []}


def print_history(session: ChatSession) -> None:
    print(f"\n消息状态（共 {len(session.state['messages'])} 条）：")
    for index, message in enumerate(session.state["messages"], start=1):
        print(f"  {index}. {message.type}: {message.content}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="用历史回显验证流程，不调用模型")
    parser.add_argument("--steps", action="store_true", help="每轮结束后打印完整消息状态")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true", help="交互聊天；/clear 清空，/exit 退出")
    mode.add_argument("--message", action="append", help="自定义消息，可重复指定以模拟连续对话")
    args = parser.parse_args()
    if args.message and any(not text.strip() for text in args.message):
        parser.error("消息不能为空或只有空白字符")

    try:
        model = RunnableLambda(offline_reply) if args.offline else create_model()
    except (ValueError, ImportError) as exc:
        parser.exit(1, f"初始化失败：{exc}\n请先安装 requirements.txt 中的依赖并检查配置。\n")

    session = ChatSession(build_graph(model))
    print("模式：离线历史回显" if args.offline else "模式：真实模型（会产生 API 调用）")

    def send_and_print(text: str) -> bool:
        try:
            response = session.send(text)
        except UnicodeEncodeError as exc:
            print(
                f"本轮调用失败（UnicodeEncodeError，编码：{exc.encoding}），历史未更新；"
                "请检查 API Key、组织/项目标识等请求头配置是否含中文或特殊字符。"
                "中文问题可以正常发送，不必改成英文。",
            )
            return False
        except Exception as exc:
            # 不打印异常正文：部分服务会在错误中带出请求或配置内容。
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
