# 烦恼典当行 · 提交说明

一句话：玩家把一件烦恼放到柜台上，老余把它鉴定成一件奇幻藏品；玩家可以纠正鉴定、决定是否典当，之后在新会话里报告经历，藏品随记忆变化。

**技术选型：Dify 1.17.1 + PowerContext 1.4.0（HTTP API）+ FastAPI/SQLite 游戏后端 + 自定义柜台前端。不使用 seekdb；Dify 使用其官方默认 PostgreSQL，本项目不声称使用 seekdb。**

## 一、评审最快路径（Dify WebApp 入口）

1. 安装 Docker Desktop（WSL2 后端）、Python 3.12、`uv`、Git。
2. 在 `dify/` 目录执行：

   ```powershell
   uv run --no-project --python 3.12 python scripts/bootstrap.py --root D:/DifyPawnshop
   uv run --no-project --python 3.12 python scripts/manage.py up --root D:/DifyPawnshop
   ```

3. 打开 <http://localhost:18080> 初始化 Dify，配置一个 OpenAI 兼容的聊天模型 provider。
4. 导入 `dsl/pawnshop-chatflow.yml`。**如果 DSL 里的模型名不是你配置的模型**，打开 LLM 节点「老余拟鉴定单」，直接选择你已配置的模型即可；也可以按 `dsl/README.md` 用你的模型名重建 DSL。
5. 在该应用的环境变量里设置 `PAWNSHOP_API_KEY`，值必须与 `dify/deploy/.env` 中的同名变量一致；确认 HTTP 节点地址是 `http://pawnshop:8080`。发布应用。
6. 从 Dify 的 WebApp 进入，输入一件具体的烦恼开始玩。完整玩法见 [README](README.md) 和 [体验记录](docs/demo.md)。

自定义柜台前端是可选的增强入口：打开 <http://localhost:18081/>，需要在 `deploy/.env` 里把该 Dify 应用的 API 密钥填到 `DIFY_APP_API_KEY`（「访问 API」页生成），然后重启游戏服务。不配置它不影响 Dify WebApp 的正常体验。

## 二、材料索引

| 材料 | 位置 | 说明 |
|---|---|---|
| Dify DSL | `dsl/pawnshop-chatflow.yml` | 16 节点 Chatflow；导入、模型绑定、环境变量说明见 `dsl/README.md` |
| 运行说明 | `docs/runbook.md` | 环境、版本、部署、模型、网络、排错、重置 |
| 玩法与创意 | `README.md`、`docs/design.md`、`docs/demo.md` | 玩法、分工、真实运行摘录 |
| 验证步骤 | `docs/acceptance.md` | 逐步操作、预期结果、证据边界 |
| 样例数据 | `data/example-session.json` | 虚构样例，不是生产数据库 |
| 游戏后端 | `backend/` | FastAPI + SQLite；Dockerfile、依赖、测试 |
| 自定义前端 | `frontend/` | 纯静态 HTML/CSS/JS；立绘为内联 SVG |
| 部署 | `deploy/` | Compose、环境变量示例、固定版本清单 |
| PowerContext 证据 | `docs/evidence/services.json` | 真实后端 + 真实 PowerContext 的读写、跨会话召回、隔离 |
| Dify 端到端证据 | `docs/evidence/e2e.json` | 真实 Dify + 真实模型；含 prepare 节点实际交给模型的 `memory_status` 与 `memory_context` |
| 界面证据 | `docs/evidence/ui-*.png` | 柜台界面、藏品卡、记忆来历、手机布局、跨浏览器当票认领 |
| 导入/发布证据 | `docs/evidence/dify-*.json` | 真实 Dify 1.17.1 导入、干净重导入、发布 |

## 三、技术分工（实际发挥作用的地方）

- **Dify**：Start → Code 安全封装 → HTTP prepare → Code 校验 → LLM 提案 → Code 封装 → HTTP act → Code 校验回执 → Answer。模型调用、提示词、条件分支和最终展示都在 Dify 内。DSL 见 `dsl/pawnshop-chatflow.yml`。
- **PowerContext**：保存玩家明确说过的故事、纠正与回访经历；`prepare` 在每个 turn 读取并按玩家 Scope 隔离，`act` 在交易确认后写入并返回真实 Memory 引用。新会话里老板能接着上次的纠正说，是它实际工作的证据（`e2e.json` 的 `memory_status: ready` 和 `memory_context`）。
- **游戏后端**：SQLite 是权威交易账本；校验玩家身份、物件版本、明确确认语句和状态流转；记忆同步失败时如实显示 `pending/unknown`，不伪造召回。
- **自定义前端**：只做展示与输入，通过后端 BFF 调用同一个已发布 Dify 应用；浏览器不接触 Dify 应用密钥或游戏服务密钥。

## 四、验证样例

最短的一组：

1. 用一个全新玩家 ID（新浏览器/无痕窗口）进入，货架为空。
2. 说一个具体的烦恼，例如“我总拿自己和同龄人比较，看到别人的消息就不舒服”。
3. 老余给出草稿藏品；说“你鉴定错了，我不是嫉妒他们，我是觉得自己的努力一直没被看见”，卡片应实质变化。
4. 单独发送“确认典当”，状态变为已入柜，勇气币 +25。
5. 新开一段对话（同一当票），问“上次我放在这里的东西还在吗”，老板应沿用纠正后的理解；prepare 证据里 `memory_status` 为 `ready`。
6. 报告一段真实经历，例如“后来我把一直拖着的作品交出去了，虽然没什么人看”，藏品应变化且版本上升。
7. 查看货架、点「这件的来历」核对事件和 Memory 引用；取回物件。

可执行验证：

```powershell
uv run --project backend python scripts/verify_services.py
uv run --project backend python scripts/verify_e2e.py --root D:/DifyPawnshop
# 可选，需要 Node.js 与本机 Edge：
npm install; npm run verify:ui
```

重置演示：使用新的玩家 ID 即可；不要删除数据库。

## 五、已知边界

- 模型凭据、Dify 应用 API 密钥、服务密钥都由评审在本机填入，提交材料不含真实密钥。
- 自定义前端的完整验收需要 Node.js 与本机 Edge；只用 Dify WebApp 时不需要。
- PowerContext 固定版本的召回是词法的，后端用账本中的藏品 ID/名称做检索锚点；未启用 Embedding 或 Rerank。
- 勇气币是动作记录与余额，目前没有消费出口；不按烦恼轻重计分。
- 作品不使用 seekdb，也不声称 Dify 使用 seekdb；如赛事要求 seekdb 方案，需要另做适配，不在本提交范围内。

## 六、提交检查表

- [x] Dify DSL（`dsl/pawnshop-chatflow.yml`）与导入/绑定说明
- [x] 运行说明（环境、版本、模型、插件、网络、排错）
- [x] 可执行的验证样例与真实运行证据（JSON + 截图）
- [x] 自定义后端/前端源码、依赖清单、Dockerfile、Compose
- [x] PowerContext 固定版本、初始化方式、实际读写与跨会话召回记录
- [x] 无真实密钥、无本地凭据、无上游完整源码进入提交目录