# 一页技术说明：SDD 上下文模块

## 1. 模块结构

```
                   ┌────────────────────────── sdd_context ──────────────────────────┐
任务文本 ─────────▶ │ cli.py  (context / baseline / patch / verify / status)          │
                   │    │                                                            │
                   │    ├─ ingest.py ──▶ 解析 specs/*.md、AST 解析代码与测试           │
                   │    │                 写入 sdd_documents / sdd_postings / sdd_links│
                   │    │                                                            │
                   │    ├─ select.py ──▶ SQL 检索 + TF-IDF + 链接图扩展                │
                   │    │                 产出规格条目/代码符号/目标测试/回归测试        │
                   │    │                                                            │
                   │    ├─ state.py  ──▶ PowerContext Atomic Memory (scope per task)  │
                   │    │                                                            │
                   │    ├─ minimax.py ─▶ MiniMax /v1/chat/completions → JSON 文件替换 │
                   │    │                 校验路径白名单 + ast.parse，生成 diff         │
                   │    │                                                            │
                   │    └─ runner.py ──▶ pytest 目标套件 / 回归套件，记录退出码与日志    │
                   └────────────────────────────────────────────────────────────────┘
                              │                        │                      │
                        seekdb/ OceanBase        PowerContext       MiniMax-M3.1-Flash
```

## 2. 资料如何进入数据库

`ingest` 做三件事：

1. **规格**：读取 YAML front matter（`spec_id`、`keywords`、`anchors`），按 `## R<n>` 标题
   拆成条目，每个条目一行，记录真实文件与行号。
2. **代码**：用 `ast` 提取模块级函数/类/方法，记录限定名、起止行号与源码片段。
3. **测试**：提取 `test_*` 函数，解析 `@pytest.mark.spec("SPEC-…")` 与
   `@pytest.mark.regression`，并用 AST 收集测试体里调用的符号。

随后建立三类链接：

- `spec-code`：规格正文提到某个符号名（如 `list_orders`）→ 链接到对应代码符号；
- `test-spec`：测试的 `mark.spec` 批注 → 链接到规格条目；
- `test-code`：测试体调用了某个符号 → 链接到对应代码符号。

每个文档的标题、`keywords`、正文都会分词后写入 `sdd_postings`（倒排索引，
ASCII 标识符 + 中文 bigram），供检索打分。

## 3. 上下文如何选择

输入只有任务文本，过程完全确定、可复核：

1. 任务分词 → 在 `sdd_postings` 上做 TF-IDF（`idf = ln(1 + N/(1+df))`，长度归一化），
   得到规格条目的得分与命中词。
2. 取分最高者为**焦点规格**，保留相对阈值 0.28 以上的前 8 个条目。
3. 沿链接图扩展代码：规格→代码链接、任务中点名的符号、目标测试实际调用的符号。
4. 目标测试 = 覆盖焦点规格条目的测试（`mark.regression` 的除外）；回归测试 = 覆盖其他
   被选规格或调用被选代码的测试。
5. 输出前逐个校验来源：文件是否存在、行号区间内容哈希是否与导入时一致
   （`source.verified`），保证“来源真实存在”。

因此更新规格并重新 `ingest` 后，`revision` 与 `requirement` 文本都会变化，
模块不可能返回固定答案（见 `scripts/update_spec_demo.sh`）。

## 4. 三项技术的分工

| 技术 | 承担的作用 | 证据位置 |
|---|---|---|
| **seekdb / OceanBase** | 存储并检索全部工程资料：规格条目、代码符号、测试结点、倒排索引与链接图。上下文里的每条来源都来自对这些表的实际查询。 | `evidence/logs/db_queries.jsonl`、`evidence/logs/ingest-*.json` |
| **PowerContext** | 保存任务进展：`context_ready → baseline_failed → patched → verified`，以及已完成/待办/验证结果。每个任务一个 Scope，状态以 Atomic Memory 追加写入；进程重启后按 Scope 读取最新一条。 | `evidence/powercontext/requests.jsonl`、`status` 输出 |
| **MiniMax** | 接收上下文（规格 + 代码 + 目标测试），生成完整文件替换，形成本次代码修改。请求与响应原样记录，并与最终 diff 对应。 | `evidence/minimax/`、`evidence/changes/` |

## 5. 关键设计取舍

- **不用模型做检索**：选择完全由 SQL + 打分 + 链接图决定，便于评委复核与复现，
  也避免把检索质量绑定在模型可用性上。
- **状态只存指针与结论**：PowerContext 中存规格 ID、测试结点、验证结果与 diff 路径，
  不存整个上下文正文，单条 Memory 控制在 8 KB 以内。
- **修改来自模型、校验留给代码**：MiniMax 返回完整文件内容，模块负责路径白名单、
  Python 语法检查、diff 生成与测试执行，模型不能直接执行任意写入。
- **两种数据库形态**：默认嵌入式 seekdb（零运维），也可指向 OceanBase/MySQL DSN；
  建表语句只用 MySQL 5.7 兼容语法。
