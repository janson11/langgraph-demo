# 第 9 天 沿运行路径读 LangGraph 源码

本例复用 day07 的报告审核图，按“提交需求 → 退回草稿 → 审核通过”运行一次完整流程。`stream_mode=["updates", "values"]` 同时显示节点返回的局部更新与合并后的完整状态；每次运行结束用 `get_state()` 显示 checkpoint 的下一节点。示例使用内存 checkpointer，只用于观察本次运行；跨进程恢复仍看 day07、day08。

在 `langgraph-demo` 根目录直接运行：

```bash
.venv/bin/python -m day09.demo
.venv/bin/python -m day09.demo --requirement "项目代号需要写入报告" --feedback "补充项目代号依据"
```

第一次运行应停在 `review`；退回后 `feedback` 写入状态，`draft` 和 `revision` 更新，再次停在 `review`；批准后 `finalize` 写入 `final_report`，下一节点显示“结束”。留意 `research` 只返回 `source_note`，但合并后的状态仍保留 `requirement`；`draft` 节点只更新报告相关字段。

## 源码阅读顺序

下面路径指向本项目旁边的 `langgraph` 源码仓库，版本应与环境中的 `langgraph==1.2.16` 一致。

| 运行时观察 | 示例入口 | LangGraph 源码入口 |
| --- | --- | --- |
| 注册节点和边 | [day07 `build_graph`](../day07/demo.py) | [`StateGraph.add_node` / `add_edge`](../../langgraph/libs/langgraph/langgraph/graph/state.py) |
| 得到 `CompiledStateGraph` | [day07 `builder.compile`](../day07/demo.py) | [`StateGraph.compile`](../../langgraph/libs/langgraph/langgraph/graph/state.py) |
| 调用 `stream`，按步执行 | [day09 `trace_run`](demo.py) | [`Pregel.stream` / `invoke`](../../langgraph/libs/langgraph/langgraph/pregel/main.py)、[`PregelLoop.tick`](../../langgraph/libs/langgraph/langgraph/pregel/_loop.py) |
| 节点返回局部字段，状态保留其他字段 | [day07 `research` / `draft`](../day07/demo.py) | [`apply_writes`](../../langgraph/libs/langgraph/langgraph/pregel/_algo.py)、[`LastValue.update`](../../langgraph/libs/langgraph/langgraph/channels/last_value.py) |
| 审核暂停及恢复 | [day07 `review`](../day07/demo.py) | [`interrupt` / `Command`](../../langgraph/libs/langgraph/langgraph/types.py) |

阅读时在 IDE 中给 `day07.build_graph`、`StateGraph.compile`、`Pregel.stream`、`PregelLoop.tick`、`apply_writes` 依次下断点。`invoke()` 内部也会遍历 `stream()`；本例直接用 `stream()`，方便观察每一步。day07 的普通状态字段默认使用 `LastValue`，新值覆盖同名字段；day02、day03 的 `MessagesState` 则通过 [`add_messages`](../../langgraph/libs/langgraph/langgraph/graph/message.py) 合并消息列表。
