# 烦恼典当行后端

Python 3.12 + FastAPI，无模型调用。Dify 负责模型与编排，SQLite 负责准确交易，PowerContext HTTP 负责跨会话记忆。接口契约见 `../docs/design.md`。

从仓库根目录运行：

```powershell
$env:UV_CACHE_DIR='D:/DifyPawnshop/cache/uv'
uv run --project dify/backend --group dev pytest dify/tests/backend -q
uv run --project dify/backend uvicorn pawnshop.app:create_app --factory --host 127.0.0.1 --port 8080 --workers 1
```

环境变量：

| 变量 | 说明 |
| --- | --- |
| `PAWNSHOP_API_KEY` | 必填；可信 Dify HTTP 节点通过 `X-Pawnshop-Key` 传入 |
| `PAWNSHOP_DB_PATH` | 默认 `/data/pawnshop.sqlite3`；本地 Windows 开发时设置为 D 盘路径 |
| `POWERCONTEXT_URL` | 默认 `http://powercontext:8000` |
| `POWERCONTEXT_TOKEN` | PowerContext Bearer 凭据 |

每个 workflow run 使用一个 `turn_id`。prepare 将用户、会话、原文和物件版本快照绑定到此 turn；重复 prepare 返回首次读取结果。act 重复同一规范化提案会重放回执，改变提案返回 409。并发请求通过每个 turn 的短生命周期互斥锁等待最终回执；部署使用一个 worker。SQLite 事务与 outbox 阶段认领保护交易和外部写入，网络请求期间不持有 SQLite 写锁。

prepare 的 `state_json.item_actions` 以完整物件 id 为键，列出每件物件的合法变更操作；`allowed_actions` 是所有物件操作与 appraise/shelf/chat 的并集。`current_item` 仍指最近操作的物件，不能因为它已取回而屏蔽较早入柜藏品的回访/取回。纠正仅提供给当前最新草稿。

`appraise` 只生成 draft；`correct` 只修改当前 draft；`pawn` 从 prepare 原文核验明确的“确认典当 / 确认入柜”，拒绝否定、问句、引述和条件句。典当不能同时修改卡片。`revisit` 只接受 pawned/transformed，`reported_event` 必须逐字出现在用户原文，卡片变化明确属于虚构故事；`retrieve` 将物件归档为 retrieved。每件物品 id 都校验 owner，版本由 prepare 快照校验；模型不得提供 scope。

## PowerContext 审计与恢复

适配器严格使用 commit `31ecdd61beadb7ac8de5da20998dead9a9e07845` 的 `/v1/scopes`、`/v1/sources/content`、`/v1/memory/remember` 和 `/v1/context/prepare`。Scope 创建使用稳定 idempotency_key。每个同步事件先捕获 Source，取得真实 `{status,source,position}` 回执，再写显式 Atomic Memory，保存真实 `records[].artifact` 引用。此版本 remember API 不接受 `source_refs`，因此真实 Source 审计引用嵌入 memory 文本，并将两份完整服务回执保存在 outbox；不声称建立了 API 不支持的结构化来源关系。每条记忆含 `pawnshop` 检索锚点。

纠正内容从 prepare 保存的用户原文提取，独立记为 `user_correction`，不从卡片寓意推断事实。纠正和后续该藏品的典当/回访/取回记忆均携带最近一次纠正的事件 id、逐字摘录与截断标志。纠正原话与用户报告事件各自最多使用 512 个 JSON 编码后的 UTF-8 字节，并各有截断标志；完整原文与完整事件仍保存在 Source。两类事实摘录和简短元数据共同放在前 1800 字节以内，完整奇幻卡片放在其后，使用保留顺序的 JSON 序列化。这样 PowerContext 的单条 2000 字节召回截断仍能保留纠正和回访信息。包含实际来源引用的最终 Memory 文本保持在 PowerContext 的 8192 字节上限内。

| act 的 memory_status | 含义 |
| --- | --- |
| `not_required` | 草稿鉴定或只读操作，不写记忆 |
| `synced` | 已取得实际 Atomic Memory 引用 |
| `pending` | 尚未送达，或 Source 已成功而 Memory 尚未送达；可安全恢复 |
| `unknown` | 请求可能已经送达，响应丢失、无效或进程在写入中终止；禁止自动重发 |

prepare 只返回 PowerContext 当前实际读取的 ready / empty / unavailable；读取失败时 `memory_context` 为空，不用 SQLite 拼接召回证据。当前物件和货架始终清楚标为本地交易状态。

该固定版本的召回是词法的（jieba 分词 + 查询词覆盖率门槛）。用户自然口语（如“上次我放在这里的东西还在吗”）与记忆文本重叠太少，会返回 empty。因此 prepare 不把用户原话当检索词，而是用账本中当前藏品的完整 id 与名称组成查询；这些词逐字出现在该藏品的每条记忆里，能稳定通过门槛，Scope 隔离又保证不会读到别人的记录。用户原话仍完整交给模型。没有藏品时（新玩家）才退回用户原话作查询。

断连前未送达的 pending 事件会在下一次新 prepare 或需写入记忆的 act 中尝试同步。`unknown`、`writing_source`、`writing_memory` 保留供人工核对；进程重启不会自动重发。通过认证的 `/v1/items/{id}?user_id=...` 可读到逐事件状态和真实引用。运营核对时应备份 SQLite（包含 WAL 的一致性备份），以 `event_id`、确定的 Source id 和源回执查询 PowerContext；若外部确已写入，应记录真实引用后完成本地对账。禁止仅因超时而把未知事件直接改回 pending。跨进程自动对账管理 API 不在首版范围。

首次返回的交易回执保持稳定：后台恢复 pending 后，原 turn 重放仍返回原回执，最新同步结果从物件事件读取。Markdown 的当票、中文状态和记忆提示由服务端生成；完整版本与同步引用保留在 JSON 回执中供审计，老板的虚构台词不能充当写入证明。

测试使用 httpx MockTransport 驱动真实 HTTP 适配器和临时 SQLite，不构成真实 PowerContext、Dify 或模型端到端证据。真实服务验收脚本由 `../scripts/verify_services.py` 提供。
