# 验收说明

本文列出可复现流程、期望行为和证据范围。期望结果描述功能，不限定模型生成某句固定台词或某张固定奇幻物品卡。

## 证据状态

下表记录 2026-10-27 在本机实际执行的结果。证据文件由脚本直接写出，未经手工改写；没有记录的项目状态是“待执行”，不是“通过”。

执行环境：Windows 11 + WSL2 + Docker Desktop；Dify 1.17.1（Compose 项目 `pawnshop-dify`，<http://localhost:18080>）；游戏后端（`pawnshop-game`，<http://localhost:18081>）；PowerContext 1.4.0（commit `31ecdd61beadb7ac8de5da20998dead9a9e07845`，<http://localhost:18082>）；Chatflow 模型经 Dify 的 OpenAI 兼容 provider 接入，模型名与凭据只保存在本机配置。

| 类别 | 执行方式 | 实际结果 | 证据 |
|---|---|---|---|
| 1. 后端行为测试 | `uv run --project backend --group dev pytest tests/backend -q` | 23 passed | 命令输出 |
| 1. DSL 节点与静态检查 | `uv run --project backend --group dev pytest tests/test_dsl.py -q` | 61 passed | 命令输出 |
| 2. 真实后端 + 真实 PowerContext | `uv run --project backend python scripts/verify_services.py` | passed；纠正、确认典当、跨会话召回、回访、货架隔离、跨玩家拒绝、重复提交、取回 | [services.json](evidence/services.json)，标记 `dify_model_executed: false` |
| 3. 真实 Dify 导入与干净重导入 | `uv run --project backend --group dev python scripts/configure_dify.py --root D:/DifyPawnshop [--new-app]` | completed，16 节点；`model_executed: false` | [dify-import.json](evidence/dify-import.json)、[dify-reimport.json](evidence/dify-reimport.json) |
| 3. 真实 Dify 应用发布 | Dify 控制台发布 + 模型 provider 绑定 | published | [dify-publish.json](evidence/dify-publish.json) |
| 4. 真实 Dify + 真实模型端到端 | `uv run --project backend python scripts/verify_e2e.py --root D:/DifyPawnshop` | passed；鉴定、纠正、确认典当、新会话召回、回访转化、玩家隔离 6 步 | [e2e.json](evidence/e2e.json)，标记 `model_executed: true` |

`verify_services.py` 只覆盖第 2 类：它直接调用真实后端与 PowerContext HTTP，使用脚本构造的虚构请求，不启动 Dify、不调用模型。第 4 类由 `verify_e2e.py` 覆盖：它通过 Dify 服务 API 驱动已发布应用，再用控制台 API 读回同一 `workflow_run_id` 的节点执行记录，因此证据里保存的是 prepare 节点实际交给模型的 `memory_status` 与 `memory_context`，而不只是模型的回答文本。

尚未执行、因此不能宣称通过的项目：

- Dify WebApp 在浏览器/设备之间的登录身份连续性（API 场景已用固定 `user` + 新 `conversation_id` 验证）。
- 换机器按手册从零复现的完整流程（本机路径已验证）。
- PowerContext 中断期间的真实 Dify 对话表现（后端层面的 pending/unavailable 行为已有自动化测试）。

## 手动端到端主流程

前置条件：Dify 1.17.1、游戏 API 和 PowerContext 正在运行；在 Dify 配好自己可用的兼容聊天模型；项目生成的 Chatflow DSL 已导入、设置正确的 `PAWNSHOP_API_KEY` 环境变量并发布。开始时使用一个此前未用过的玩家 ID。

