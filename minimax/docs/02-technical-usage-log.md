# 技术使用记录

记录本次验证样例的真实运行：MiniMax 生成代码修改、seekdb 存储与检索工程资料、
PowerContext 保存并复用任务状态。所有数字均来自 `evidence/` 下的原始记录。

## 0. 环境与版本

| 项 | 值 |
|---|---|
| 运行时间 | 2026-10-26（UTC 08:27–08:29） |
| 主机 | Windows 11 + WSL2 Ubuntu（glibc 2.43） |
| Python | 3.12.14 |
| PowerContext | 1.4.0（`powercontext[cli,server,seekdb]`） |
| pylibseekdb | 1.4.0.post1（嵌入式 seekdb，服务端版本 `5.7.25-OceanBase seekdb-v1.4.0.0`） |
| pytest | 8.x |
| 数据库目录 | `/root/sdd-live-db`（WSL 的 `/mnt/c` 是 9p 文件系统，seekdb 无法打开，故使用 Linux 原生路径；原生 Linux 上用默认 `minimax/.seekdb` 即可） |
| PowerContext 数据目录 | `/root/mm-live/.powercontext`（同上） |

## 1. MiniMax 开发记录

### 1.1 接入方式

- 协议：OpenAI 兼容的 `POST {base}/chat/completions`，`Authorization: Bearer <MINIMAX_API_KEY>`
- Base URL：`https://api.minimaxi.com/v1`
- 代码：`sdd_context/minimax.py`（`MinimaxClient.chat`），无额外 SDK 依赖

### 1.2 模型选择（实测）

先按文档使用 `MiniMax-M2`，接口返回：

```
HTTP 404 {"error":{"type":"not_found_error","message":"The model \"MiniMax-M2\" is no longer available. (2069)"}}
```

`GET /v1/models` 返回的可用列表中包含 `MiniMax-M3.1-Flash`、`MiniMax-M3`、`MiniMax-M2.7` 等。
实测 `MiniMax-M3.1-Flash` 可用，最终采用：

| 项 | 值 |
|---|---|
| 模型 | `MiniMax-M3.1-Flash` |
| 请求 id | `072e41ebf67119aa4664053f9ae2dd67` |
| 耗时 | 98.66 s |
| finish_reason | `stop` |
| prompt_tokens | 3374 |
| completion_tokens | 6615（其中 reasoning 5909） |
| total_tokens | 9989 |
| 输入字符数 | 10895（system + user） |
| 输出字符数 | 2831（JSON） |

首次尝试时把 `max_tokens` 设为 6000，结果被截断（`finish_reason=length`，推理占满预算）。
模块现在会在截断时给出明确错误，默认预算已提高到 16000。

### 1.3 提供给模型的上下文

用户消息由 `sdd_context/minimax.py::build_messages` 从上下文包渲染：

1. 8 条规格条目（`SPEC-ORD-003#R1/R2/R3/R4`、`SPEC-ORD-001#R1/R2/R3`、`SPEC-ORD-004#R1`），含文件路径与行号；
2. 需要修改的代码：`OrderService.list_orders` 的带行号源码；
3. 6 个目标测试的源码；
4. 可修改文件白名单（完整 `service.py`、`models.py`）。

system prompt 固定了规则：只改白名单文件、不得改测试、只用标准库、返回约定 JSON。

### 1.4 模型返回与实际修改

模型 summary：

> 更新订单查询服务：按闭区间校验并筛选 min_total，统一转换非法输入为 ValueError，同时保持状态筛选和创建时间降序。

- 修改文件：`demo_project/ordermesh/service.py`（1 个）
- 自报覆盖：`SPEC-ORD-003#R1/R2/R3/R4`、`SPEC-ORD-001#R1/R2/R3`、`SPEC-ORD-004#R1`
- 说明：`models.py` 已满足金额模型要求，无需修改。模块只写入了模型实际返回的文件。

关键改动（完整 diff 见 `evidence/changes/task-b5160ce9c9.patch`）：

```diff
-            threshold = min_total if isinstance(min_total, Decimal) else Decimal(min_total)
-            orders = [order for order in orders if order.total > threshold]
+            if isinstance(min_total, bool) or not isinstance(
+                min_total, (Decimal, int, str)
+            ):
+                raise ValueError(f"invalid min_total: {min_total!r}")
+            try:
+                threshold = (
+                    min_total if isinstance(min_total, Decimal) else Decimal(min_total)
+                )
+            except (DecimalException, TypeError, ValueError):
+                raise ValueError(f"invalid min_total: {min_total!r}") from None
+            if not threshold.is_finite():
+                raise ValueError(f"invalid min_total: {min_total!r}")
+            if threshold < 0:
+                raise ValueError(f"min_total must be non-negative: {min_total!r}")
+            orders = [order for order in orders if order.total >= threshold]
```

模块侧的后处理：路径白名单校验 → `ast.parse` 语法校验 → 写文件 → 用 `difflib` 生成 unified diff。

### 1.5 记录与复现

| 内容 | 路径 |
|---|---|
| MiniMax 完整请求/响应（含 messages 与 usage，不含 Authorization 头） | `evidence/minimax/task-b5160ce9c9/20261026T082901Z.json` |
| 供无 key 复现的响应正文 | `evidence/minimax/recorded-response.json` |
| 代码差异 | `evidence/changes/task-b5160ce9c9.patch` |

无 key 复现：`bash scripts/run_sample.sh --replay`（使用上面的 recorded-response.json）。

## 2. 数据库使用记录

### 2.1 存储内容

