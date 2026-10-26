# 提交说明与评审对照表

- 赛题：MiniMax × OceanBase ——「规有所依」面向软件持续演进的 SDD 上下文管理系统
- 仓库：`https://github.com/juanzhi-gcb/powercontext`
- 分支：`2026-competition-ecosystem`
- 作品目录：`minimax/`
- 不可变引用：tag `minimax-submission-v1`（指向本目录所在提交）

评分规则：六项必做项**全部通过得 20 分，任一项不通过得 0 分**。以下逐项给出判定方法、
复现命令和证据位置。

## 1. 能够运行

判定：按说明初始化数据、启动模块、执行验证样例，不依赖未交付的本地文件或状态。

```bash
cd minimax
bash scripts/bootstrap.sh          # 固定依赖：powercontext[cli,server,seekdb]==1.4.0
bash scripts/run_sample.sh --replay
```

`run_sample.sh` 每次从空数据库、空 PowerContext 状态开始，依次完成 8 个步骤。
证据：`evidence/logs/commands.jsonl`（每条命令的退出码）。

## 2. MiniMax 实际参与

判定：开发记录包含任务、提供的上下文和代码修改过程，并与提交的代码差异对应。

| 内容 | 位置 |
|---|---|
| 任务文本 | `tasks/TASK-ORD-003.md` |
| 提供给模型的上下文 | `sdd_context/minimax.py::build_messages` 生成的规格+代码+目标测试 |
| 请求/响应原文（含 usage） | `evidence/minimax/task-b5160ce9c9/20261026T082901Z.json` |
| 模型、token、耗时记录 | `docs/02-technical-usage-log.md` §1 |
| 与模型输出对应的 diff | `evidence/changes/task-b5160ce9c9.patch` |

模型：`MiniMax-M3.1-Flash`；请求 id `072e41ebf67119aa4664053f9ae2dd67`；
finish_reason `stop`；9989 tokens；98.66 s。

## 3. 上下文正确

判定：输出包含规定的规格、代码和测试来源；规格更新并重新导入后使用新内容。

- 8 条规格条目、3 个代码符号、6 个目标测试、7 个回归测试，全部带真实路径与行号，
  `source.verified=true`：`evidence/context/task-b5160ce9c9.json`
- 规格更新实验：`evidence/spec-update/`（`SPEC-ORD-003#R1` revision 1→2，文本随之变化）
- 复现：`bash scripts/update_spec_demo.sh`

## 4. 数据库实际参与

判定：seekdb/OceanBase 保存工程资料或索引，实际查询结果用于任务上下文。

- 嵌入式 seekdb：43 个文档（14 规格 / 12 代码 / 17 测试）、40 条链接、1444 条倒排索引
- SQL 记录（186 条，含参数、行数、耗时）：`evidence/logs/db_queries.jsonl`
- 导入结果：`evidence/logs/ingest-15a13dcd2b87498e.json`
- 也支持 OceanBase 直连：`SDDCTX_DB_MODE=server SDDCTX_DSN=mysql://root@127.0.0.1:2881/sdd_context`

## 5. 状态能够复用

判定：从空状态保存任务记录，重启模块后能够读取并用于后续处理。

- PowerContext Scope：`sdd:ordermesh:task-b5160ce9c9`
- 状态序列：`context_ready → baseline_failed → patched → verified`（seq 1–4）
- 重启前后两次 `status`：`evidence/powercontext/status-before-restart.txt`、
  `status-after-restart.txt`（内容一致）
- 全部 23 次 HTTP 调用：`evidence/powercontext/requests.jsonl`

## 6. 代码修改有效

判定：同一组目标测试修改前因目标行为未实现而失败，修改后全部通过；回归测试也通过。

| 阶段 | 结果 | 日志 |
|---|---|---|
| 修改前（目标） | `6 failed`（断言/`decimal.InvalidOperation`） | `evidence/logs/20261026T082720Z-target-baseline.log` |
| 修改后（目标） | `6 passed` | `evidence/logs/20261026T082901Z-target.log` |
| 修改后（回归） | `7 passed` | `evidence/logs/20261026T082901Z-regression.log` |

注意：仓库中 `demo_project/` 提交的是**修改前**状态，直接 `pytest` 会看到 6 个失败；
这是验证样例的起点，不是缺陷。`run_sample.sh` 会应用 MiniMax 补丁后再验证。

## 材料清单

| 材料 | 位置 |
|---|---|
| 完整源码 | `sdd_context/`、`demo_project/`、`scripts/` |
| 运行说明 | `README.md` |
| 验证样例 | `docs/01-verification-sample.md`、`tasks/TASK-ORD-003.md` |
| 代码与测试 | `evidence/code/before/`、`evidence/code/after/`、`evidence/changes/`、`evidence/logs/` |
| 技术使用记录 | `docs/02-technical-usage-log.md`、`evidence/minimax/`、`evidence/powercontext/` |
| 一页技术说明 | `docs/00-design.md` |

## 最短复现路径

```bash
cd minimax
bash scripts/bootstrap.sh
bash scripts/run_sample.sh --replay   # 无 API key 也可完整复现
```

需要真实调用 MiniMax 时，在 `minimax/.env` 填入 `MINIMAX_API_KEY` 后执行
`bash scripts/run_sample.sh --live`。