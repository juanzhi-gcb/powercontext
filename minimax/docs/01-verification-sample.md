# 验证样例：订单金额下限筛选（SPEC-ORD-003）

## 1. 任务描述

任务文本：`tasks/TASK-ORD-003.md`

> 为 ordermesh 的订单查询增加金额下限筛选（`list_orders` 的 `min_total` 参数）：
> 结果必须包含金额等于下限的订单（闭区间），支持十进制字符串金额；负数与无法解析的
> 金额必须抛出 `ValueError`，并且结果仍然按创建时间降序排列。

要改什么：`demo_project/ordermesh/service.py` 中 `OrderService.list_orders` 的金额下限分支。
哪些原有行为必须保持：无筛选/状态筛选/未知状态报错/排序/金额精度（SPEC-ORD-001）。

## 2. 初始数据

- 5 条订单（客户 `c-1` 四条：100.00 / 150.00 / 200.00 / 150.00；客户 `c-2` 一条 300.00），
  见 `demo_project/tests/conftest.py`。
- 规格 4 份、规格条目 14 条；代码符号 12 个；测试 17 个（`ingest` 实际统计）。
- 数据库从空库开始：`init --drop` 建表 → `ingest` 导入。

## 3. 上下文中必须出现的来源

评审可对照 `context` 输出逐项核对（`source.verified` 应为 `true`）：

| 类别 | 必须包含 | 位置 |
|---|---|---|
| 规格 | `SPEC-ORD-003#R1` 闭区间语义 | `specs/SPEC-ORD-003-min-total.md:20-24` |
| 规格 | `SPEC-ORD-003#R3` 入参校验 | `specs/SPEC-ORD-003-min-total.md:31-34` |
| 规格 | `SPEC-ORD-003#R2` 缺省行为 | `specs/SPEC-ORD-003-min-total.md:27-28` |
| 规格 | `SPEC-ORD-001#R1` 返回范围与排序 | `specs/SPEC-ORD-001-order-listing.md:20-22` |
| 代码 | `OrderService.list_orders` | `demo_project/ordermesh/service.py:17-50` |
| 测试 | 6 个目标测试 | `demo_project/tests/test_min_total_filter.py` |
| 测试 | 7 个回归测试 | `demo_project/tests/test_list_orders_baseline.py` |

行号以提交版本为准；`context` 输出中的 `start_line/end_line` 即实际行号。

## 4. 操作步骤与预期结果

前置：`bash scripts/bootstrap.sh`，`.env` 中按需填 `MINIMAX_API_KEY`。

```bash
cd minimax
bash scripts/run_sample.sh --replay   # 或 --live
```

| 步骤 | 命令 | 预期 |
|---|---|---|
| 1 | `start_powercontext.sh` | `/health/ready` 返回 `{"status":"ready",...}` |
| 2 | `init --drop` + `ingest` | 4 张表；`spec_docs=14 code_docs=12 test_docs=17` |
| 3 | `reset-demo` | 业务工程回到修改前快照 |
| 4 | `context --task-file tasks/TASK-ORD-003.md` | 输出上表来源；`task_id=task-<hash>`；PowerContext 写入 `context_ready` |
| 5 | `baseline --task-id … --expect fail` | 目标测试 `exit=1`，`6 failed`（断言/异常均为功能失败，不是环境错误） |
| 6 | `patch --task-id … --replay …` | 生成 `evidence/changes/<task>.patch`；状态 `patched` |
| 7 | `verify --task-id …` | 目标 `6 passed`、回归 `7 passed`；状态 `verified` |
| 8 | 重启 PowerContext 后 `status --task-id …` | 仍读到 `verified` 与全部验证记录（状态复用） |

## 5. 规格更新后的行为（非固定答案）

```bash
bash scripts/update_spec_demo.sh
```

脚本在 `SPEC-ORD-003 R1` 末尾追加一条新规则，重新 `ingest`，再生成上下文：

- `revision` 从 1 变 2；
- `requirement` 文本包含新增的“千分位分隔符”规则；
- 脚本退出后自动恢复规格并再次 `ingest`。

## 6. 重置方法

```bash
bash scripts/reset_demo.sh                       # 恢复业务工程
rm -rf .seekdb .powercontext .sdd_state .runtime # 清空本地数据库与状态
bash scripts/run_sample.sh --replay              # 重新开始
```

## 7. 证据清单

| 证据 | 路径 |
|---|---|
| 任务上下文包（修改前生成） | `evidence/context/task-b5160ce9c9.json` |
| 规格更新前后的上下文 | `evidence/spec-update/context-before.json`、`context-after.json`、`spec-update-demo.log` |
| 修改前/后代码快照 | `evidence/code/before/`、`evidence/code/after/` |
| 代码差异 | `evidence/changes/<task>.patch` |
| 目标/回归测试日志（含命令与退出码） | `evidence/logs/*-target*.log`、`evidence/logs/*-regression.log` |
| MiniMax 请求/响应 | `evidence/minimax/<task>/` |
| 数据库查询记录 | `evidence/logs/db_queries.jsonl`、`evidence/logs/ingest-*.json` |
| PowerContext 写入/读取 | `evidence/powercontext/requests.jsonl`、`status` 输出 |
| 命令运行记录 | `evidence/logs/commands.jsonl` |