嵌入式 seekdb，4 张表（`sdd_documents`、`sdd_postings`、`sdd_links`、`sdd_ingest_runs`）。

`ingest` 运行 `15a13dcd2b87498e` 的统计：

| 指标 | 值 |
|---|---|
| 规格条目 | 14 |
| 代码符号 | 12 |
| 测试结点 | 17 |
| 链接 | 40（`spec-code` 4、`test-code` 19、`test-spec` 17） |
| 倒排索引条目 | 1444 |
| 资料摘要 | `d42ed23d…e890da` |

### 2.2 实际查询（用于构造上下文）

文档元数据与行号（输出里 `source.path/start_line/end_line` 的直接来源）：

```sql
SELECT doc_id, doc_type, path, symbol, title, start_line, end_line,
       revision, checksum, keywords
  FROM sdd_documents
 WHERE project_id = 'ordermesh';
```

倒排索引检索（任务关键词 → 候选规格条目）：

```sql
SELECT p.term, p.doc_id, p.tf
  FROM sdd_postings p
  JOIN sdd_documents d ON d.doc_id = p.doc_id
 WHERE p.term IN ('min_total','金额','下限','负数','排序')
   AND d.doc_type = 'spec'
 ORDER BY p.tf DESC;
```

实际返回示例（节选）：

```
term=min_total  doc_id=spec:SPEC-ORD-003#R1  tf=…
term=负数       doc_id=spec:SPEC-ORD-003#R3  tf=11.0
term=排序       doc_id=spec:SPEC-ORD-001#R1  tf=13.0
```

链接图扩展（规格 → 代码、测试 → 规格/代码）：

```sql
SELECT src_id, dst_id, kind
  FROM sdd_links l
  JOIN sdd_documents d ON d.doc_id = l.src_id
 WHERE d.project_id = 'ordermesh';
```

这些行的内容随后由 `select.py` 计算 TF-IDF 分数并做相对阈值截断，最终成为上下文包中的
`spec_items/code/tests`。

### 2.3 证据

| 内容 | 路径 |
|---|---|
| 本次运行的全部 SQL（含参数、行数、耗时） | `evidence/logs/db_queries.jsonl`（186 条） |
| 导入结果 | `evidence/logs/ingest-15a13dcd2b87498e.json` |
| OceanBase 直连模式 | 另测 `SDDCTX_DB_MODE=server` + `mysql://root@127.0.0.1:2881/sdd_context`，同样建表并导入 43 个文档 |

## 3. PowerContext 使用记录

### 3.1 Scope 与状态序列

- Scope 标题：`sdd:ordermesh:task-b5160ce9c9`
- Scope id：`scp_2xbrpjyr33vg70jb8y3wdpb0yv`
- 每次状态写入都是 `POST /v1/memory/remember`，`kind=sdd-task-state`，正文为 JSON

| seq | phase | 时间（UTC） | completed | verification |
|---:|---|---|---:|---:|
| 1 | `context_ready` | 08:27:18 | 0 | 0 |
| 2 | `baseline_failed` | 08:27:20 | 1 | 1（6 failed） |
| 3 | `patched` | 08:29:01 | 2 | 1 |
| 4 | `verified` | 08:29:01 | 3 | 3（目标 6 passed、回归 7 passed） |

另有 3 条 `sdd-milestone`：baseline 结果、应用修改、验证结果。

全部 23 次 HTTP 调用：

```
 3x POST /v1/scopes                     # 同一 idempotency_key，返回同一 scope
 7x POST /v1/memory/remember            # 4 条状态 + 3 条里程碑
10x POST /v1/memory/entries/list        # 每次读回最新状态
 3x GET  /v1/scopes?query_field=title…  # 重启后按标题找回 Scope
```

### 3.2 重启后复用

`run_sample.sh` 第 8 步停止并重新启动 PowerContext，再用同一 `--task-id` 执行 `status`：

- 重启前：`evidence/powercontext/status-before-restart.txt`
- 重启后：`evidence/powercontext/status-after-restart.txt`

两份输出一致：`phase: verified`，`seq 4`，3 条验证记录齐全，说明状态来自 PowerContext 的持久化存储，
而不是模块进程内缓存。后续 `verify` 也直接从该状态读取测试结点清单。

### 3.3 证据

| 内容 | 路径 |
|---|---|
| 全部请求/响应（含 scope、memory 正文） | `evidence/powercontext/requests.jsonl` |
| 重启前后状态 | `evidence/powercontext/status-*.txt` |

## 4. 本次运行的命令与退出码

来自 `evidence/logs/commands.jsonl`（均为 `exit=0`）：

```
sddctx init --drop
sddctx ingest
sddctx reset-demo
sddctx context --task-file tasks/TASK-ORD-003.md --out .runtime/context.json
sddctx baseline --task-id task-b5160ce9c9 --expect fail
sddctx patch --task-id task-b5160ce9c9
sddctx verify --task-id task-b5160ce9c9
sddctx snapshot --label after
sddctx status --task-id task-b5160ce9c9
sddctx status --task-id task-b5160ce9c9        # 重启 PowerContext 之后
```

## 5. 已知偏差与说明

- `MiniMax-M2` 在该账号下不可用（错误码 2069），实际使用 `MiniMax-M3.1-Flash`；模型 id 可通过
  `MINIMAX_MODEL` 覆盖。
- 首次调用因 `max_tokens=6000` 被截断，属预算问题而非模型失败；默认值已调整为 16000。
- 本地 WSL 中数据目录必须放在 Linux 文件系统；这是 WSL/9p 的限制，不影响原生 Linux 判题环境。