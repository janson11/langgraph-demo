# 第 6 天 SQLite checkpoint 历史与会话隔离

目标：区分最新状态和历史快照，查看图每一步保存的 checkpoint，并确认不同 `thread_id` 的状态互不混淆。

day06 默认查看 day05 使用的 `day05/checkpoints.sqlite`，不会调用模型或推进图。先在 `langgraph-demo` 项目根目录列出数据库中的会话：

```bash
.venv/bin/python -m day06.demo --threads
```

查看 day05 中 `review-a` 会话的最新状态和最近 10 个 checkpoint：

```bash
.venv/bin/python -m day06.demo --thread-id review-a
```

查看另一个会话（例如 `demo`）并比较两者的消息与 checkpoint；也可以使用 `--limit 5` 缩短列表。从列表中复制某个 `checkpoint_id`，读取当时的完整状态：

```bash
.venv/bin/python -m day06.demo --thread-id review-a --checkpoint-id "替换为列表中的实际 ID"
```

若要新建会话或继续对话，仍使用 day05：

```bash
.venv/bin/python -m day05.demo --offline --thread-id history-a --message "你好"
.venv/bin/python -m day06.demo --thread-id history-a
```

两个程序默认使用同一个数据库；指定其他文件时，两边都要传相同的 `--db`。不存在的数据库会报错，不会自动创建空文件。

checkpoint 不等于一条聊天消息。一次 `invoke()` 可能依次保存输入、助手输出、审核暂停、工具结果等多个快照。每条历史记录有 `checkpoint_id`，通过 `parent_checkpoint_id` 串成前后关系；`step` 和 `source` 是 LangGraph 元数据，`next` 表示当时等待执行的节点。按 ID 读取旧快照只用于观察，不会把当前会话回退到那个时间点。当前最新状态始终由该 `thread_id` 的最新 checkpoint 决定。

测试会使用临时 SQLite 文件，验证跨连接恢复、历史快照和会话隔离：

```bash
.venv/bin/python -m unittest day06.test_demo -v
```
