# 第 8 天 失败恢复与幂等发布

本例接续 day07 的已批准报告，检查资料工具异常、节点失败后的恢复，以及外部写入是否重复。`published_reports` 表模拟外部发布系统；它使用独立 SQLite 连接，写入可能先于 LangGraph 的 checkpoint 提交。

在项目根目录使用一个新的 `thread_id`，先批准第 7 天报告：

```bash
.venv/bin/python -m day07.demo --thread-id day08-a --requirement "报告输出前需要人工审核"
.venv/bin/python -m day07.demo --thread-id day08-a --resume approve
```

模拟“发布记录已写入，但节点随后失败”，再在新进程中恢复：

```bash
.venv/bin/python -m day08.demo --thread-id day08-a --start --fail-at after-write
.venv/bin/python -m day08.demo --thread-id day08-a --show
.venv/bin/python -m day08.demo --thread-id day08-a --retry
```

第一条 day08 命令会故意失败并返回非零退出码；应看到 `下一节点：publish`、`图状态 published：False`、`发布记录：1 条`。恢复时 `publish` 节点再次执行并显示“命中幂等键，跳过重复写入”；图状态变为 `True`，发布记录仍为 1 条。相同报告的 `publication_key` 由 `thread_id` 和报告内容哈希生成，表的主键约束配合 `ON CONFLICT DO NOTHING` 保证重试不重复写入。

另用一个新 `thread_id` 验证资料工具异常：

```bash
.venv/bin/python -m day07.demo --thread-id day08-b --requirement "报告输出前需要人工审核"
.venv/bin/python -m day07.demo --thread-id day08-b --resume approve
.venv/bin/python -m day08.demo --thread-id day08-b --start --fail-at tool
.venv/bin/python -m day08.demo --thread-id day08-b --retry
```

故障后下一节点应为 `check_source`，发布记录为 0 条；恢复后为 1 条。两种故障都只对带 `--fail-at` 的那次进程生效。

day08 使用同一数据库；命令行传入 day07 的 `thread_id`，内部将发布流程存到 `day08:<thread_id>`，隔离两套 checkpoint。`--show` 只读取，不推进节点。测试使用临时数据库：

```bash
.venv/bin/python -m unittest day08.test_demo -v
```