| 步骤 | 玩家操作 | 预期行为 |
|---|---|---|
| 1. 鉴定 | 描述一个烦恼，例如“我总拿自己和同学比较”。 | 老余给出奇幻物品草稿和叙事邀请；它是可纠正的虚构鉴定，不应被表述为诊断。货架或当前物件显示草稿状态。 |
| 2. 纠正 | 指出鉴定误解，例如“我不是嫉妒，是觉得努力没人看见”。 | 系统据玩家纠正更新草稿内容，不把模型猜测记录为玩家经历。尚未确认时不应显示已经典当。 |
| 3. 确认典当 | 单独发送精确文字 **“确认典当”**。 | 后端回执确认状态变化后，才显示已入柜。仅有模型提案、含糊同意或其他文字不应完成 pawn 交易。 |
| 4. 新会话回访 | 在同一玩家身份下新建 conversation，询问老余是否记得物件或补充一段新经历。 | prepare 用该玩家身份从 PowerContext 读取已确认故事；老余可沿用纠正后的主题。记忆不可用时如实显示不可用/待同步，不伪称回忆成功。 |
| 5. 回访转化 | 描述一段与物件相关的新经历，并请求回访。 | 若状态允许，物品版本上升、故事内容发生有依据的变化；SQLite 回执决定是否成功。生成内容应呼应用户明确叙述，不强行替用户推断结局。 |
| 6. 查看货架 | 发送“查看货架”。 | 返回该玩家的物品、状态和版本；不应展示其他玩家物件。 |
| 7. 取回 | 发送取回意图，例如“取回这件物品”。 | 仅在可取回状态下执行；成功与否以服务端回执为准，失败时不能宣称已取回。 |

每次新验收从新的固定玩家 ID 开始。通过 Dify `/chat-messages` API 测试时，跨请求保持同一个 `user` 值，并在新会话时更换 `conversation_id`；同时确认 Chatflow 传入后端的 `user_id` 在这两次请求中一致。API 场景中，多轮可使用同一个 `user_id`，每次调用使用本轮返回要求的独立 `turn_id`；重复同一 turn 与同一提案应返回幂等回执，同一 turn 提交不同提案应冲突失败。浏览器/WebApp 的用户身份不一定能在新浏览器保持，身份连续性应使用上述 API 或同一已验证的 Dify 用户身份测试。

## 服务集成脚本

从 `dify/` 目录运行：

```powershell
uv run --project backend python scripts/verify_services.py
```

脚本为每次执行生成随机 `acceptance-…` 虚构玩家，直连后端和 PowerContext；验证纠正、确认典当、记忆同步与新会话读取、回访版本变化、货架隔离、跨玩家物品拒绝、重复提交和取回。默认输出为 `docs/evidence/services.json`。该记录不得标作 Dify 或真实模型验收。脚本失败时保留实际错误和环境说明，不得手工改写为通过。

## Dify 端到端脚本

前置条件：Dify 已初始化并发布本项目的 Chatflow，`D:/DifyPawnshop/dify-local.json` 中有已发布应用的 `app_id` 与 `api_key`，`D:/DifyPawnshop/local-credentials.json` 中有可登录的控制台账号，后端与 PowerContext 正在运行。

```powershell
uv run --project backend python scripts/verify_e2e.py --root D:/DifyPawnshop
```

脚本使用全新的 `e2e-…` 虚构玩家，按下列顺序执行并逐步断言：鉴定出新草稿 → 玩家纠正后草稿内容实质变化 → 单独发送“确认典当”后入柜且记忆 `synced` → 同一 `user` 新建 `conversation_id` 后 prepare 返回 `ready` 且召回内容含玩家纠正原文 → 报告经历后物件转化且版本上升 → 另一位玩家看不到该货架与藏品。

每一步都会从该轮 `workflow_run_id` 的节点执行记录中提取 prepare 与 act 的真实输出，连同 Dify 回答一起写入 `docs/evidence/e2e.json`。脚本不读取、不打印任何模型凭据；失败时同样写文件并把该步标记为 failed，不得手工改成通过。

## 已知限制

- 奇幻物品、比喻和老余的解释是创作性叙事，不是事实诊断、治疗建议或未来预测。
- 模型调用需要用户自行配置可用的 provider、API 凭据和网络访问；目前不预置模型供应商凭据。
- PowerContext 不可用时跨会话记忆不可保证；系统应明确报告不可用或待同步，不可把 SQLite 账本描述为 PowerContext 的召回证据。
- Dify WebApp 的浏览器用户身份连续性取决于实际部署和登录方式，不能假定换浏览器后自动沿用同一游戏玩家。
- PowerContext 的召回是词法的（jieba 分词 + 查询词覆盖率门槛），自然口语问句通常不足以命中历史记录。因此后端用账本中已有藏品的 ID 与名称构造检索锚点，用户原话仍完整交给模型。若未来更换为向量检索，可再评估这一约定。
- 本文件的记录对应上面写明的本机环境。换机器复现必须重新执行并补充证据；静态文件检查或旧日志不能推出新环境的结果。
