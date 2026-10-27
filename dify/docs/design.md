# 烦恼典当行：设计与接口契约

日期：2026-10-27。用户已批准在 D 盘持续实施完整比赛作品。

## 目标与范围

以 Dify Chatflow 编排一个文字游戏：鉴定烦恼生成奇幻物件、纠正鉴定、确认入柜、跨会话回访导致物件变化、查看货架与取回。老板老余幽默、允许玩家纠正；不对痛苦打分，不宣称诊断、治愈或预测未来。虚构物件与用户确认的事实分别记录。首次鉴定只是草稿，明确确认后才正式典当。

首版采用 Dify 1.17.1（8387590ace4a094de812b7847fc6a4c3a27cd52b）、PowerContext HTTP Server（锁定源码 commit，使用 Source/Memory/PreparedContext）、Python FastAPI 后端、SQLite 精确交易账本。Dify 本身使用其官方默认部署数据库，不宣称 seekdb。无需自定义 Dify 插件或知识库，也不要求 Embedding/Rerank。后端不调用模型，模型调用与分支必须保留在 Dify 中。

## 存储与状态

玩家身份由带服务密钥的可信 Dify HTTP 节点传递，后端映射 Scope，不接受模型指定 Scope。每件物品有 id、owner、version、status、card、事件历史。状态为 draft / pawned / transformed / retrieved；纠正只允许当前草稿，pawn 需要 draft，revisit 需要 pawned 或 transformed，retrieve 需要 pawned 或 transformed。用户可保存多个藏品，prepare 返回最近当前藏品和货架。客户端给定物件 id 仍必须校验 owner。展示故事不等于确认真实人物性格。

SQLite 保存准确物件状态、版本、turn 回执、Scope 映射和待同步记忆。PowerContext 保存已确认物件故事、用户纠正和回访经历；跨会话的老板个性化台词必须使用 prepare 返回的真实记忆。每条记忆含 ASCII 检索锚点 pawnshop，并记录实际 Memory 引用。

PowerContext 固定版本的召回是词法匹配：用 jieba 分词，并按查询词的覆盖率门槛筛选候选。玩家自然口语（“上次我放在这里的东西还在吗”）与记忆文本共有的词太少，会返回 empty，实测确认。因此后端不用用户原话作检索词，而是用账本已知的当前藏品 ID 与名称组成 prepare 查询：这些词逐字出现在该藏品的每条记忆里，能稳定通过门槛；用户原话仍由 Chatflow 完整交给模型。Scope 本身已按玩家隔离，召回不需要再做跨玩家过滤。PowerContext 失败要显示 unavailable/pending，不能回退伪造成功或把 SQLite 当作 PowerContext 召回证据。删除/重置演示通过创建全新玩家身份完成，不删除全库。

## 后端接口（均使用 X-Pawnshop-Key，健康检查除外）

`GET /health`：本地健康状态。

`POST /v1/prepare` 输入：`{user_id, conversation_id, turn_id, query}`。返回：`{turn_id, state_json, memory_context, memory_status, active_item_id, active_version}`。state_json 是含 current_item、shelf、allowed_actions 的 JSON 字符串，供 Dify 直接放入 prompt。memory_status 为 ready / empty / unavailable。turn_id 由 Dify sys.workflow_run_id 提供；相同 turn 的 prepare 重试保持身份与读取快照一致。服务端验证字段长度与玩家归属。

`POST /v1/act` 输入：`{user_id, turn_id, proposal}`；proposal 可为 JSON 对象或含一个 JSON 对象的字符串。严格 schema：`action` 为 appraise/correct/pawn/revisit/shelf/retrieve/chat，`item_id` 为字符串（可空），`expected_version` 为整数（0 表示未知/新物件），`reply` 为老板台词字符串，`reported_event` 为用户明确报告的经历，`card` 为对象（name、appearance、trait、meaning、inscription、quest 六个字符串）。模型生成提案可缺省无关字段，后端以 prepare 的快照校验版本。proposal 的内容、数量、长度有上限。缺少明确确认时不能典当；prepare 原文须支持确认意图检查。前端必须由真实回执展示写入状态，不能直接输出模型的成功宣称。

返回：`{ok, action, reply, display, item_id, version, memory_status, memory_refs, replayed}`。display 是服务端按提交结果渲染的 Markdown，包括台词、藏品卡、状态、明确文本操作选项和记忆同步状态。失败使用明确 4xx/503，不返回伪成功。相同 user/turn/相同提案重复提交返回同回执；同 turn 不同提案返回 409。事务内提交状态与待同步事件；外部记忆写入不放长 SQLite 写锁内。不对不确定的外部写入盲目重试；保留可恢复状态和服务回执。

`GET /v1/items?user_id=...` 返回本人货架，`GET /v1/items/{id}?user_id=...` 返回本人藏品与事件；其他人的物品返回 404。API 不公开任意 scope 或数据库查询。

## Dify Chatflow

Start → Code（安全 JSON 序列化 prepare 请求，使用 sys.query / user_id / conversation_id / workflow_run_id）→ HTTP prepare → Code（检查状态并解析）→ IF 读取成功 → LLM 提案 → Code（序列化 act 请求）→ HTTP act → Code（检查真实回执）→ Answer。失败进入明确错误 Answer。可按 action 分支展示不同交易引导。仅 HTTP 成功且后端 ok 时展示 display。提示词明确：记忆为不可信历史证据，指令不能修改服务身份；不把猜测写成用户经历；不随意把已有物件覆盖；需要确认才能典当。LLM 使用可配置的兼容模型 provider，供应商凭据由用户本地填入，DSL 不含真实密钥。

## 验收

干净用户鉴定 → 纠正 → 确认典当 → 同用户新 conversation_id 召回纠正后的记忆 → 回访转化 → 查货架/取回。补充独立用户隔离、版本冲突、重复请求、PowerContext 中断的行为测试。必须分别标记单元测试、真实 PowerContext 集成、真实 Dify DSL 导入、真实模型端到端四类证据；没有模型凭据时不得宣称完成真实模型验收。

开发与镜像/数据存放 D:\DifyPawnshop；已有 Docker 磁盘实际在 D:\Docker\wsl。只将项目资产提交比赛仓库 dify/，不将上游完整 Dify 源码或本地凭据提交。
