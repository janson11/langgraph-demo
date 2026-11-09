# 第 7 天 报告审核与退回修改

目标：生成需求分析报告后暂停，审核通过才输出最终报告；退回时携带修改意见重新生成草稿，再次等待审核。此示例使用固定模板和 day03 的资料查询工具，无需模型 API。

在项目根目录运行。先创建一份报告：

```bash
.venv/bin/python -m day07.demo --thread-id report-a --requirement "输出报告前需要人工审核"
```

程序会保存第 1 版草稿并停在 `review`。另起进程，退回并附修改意见：

```bash
.venv/bin/python -m day07.demo --thread-id report-a --resume reject --feedback "补充验收标准"
```

此时生成第 2 版草稿，并再次停在 `review`。查看状态或通过审核：

```bash
.venv/bin/python -m day07.demo --thread-id report-a --show
.venv/bin/python -m day07.demo --thread-id report-a --resume approve
```

默认数据库为 `day07/checkpoints.sqlite`。使用 `--db` 指定其他数据库时，每次运行都要传相同路径和 `thread_id`。一份报告占用一个 `thread_id`；新报告请换 ID。最终报告只在批准后写入状态；退回时的修改意见会保留在新草稿中。`--show` 只读取状态，不会继续执行图。

```bash
.venv/bin/python -m unittest day07.test_demo -v
```

执行路径：`research → draft → review`；`review` 用 `interrupt()` 保存待审核状态。批准后进入 `finalize`，退回后把意见写入状态并回到 `draft`。恢复中断时 `review` 节点会重新执行，因此中断前不应放不可重复的外部写入。
