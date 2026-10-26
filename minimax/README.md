# 规有所依：面向 SDD 的工程上下文模块（MiniMax × OceanBase）

本作品实现一个**规格驱动开发（SDD）上下文模块**：给它一句开发任务，它会从数据库里
检索出**适用的规格条目、需要修改的代码符号、用于验证的测试**，把上下文交给 MiniMax
生成代码修改，运行目标测试与回归测试，并把任务进展写入 PowerContext 供下次运行复用。

- 业务工程：`demo_project/`（Python 3.10+，`ordermesh` 订单查询服务，自带 pytest 测试）
- 规格：`specs/`（Markdown + YAML front matter，按 `R1/R2/...` 拆分条目）
- 上下文模块：`sdd_context/`（CLI：`python -m sdd_context.cli`）
- 数据库：seekdb（嵌入式，`pylibseekdb`）或 OceanBase / MySQL（DSN）
- 任务状态：PowerContext 1.4.0（HTTPServer + Atomic Memory）
- 代码修改：MiniMax `MiniMax-M2`（OpenAI 兼容 `/v1/chat/completions`）

完整验证样例见 [docs/01-verification-sample.md](docs/01-verification-sample.md)，
技术说明见 [docs/00-design.md](docs/00-design.md)，
MiniMax / 数据库 / PowerContext 使用记录见 [docs/02-technical-usage-log.md](docs/02-technical-usage-log.md)。

## 1. 目录结构

```
minimax/
├── sdd_context/            上下文模块（导入、检索、选择、状态、MiniMax 调用、测试执行）
├── specs/                  SPEC-ORD-001/003/004/005 规格源文件
├── demo_project/           业务工程（修改前状态），含目标测试与回归测试
├── tasks/TASK-ORD-003.md   本次任务的描述
├── scripts/                bootstrap / start_powercontext / run_sample / update_spec_demo
├── evidence/               验证证据：代码快照、diff、测试日志、数据库查询、PowerContext 记录
├── docs/                   一页技术说明、验证样例、技术使用记录
├── requirements.txt        固定依赖版本
├── .env.example            配置模板（占位值，不含真实凭据）
└── pyproject.toml          模块元数据（可选安装为 `sddctx` 命令）
```

## 2. 依赖版本

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.11 – 3.14（实测 3.12.14） | `pylibseekdb` 提供 cp311/cp312 abi3 wheel |
| PowerContext | 1.4.0 | `powercontext[cli,server,seekdb]` |
| pylibseekdb | 1.4.0.post1 | 嵌入式 seekdb，Linux/macOS x86_64/aarch64 |
| PyMySQL | 1.1.x | 1.2.x 与 aiomysql 有兼容问题，requirements 由 powercontext 约束 |
| pytest | 8.x | 运行目标/回归测试 |
| MiniMax API | `https://api.minimaxi.com/v1` | OpenAI 兼容，模型 `MiniMax-M2` |

> Windows 无 `pylibseekdb` wheel，请在 **WSL2 / Linux / macOS** 中运行；或把
> `SDDCTX_DB_MODE=server` 指向一个 OceanBase/MySQL 实例（见第 3 节）。

## 3. 环境准备

```bash
cd minimax
bash scripts/bootstrap.sh          # 创建 .venv 并安装 requirements.txt
cp .env.example .env               # 填入 MINIMAX_API_KEY（不要提交到仓库）
```

`bootstrap.sh` 会优先使用 `uv`，否则退回 `python3 -m venv`。网络受限时可指定镜像：

```bash
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple bash scripts/bootstrap.sh
```

### 数据库选择

默认是**嵌入式 seekdb**：第一次运行 `sdd_context` 时在 `.seekdb/` 下创建实例，
无需单独的数据库进程。若要复用已有 OceanBase：

```bash
# .env
SDDCTX_DB_MODE=server
SDDCTX_DSN=mysql://root@127.0.0.1:2881/sdd_context
# 先建库：mysql -h127.0.0.1 -P2881 -uroot -e 'CREATE DATABASE sdd_context'
```

两种模式写入的是同一套表：`sdd_documents`、`sdd_postings`、`sdd_links`、`sdd_ingest_runs`。

### PowerContext

任务状态存放在 PowerContext 的 Atomic Memory 中，Scope 名为
`sdd:<project>:<task_id>`。脚本会用**嵌入式 seekdb** 作为 PowerContext 自身的持久化后端：

```bash
bash scripts/start_powercontext.sh   # 启动并等待 /health/ready
bash scripts/stop_powercontext.sh
```

## 4. 调用入口与输入/输出

入口：`python -m sdd_context.cli <command>`（需要 `PYTHONPATH=.`，或安装后直接用 `sddctx`）。

