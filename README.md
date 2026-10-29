# langgraph-demo

LangGraph 学习与源码研究。通过一个需求分析助手，掌握状态传递、工具调用、持久化、人工审核与中断恢复，并沿运行路径阅读核心源码。

## 按天分包的学习 DEMO

每天的示例放在独立的 `dayXX` Python 包中，每个包包含当天代码、说明和验证用例，方便分别运行与学习。

```text
langgraph-demo/
├── requirements.txt
├── README.md
└── day01/
    ├── __init__.py
    ├── demo.py
    ├── test_demo.py
    └── README.md
```

| 天数 | 内容 | 学习入口 | 运行命令 |
| --- | --- | --- | --- |
| 第 1 天 | State、Node、Edge 与普通函数节点 | [day01 学习说明](day01/README.md) | `python -m day01.demo --steps` |

### 安装与运行

在本项目根目录使用独立的 Python 3.12 虚拟环境并安装依赖，首次安装需要网络。若 `.venv` 已创建，跳过创建环境这一步：

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

python -m day01.demo
python -m day01.demo --steps --requirement "  ABC   DEF  "
python -m unittest day01.test_demo -v
```

不激活环境时，也可以直接使用本项目的解释器：

```bash
.venv/bin/python -m day01.demo --steps
.venv/bin/python -m unittest day01.test_demo -v
```

第 1 天运行时不调用模型，无需 API Key。PyCharm 中选择 `Python 3.12 (langgraph-demo)`，解释器路径为项目下的 `.venv/bin/python`，直接运行 `day01/demo.py` 即可。学习源码时，可另外打开相邻的 `langgraph` 项目。

## 学习安排

- 学习周期：两周，每周一至周五。
- 每天投入：1～2 小时，共 10 个学习日，预计 10～20 小时。
- 周六、周日休息；未完成的任务顺延到下一个工作日。
- 学习顺序：先跑通示例，再扩展能力，最后沿示例追踪源码。

## 统一练习案例

实现一个需求分析助手，逐步接通以下流程：

```text
输入需求 → 读取资料 → 生成分析报告 → 人工审核 → 输出最终报告
                             ↑            │
                             └── 退回并附修改意见 ──┘
```

输入为一份需求描述和一组固定资料。分析报告包含需求摘要、关键约束、待澄清问题、分析建议和资料依据。人工审核通过后输出最终报告；退回时携带修改意见重新分析。

第一周逐步搭建流程，第二周完善持久化、恢复、异常处理与源码梳理。后续学习 AgentScope 和 CrewAI 时复用相同的资料、工具与报告格式，方便比较。

## 第 1 周 LangGraph 入门

目标：理解 State、Node、Edge，搞懂一次请求如何经过各节点，以及状态如何被更新。

| 时间 | 学习内容 | 完成标准 |
| --- | --- | --- |
| 周一 第 1 天 | 跑通最小示例，理解 State、Node、Edge；先用普通函数，不依赖模型。 | 能解释输入经过哪些节点，以及最终得到什么输出。 |
| 周二 第 2 天 | 接入模型，实现连续对话，观察消息状态的累积。 | 同一会话中，助手能记住此前的对话内容。 |
| 周三 第 3 天 | 添加自定义工具和条件分支。 | 助手能选择调用工具或直接回答。 |
| 周四 第 4 天 | 接入 SQLite checkpoint，理解 thread_id 与会话持久化。 | 重启程序后，能用同一 thread_id 继续原来的会话。 |
| 周五 第 5 天 | 体验人工确认与中断恢复，画出本周示例的执行流程。 | 工具执行前暂停，确认后继续；能说明状态的更新过程。 |

本周以跑通为主，第二周深化持久化、恢复与异常场景，并梳理核心源码。

## 第 2 周 LangGraph 工程能力

目标：将第一周的演示完善为可恢复、可审核的需求分析流程，并沿运行路径阅读源码。

| 时间 | 学习内容 | 完成标准 |
| --- | --- | --- |
| 周一 第 6 天 | 完善 SQLite checkpoint，检查会话隔离与历史状态。 | 重启后能恢复原会话，使用不同 thread_id 时状态互不混淆，并能查看历史状态。 |
| 周二 第 7 天 | 完善人工审核环节，处理通过、修改意见和退回。 | 审核通过后输出报告，退回后携带意见重新分析。 |
| 周三 第 8 天 | 检查重复执行、节点失败和工具异常；为外部写入设计幂等处理。 | 故意触发一次失败，恢复后检查是否产生重复副作用。 |
| 周四 第 9 天 | 沿示例追踪 StateGraph、compile、invoke 或 stream 及状态合并。 | 能定位构图入口、执行入口和关键状态更新逻辑。 |
| 周五 第 10 天 | 整理运行说明、状态字段和流程图，完整演示案例。 | 能演示重启续接与人工审核，并用自己的话讲清执行过程。 |

## 每天如何安排

1. 用约 10 分钟回顾前一天的内容，确定当天要回答的问题。
2. 用 40～80 分钟编码和运行，观察节点执行、工具调用和状态变化。
3. 用 10～20 分钟记录执行结果、关键概念和遗留问题。

## 源码阅读方法

源码先沿跑通的例子读，按以下顺序追踪：

```text
示例入口 → 核心 API → 执行循环 → 状态与消息更新 → 工具调用 → 持久化与恢复
```

每次只回答一个具体问题，并记录对应文件、函数和调用关系，例如：

- StateGraph 如何记录节点与边，compile 后得到什么可执行对象？
- invoke 或 stream 如何触发节点执行？
- 节点返回的状态如何与现有状态合并，消息如何累积？
- 条件分支如何决定调用工具还是直接结束？
- checkpoint 保存哪些信息，thread_id 如何关联会话？
- 人工审核在哪里暂停，恢复时从哪里继续，哪些逻辑可能再次执行？

## 两周结束时的交付物

- 一个能读取资料、生成分析报告并接受人工审核的需求分析助手。
- 可演示的会话持久化、重启续接与中断恢复流程。
- 一份包含依赖版本、启动方式、会话标识和操作步骤的运行说明。
- 一张执行流程图，以及状态字段、关键函数和调用关系的源码笔记。

## 学习资料

- [LangGraph 官方概览](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph 快速开始](https://docs.langchain.com/oss/python/langgraph/quickstart)
- [持久化](https://docs.langchain.com/oss/python/langgraph/persistence)
- [中断与恢复](https://docs.langchain.com/oss/python/langgraph/interrupts)