| 命令 | 输入 | 输出 |
|---|---|---|
| `init [--drop]` | — | 创建 4 张表，打印表数 |
| `ingest` | `specs/*.md`、`demo_project/**/*.py`、`demo_project/tests/*.py` | 导入/更新文档数、链接数、`run_id`，被更新的文档 revision |
| `context --task-file tasks/TASK-ORD-003.md --out ctx.json` | 任务文本 | 上下文包 JSON（规格条目、代码符号、目标/回归测试、真实文件行号与校验），并把 `context_ready` 状态写入 PowerContext |
| `baseline --task-id <id> --expect fail` | 已保存的上下文 | 目标测试基线运行结果（预期失败） |
| `patch --task-id <id> [--replay FILE]` | 上下文 + MiniMax | 代码 diff（`evidence/changes/<task>.patch`）、MiniMax 请求/响应记录 |
| `verify --task-id <id>` | PowerContext 中的测试清单 | 目标测试与回归测试结果，更新状态为 `verified` |
| `status --task-id <id>` | PowerContext | 已完成、待办、历史验证结果 |
| `doctor` | — | 依赖、数据库、PowerContext、MiniMax key 状态 |

`context` 的输出结构（节选）：

```json
{
  "task_id": "task-b3686e98ff",
  "spec_items": [
    {"id": "SPEC-ORD-003#R1", "title": "…", "requirement": "…",
     "source": {"path": "specs/SPEC-ORD-003-min-total.md", "start_line": 20,
                "end_line": 24, "revision": 1, "verified": true}}
  ],
  "code": [
    {"symbol": "OrderService.list_orders", "path": "demo_project/ordermesh/service.py",
     "reason": ["linked to SPEC-ORD-001#R1", "exercised by 13 tests"],
     "source": {"start_line": 17, "end_line": 50, "verified": true}}
  ],
  "tests": {
    "target": [{"node_id": "tests/test_min_total_filter.py::test_min_total_includes_orders_equal_to_the_boundary", "covers": ["SPEC-ORD-003#R1"]}],
    "regression": [{"node_id": "tests/test_list_orders_baseline.py::test_returns_every_order_of_one_customer_newest_first", "covers": ["SPEC-ORD-001#R1"]}]
  }
}
```

所有 `source.path/start_line/end_line` 都指向真实文件，`verified` 表示导入时的内容哈希
与磁盘一致；规格被改动后再次 `ingest`，`revision` 加一并返回新内容。

## 5. 验证样例（一条命令）

```bash
# 无 API key：回放已记录的 MiniMax 响应
bash scripts/run_sample.sh --replay

# 有 API key：真实调用 MiniMax
bash scripts/run_sample.sh --live
```

脚本会：清空 seekdb 与 PowerContext 状态 → 导入资料 → 恢复业务工程 → 生成上下文 →
基线（6 个目标测试失败）→ 应用 MiniMax 修改 → 验证（目标 6 通过、回归 7 通过）→
重启 PowerContext 后再次 `status` 读取同一份状态。

单独运行测试：

```bash
cd demo_project && ../.venv/bin/python -m pytest -q      # 修改前：6 failed, 11 passed
cd demo_project && ../.venv/bin/python -m pytest -q tests/test_list_orders_baseline.py tests/test_discount.py
```

验证“规格更新后上下文随之变化”：

```bash
bash scripts/update_spec_demo.sh
```

## 6. 已知限制

- `pylibseekdb` 只提供 Linux/macOS wheel；Windows 需在 WSL2 中运行，或改用 `SDDCTX_DB_MODE=server`。
- 嵌入式 seekdb 每个进程约 1–2 秒启动时间，CLI 每次调用都会打开/关闭实例。
- PowerContext 未配置生成/向量模型，因此只使用显式 Memory 与 FTS 检索；不使用自动记忆抽取。
- 上下文选择是可解释的 TF-IDF + 链接图，不做语义向量检索；规格中的 `keywords` 会加权。
- 目标测试的划分规则：覆盖“焦点规格”（得分最高的规格）的测试为目标测试；带
  `@pytest.mark.regression` 的测试始终归入回归测试。
- MiniMax 生成结果需要人工复核；模块会校验路径白名单与 Python 语法，但不会自动判断语义正确性。

## 7. 复现说明

- 分支：`2026-competition-ecosystem`，作品目录：`minimax/`
- 业务工程以“修改前”状态提交；修改后的文件快照在 `evidence/code/after/`，差异在
  `evidence/changes/`。
- 真实凭据只存在于本地 `.env`（已被 `.gitignore` 排除），仓库内只保留占位值。