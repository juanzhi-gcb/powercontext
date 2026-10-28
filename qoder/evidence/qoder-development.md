# Qoder 开发记录

## 项目与仓库

- 项目：NullPath / Research CI。
- 开发仓库：`AtoFuture/NullPath-Research-CI`，分支 `2026-competition-ecosystem`。
- 比赛提交仓库：`juanzhi-gcb/powercontext`，分支 `submit/qoder`，项目位于 `qoder/`；平台登记仓库固定，评测读取该分支。
- 官方 `oceanbase/powercontext` 仅作为基线与 PowerContext 实现参考，项目代码位于 `qoder/`。
- 主要需求拆解、FastAPI 与 React 实现、数据库接入、测试修复、Docker 调试、浏览器验收和发布准备均由 Qoder 在本次会话中执行。

## 实现过程

1. 将原始框架拆成研究事实源、连续工作台、确定性裁决、人工终审和历史回放五个边界。
2. 使用 PyMySQL 实现 seekdb 原生 SQL：64 维向量、IK 全文索引、结构化时间过滤、RRF 融合及原始分审计。
3. 使用 PowerContext 1.4.1 的 Scope、Atomic Memory、ETag 和精确 revision API，保存研究约束、活跃合同、指针与 Handoff。
4. 实现确定性资源/流程门槛、比较器引用校验、机器建议与人工裁决分写、实验结果同事务回流。
5. 实现 React 工作台，区分 Qoder Sites 静态演示与本地真实服务，不伪造在线后端。
6. 加入五个黄金案例、三种真实检索路径消融和固定历史时点的七项回归断言。
7. 使用 Docker Compose 启动 seekdb、PowerContext、bootstrap、API 和 Web，并在浏览器中完成真实新建预检、人工终审和历史回放。
8. 根据“保留 Research CI，但降低理解和使用门槛”的反馈，新增只读 `history-search`：一句话即可查询有出处的历史，不创建提案或裁决；完整预检改为渐进表单，报告改用中文结论并默认收起审计参数。
9. 根据“内置证据无法代表用户真实资料”的反馈，新增本地研究资料库：浏览器读取 Markdown/TXT，API 按段落切分并写入 seekdb；每段保留原文、资料日期、稳定 locator 与幂等 ID，导入记录直接进入既有混合检索和完整预检。
10. 根据“加一个秘书管理资料、让 PowerContext 有真实用途”的反馈，实现确定性研究秘书：扫描已导入资料，按词面 Jaccard 与向量余弦生成知识线、疑似重复和孤立资料提案；审阅状态持久化，只有人工接受的知识线写入 PowerContext 的 `secretary_context`，不修改 seekdb 证据、预检结论或人工裁决。另提供无模型调用的夜间扫描脚本与无摘录回执。
11. 根据“就要游戏化，这样才有人愿意用”和组员手绘角色的反馈，把默认入口改为「研究档案馆」：纸条输入、夜班馆员老余、检索回执、考据币与四级馆员等级。检索仍走同一只读 API，回执只标出处、不替用户决定；静态演示保留交互，但回执固定标注「演示回执」。
12. 根据“切换动态，不要静态演示”的反馈，把公开站点从固定样例改为浏览器内真实引擎：`web/src/blake2b.ts` 复刻服务端 BLAKE2b-128 哈希嵌入，`web/scripts/build-public-archive.py` 从 8 张重建卡和 2 篇公开论文摘要生成 10 条公开馆藏及 64 维向量，`web/src/publicEngine.ts` 执行中文二元词 + 停用词归一、词面/向量 RRF（0.6/0.4、k=60）、证据过滤、机制 Jaccard 比较、确定性门槛、时间边界与快照哈希。大厅与完整预检都改为按用户输入实时计算，报告版本标记为 `browser-*`。公开版仍明确声明不写入 seekdb、不读取 PowerContext、不执行人工终审。

## 实际修复记录

- 官方 pylibseekdb wheel 下载超时后，改用 PyMySQL 与 seekdb 原生 SQL，而非跳过真实数据库。
- 比较器可能返回未知证据 ID，在统一裁决边界增加引用集合与相似度范围校验。
- 补齐 storage 与 problem-before-baseline 的确定性检查，避免配置字段只展示不执行。
- 回放增加 cutoff、快照、规则/模型版本和上下文修订断言，能够识别回填数据造成的历史快照变化。
- 最终审计发现候选提案自身未校验 cutoff，已增加候选 `available_at <= cutoff` 边界与回归测试；真实 API 对未来提案返回 422，不保存运行。
- 修复真实 PowerContext entries 与独立 references 的哈希映射，浏览器研究状态页已显示 4 个真实条目且无控制台错误；报告页提供可全选的完整 run ID。
- 同时启动主验证 profile 时，两个 bootstrap 会竞争同一 PowerContext ETag；Compose 已改为串行初始化，重建后全部服务恢复。
- 修复静态/离线状态文案与人工终审提示：PowerContext 失败时只声明 seekdb 已保存，并显示上下文警告。
- 浏览器验收曾将一个新提案放在黄金 cutoff 前，导致 IBML 案例合理变为证据不足。没有修改预期或放宽规则，而是新增独立 `nullpath_validation` 数据库与 validation profile，隔离交互数据后重跑。
- Docker 凭据 helper 挂起时使用不含凭据的临时 `DOCKER_CONFIG`；未修改全局 Docker 凭据配置。
- 轻量检索首次真实验收发现无出处的新提案会占据前列，因此只在轻量入口过滤无证据记录；完整预检的召回和裁决逻辑不变，并增加只读与证据过滤回归测试。
- 浏览器验收确认自然语言检索结果可以一键带入完整预检，报告展示中文建议、检查原因和最小实验；内置点击工具未触发表单时使用 DOM 原生 `requestSubmit()` 验证，未将其误判为应用错误。
- 公开静态版原先禁用首屏示例和完整预检表单，造成按钮看似无效；现已开放交互，并明确标注检索结果与报告始终为固定 MOON 样例，不根据输入假装计算。
- 资料库没有另建一套检索，而是复用 attempt/evidence 模式：外部资料每段对应一条可召回记录与证据，避免迁移数据库；材料日期写入 `available_at`/`published_at`，资料早于 cutoff 时不会出现在比较中。
- 资料库验收时 in-app browser 一度只剩空白标签页；重新导航后完成真实导入。内置点击工具受预览视口限制时，改用 DOM 原生 `click()`，未将工具故障误判为应用故障。
- 资料库首轮验收发现：在内置测试记录较多、当前 cutoff 下，导入论文位列第 7 个向量候选，低于完整预检的 6 个融合候选上限；在干净且合法的 2026-03-01 cutoff 下，论文作为第 2 个比较出现。没有为截图调高召回上限或删除测试记录，记录真实边界。
- 秘书联调发现 PowerContext `list_kind` 的 artifact 引用嵌在 `artifact` 字段，而 save/get 返回扁平字段，导致 workspace/context revision 为 null；已统一两种响应形状并增加测试。
- 秘书每次运行都会更新 `updated_at`，曾让已接受上下文产生无意义的 revision 增长；已改为规范化 JSON 比较，内容未变时不写入新修订，首次没有接受项时也不创建空 artifact。
- 知识线标题曾被 `all`、`architecture`、`arxiv` 等泛词占据；已加入停用词、复数归一和标题噪声过滤，改用首篇资料标题加共享主题命名。提案 ID 仍由资料 ID 生成，因此修改标题不会丢失已有人工审阅结果。
- `GET /api/sources` 曾把内置演示卡误列为用户资料；已按 `source-` 命名空间过滤，只显示真实导入资料。
- 静态演示中的「修改审阅」仍可能调用真实 API；已改为只读提示，公开站点不会对固定样例发起写请求。
- 第二次真实预检中 Attention 论文进入 top-6 比较，BERT 未进入；当前 RRF 权重 0.6/0.4 与 limit 6 未为演示调整，作为已知召回边界记录。
- 档案馆角色最初用自绘 SVG 占位；组员交来手绘 `archivist.png` 后改为直接使用原图，并按图片烘焙背景调整遮罩、灯晕和移动端尺寸，避免露出矩形边界。
- 手机回执曾因 flex 拉伸导致页脚上方出现大片空纸；改为按内容收缩，并让证据立场徽标不换行，避免「支持」被挤成竖排。
- 短屏桌面回执曾把第二条证据压到粘性页脚以下；在 `max-height: 760px` 时隐藏机制摘要，优先保留出处，并给回执页脚加滚动阴影。
- 移动端顶栏的第三个导航项曾被裁掉；压缩导航内边距与字号后，「档案馆大厅 / 研究资料库 / 完整预检」在 390px 内完整显示，其余项横向滚动。
- 从回执点「继续正式考据」时，标题和机制曾被整段复制；改为标题取前 6 个词、机制留空，让用户自己补“为什么可能有效”。
- 用户反馈「推过去」点击没反应：曾要求至少 10 个字才提交，但短想法同样可以检索，限制只会制造摩擦；现已去掉字数门槛，只拦空输入，提交时读取 textarea 的实际值以避开中文输入法回填延迟，并在纸条上方显示明确提示。
- 公开版词面检索最初按单个汉字切词，BERT 别名中的「码」会误命中「代码迁移」；改为中文 bigram，同时保留单字查询。BLAKE2b 实现已用空串、ASCII、中文、长文本和多词查询与 Python 输出逐字节比对。
- 只用「词面分 > 0」作为召回门控时，IBML 示例会把仅共享 `control` 的 MOON 和仅共享 `two`/`jointly` 的 Attention、BERT 带进比较；增加常用停用词和「不低于最高词面分 25%」的相对门槛后，报告只保留 IBML broad phase diagram 一条历史比较，裁决仍为 `CONDITIONAL_GO`。
- 公开预检曾把无证据的 IBML identifiability narrow 排到首位，导致比较缺少可定位证据；现在检索池先过滤 cutoff 内无证据记录，报告带回 IBML broad phase diagram 的 3 条证据。
- 公开回执的长论文摘要视觉过重；机制文本截断到 260 字并保留两行 clamp。手机端回执表头改为堆叠，避免「PUBLIC ARCHIVE RECEIPT · 浏览器实时检索」与回执编号互相挤压。
- 用户反馈点击馆内入口会跳回浅色工作台、风格割裂；公开演示模式的全部入口改为在同一档案馆内打开纸页：我的馆藏、研究秘书、旧裁决、技术档案与正式考据分别渲染馆内纸页，回执的「继续」和抽屉菜单也走同一套；真实/自托管模式仍保留原工作台路由。旧裁决直接复用公开档案中的历史裁决与证据，不新增后端请求。
- 公开站馆内的「代码仓库」入口仍指向个人开发仓库，与平台登记的团队仓库不一致；已把大厅抽屉、技术档案和顶部仓库链接统一改为 `juanzhi-gcb/powercontext` 的 `submit/qoder` 分支，并在 README 增加比赛提交段落。

## 验证证据

| 验证 | 实际结果 |
| --- | --- |
| `uv run --extra dev pytest` | 20 passed |
| Ruff lint / format | All checks passed；18 files already formatted |
| 真实轻量检索 | `POST /api/history-search` 返回 seekdb 召回的历史与出处；不写提案、运行或裁决 |
| 真实资料导入 | `POST /api/imports/sources` 首次 `imported=1, skipped=0`；重复导入 `imported=0, skipped=1`；`GET /api/sources` 保留 `2017-06-12` 与 arXiv 原始链接 |
| 导入后检索 | 相关想法检索将导入论文列为第 1 条，证据 locator 为 `https://arxiv.org/abs/1706.03762` |
| 导入后完整预检 | `2026-03-01` cutoff 的运行将论文列为第 2 个比较，裁决 `INSUFFICIENT_EVIDENCE`，证据随比较返回 |
| 第二份资料导入 | BERT 摘要首次 `imported=1, skipped=0`，重复导入 `imported=0, skipped=1`；列表显示 `2018-10-11` 与 arXiv 原始链接 |
| 秘书扫描与人工接受 | 2 个资料分段生成 1 条 `knowledge_line` 提案；接受后 workspace rev 9、context rev 5；无模型调用 |
| 秘书上下文进入预检 | run `d7c41dfc-1a2c-4aae-b9f2-01634ed9bd40` 的 `context_refs` 固定 `secretary_context` rev 5；Attention 论文作为比较出现，BERT 未进入 top-6 |
| 夜间秘书脚本 | `run_secretary.py` 退出 0，回执写入 `evidence/secretary-last-run.json`；2 sources、0 new、1 proposal、1 accepted |
| 档案馆真实检索 | 真实主 API 下检索 “Replace recurrence with self-attention…” 召回 Attention 与 BERT 共 2 条记录、2 条可定位证据；回执盖章「有出处」，考据币 20→35 |
| 档案馆三档布局 | 1440×900、1024×768、390×844 均完成写纸条→回执；390×844 另完成继续正式考据，表单带入想法且机制留空；390px 无横向溢出，控制台 0 错误 |
| 档案馆移动导航 | 390px 下「档案馆大厅 / 研究资料库 / 完整预检」完整可见；档案柜抽屉可打开 |
| 静态演示回执 | 固定显示「演示回执」和“固定样例、不随输入重新检索”；仍可展开样例证据，不对固定样例发起写请求 |
| 档案馆提交反馈 | 空输入在纸条上方显示红色提示；1 字与 4 字输入均能提交并返回回执；绕过 React 回填直接写 DOM 值仍能提交；真实鼠标与手机触摸均通过，390px 无横向溢出 |
| `npm run build` | TypeScript 与 Vite 构建通过 |
| `npm audit` | 0 vulnerabilities |
| `evaluation/run_golden.py` | 5/5 真实 API 原运行及回放通过 |
| `evaluation/run_ablation.py` | vector 5/5、fulltext 5/5、hybrid 5/5，共 15 次真实 seekdb 运行 |
| 真实人工终审 | 机器建议保持不变；独立裁决写入 seekdb；active_pointer 与 handoff 指向同一 run |
| 真实历史回放 | 七项断言全部通过，结果持久化并显示在报告页 |
| 实验回流 | 实验与 `exp-…` 证据同时出现在 lineage，后续真实预检召回该证据 |
| Qoder Sites 公开更新 | 2026-10-27 发布 action `ace3d78d-46d0-40b9-bcb2-d21c9fd094c4` 到 `https://nullpath-research-ci-5dqanvro27t.qoder.zone`；匿名首屏、资料库与秘书固定演示通过，控制台无错误 |
| Qoder Sites 档案馆发布 | 2026-10-27 发布 action `3bfc2135-cbf4-4f30-91fc-1a7ec430d0b4` 到同一站点；线上入口引用与本地 `dist` 相同的 `index-DMegC5pi.js` / `index-k1bi_Idi.css`，匿名桌面 1440×727 与手机 390×844 均完成写纸条→回执，回执标注「演示回执」，考据币 20→35（同一浏览器移动端再查一次累加至 50），控制台 0 错误、无横向溢出 |
| Qoder Sites 提交门槛发布 | 2026-10-27 发布 action `6aa5a2e2-9d4d-4088-b5c1-4bd6b1a4be06` 到同一站点；线上入口引用 `index-CArjwl1m.js` / `index-6pI8IuTa.css`，空输入显示完整红色提示，4 字与 1 字输入均可提交并返回回执，桌面鼠标与手机触摸通过，控制台 0 错误、无横向溢出 |
| 公开版浏览器内检索 | `confirmation bias` → MOON original（2 条证据，「有出处」）；`self-attention transformer` → Attention + BERT；`今天天气` → 查无旧档且无继续按钮；`code alignment`、`moon`、`phase diagram`、`注意力` 分别命中对应馆藏；1440×900 与 390×844 控制台 0 错误、无横向溢出 |
| 公开版浏览器内预检 | 内置 IBML 示例在浏览器内返回 `CONDITIONAL_GO`、9 通过/0 失败、3 条证据、1 条历史比较（IBML broad phase diagram），比较中不再出现 MOON/Attention/BERT 噪声 |
| 动态公开版发布 | 2026-10-28 发布 action `d247e470-e73f-4dec-b51b-41ce85e54a4d` 到 `https://nullpath-research-ci-5dqanvro27t.qoder.zone`；线上入口引用 `index-C70i6bnz.js` / `index-DAY4czuc.css`，与本地 `dist` 一致，匿名桌面与手机端复测通过 |
| 公开大厅馆内导航 | 演示模式下「我的馆藏 / 正式考据 / 研究秘书 / 取回旧裁决 / 技术档案」、今日归档与底部入口全部在馆内打开纸页，侧栏保持隐藏；IBML 示例报告 9 通过 / 0 失败 / 3 条证据 / 1 条比较；1440×900 与 390×844 无横向溢出、控制台 0 错误 |
| 馆内导航修复发布 | 2026-10-28 发布 action `cd59dd92-93bb-40d3-be4b-11d1959b630f` 到同一站点；线上入口引用 `index-BRBSUW2S.js` / `index-DZ_-GYrD.css`，匿名桌面与 390px 手机打开旧裁决、技术档案与正式考据均在馆内，IBML 示例返回 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较，控制台 0 错误、无横向溢出 |
| 馆内仓库链接修复 | 2026-10-28 发布 action `314fef4f-0343-4e96-92b3-168a34598ee1`；当前线上引用 `index--PnxTbZK.js` / `index-DZ_-GYrD.css`，抽屉、技术档案和构建产物均只引用 `juanzhi-gcb/powercontext/tree/submit/qoder/qoder`；IBML 示例仍返回 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较，桌面无横向溢出、控制台 0 错误 |

详细机器结果见 `golden-results.json` 与 `ablation-results.json`。三路检索在这组小样本上都通过，不据此声称混合检索优于单路。

## 真实运行样例

- 浏览器新建预检返回真实 run ID、快照哈希和 2 个 PowerContext 引用。
- 最近邻没有 cutoff 内可定位证据时，返回 `INSUFFICIENT_EVIDENCE / NO_LOCATABLE_HISTORICAL_EVIDENCE`，没有误判成弱 NO-GO。
- 真实回放报告显示机器建议、必需证据、禁止证据、cutoff、快照、版本和上下文七类断言。
- 资料库导入 arXiv:1706.03762 的公开摘要后，持久记录为 `source-6dbddfe514fcbbc20e3952c3`；重复导入被识别为同一分段；相关想法检索与合法 cutoff 的完整预检均能带回论文和原始链接。第二份 arXiv:1810.04805 摘要记录为 `source-9e2b4e4f4201edde9263ac74`，重复导入返回 `skipped=1`。
- 秘书真实验收：2 个资料分段生成知识线 `knowledge_line-b07ab29f327216a0`（连接强度 0.3401），人工接受备注为“保留为 Transformer 注意力架构背景，不视为已复现结论”；PowerContext workspace 为 `art_59cb2c983ba4459282e7da58b9c080f8` rev 9，accepted context 为 `art_a7ea3aa28b9e42d68281641990de61dd` rev 5。
- 第二次真实预检：attempt `6e488e14-16cc-4f51-9900-6e01568475ce`，run `d7c41dfc-1a2c-4aae-b9f2-01634ed9bd40`，裁决 `INSUFFICIENT_EVIDENCE / NO_LOCATABLE_HISTORICAL_EVIDENCE`；`context_refs` 包含 `secretary_context` rev 5，比较中包含 Attention 论文，BERT 未进入 top-6。
- 实验回流验证使用明确标注的 synthetic API validation record，不将其冒充科学实验结果。

界面证据：

- `hall-desktop.png`：档案馆首屏（真实主 API，考据币 20，馆藏 2 份、知识线 1 条）。
- `hall-receipt.png`：真实检索回执，2 条召回、2 条可定位证据和「有出处」印章。
- `hall-mobile.png`、`hall-mobile-receipt.png`：390×844 手机首屏与两结果回执。
- `hall-drawer.png`：手机档案柜导航抽屉。
- `hall-demo-receipt.png`：早先静态站固定演示回执留档，曾显式标注「演示回执」和固定样例说明。
- `published-dynamic-hall-desktop.png`：2026-10-28 公开站点动态检索回执（1440×900），`self-attention transformer` 实时召回 Attention 与 BERT。
- `published-dynamic-hall-mobile.png`：公开站点 390×844 动态回执，`attention transformer` 返回两条带出处记录，表头堆叠不溢出。
- `published-dynamic-report-desktop.png`：公开站点浏览器内预检报告，IBML 示例得到 `CONDITIONAL_GO`、9 通过/0 失败、3 条证据、1 条历史比较。
- `published-hall-desktop.png`：早先公开站点桌面端固定演示回执（1440×727），保留作版本对比。
- `published-hall-mobile.png`：早先公开站点 390×844 手机端固定演示回执。
- `hall-empty-error.png`、`hall-mobile-empty-error.png`：空提交时的红色提示和「写得越具体，越容易翻到旧档」软提示。
- `hall-mobile-short-query.png`：4 字短查询也能提交并得到固定演示回执。
- `library-import.png`、`library-search.png`：真实导入资料及检索出处。
- `library-two-papers.png`：资料库同时显示 Attention 与 BERT 两份真实导入摘要，以及「让秘书梳理」入口。
- `secretary-review.png`：已接受的知识线、两份资料出处、workspace rev 9 与 accepted context rev 5。
- `workbench-demo.png`：移动端完整工作台。
- `replay-ui.png`：真实历史回放及七项回归断言。

## 复现入口

```bash
cd qoder
docker compose -f deploy/compose.yaml up --build

docker compose -f deploy/compose.yaml --profile validation up -d --build validation-api
cd server
uv sync --extra dev
uv run ruff check .
uv run pytest
uv run python ../evaluation/run_golden.py
uv run python ../evaluation/run_ablation.py
uv run python ../evaluation/run_secretary.py
```

## 边界与限制

- 演示卡是依据用户框架重建的功能验证材料，不是原始实验日志，也不代表外部论文结论。
- 资料库验收使用 arXiv:1706.03762 与 arXiv:1810.04805 的公开摘要，仅验证导入、去重、时间边界、检索和秘书链路，不声称它们是用户自己的实验或研究结论。
- 秘书是确定性实现：扫描、相似度与提案生成均无模型调用，夜间运行不产生 token 费用；定时任务仅在机器唤醒且本地 API 启动时执行，睡眠期间不会补跑。
- 秘书只生成提案并保存已接受的知识线，不会自动修改 seekdb 证据、预检结论或人工裁决；拒绝和暂缓的提案不会进入预检上下文。
- 完整预检默认取混合检索 top-6 比较；两篇导入论文中 Attention 能进入比较，BERT 在本次 cutoff 下未进入，这是当前 RRF 权重与召回上限的真实边界，未为演示调参。
- 默认模型为确定性本地实现；可选 LLM 只负责语义比较，硬门槛与最终机器建议由应用规则生成。
- 时间隔离只保证输入证据的 cutoff，不声称模型训练知识具有时间边界。
- Qoder Sites 公开版现在在浏览器内执行真实检索与确定性预检，但只针对随构建打包的 10 条公开馆藏（8 张重建演示卡 + 2 篇公开论文摘要，其中 5 条带可定位证据）；不会读取或上传访问者资料，结果不写入 seekdb、不读取 PowerContext、不能执行人工终审。资料导入、秘书扫描与审阅、持久化提交、终审、实验回流和可写回放仍需本地 Compose 服务。
- 公开馆藏是重建演示卡与公开论文摘要，不是访问者自己的实验日志；浏览器内引擎使用与服务端相同的算法版本标识，但公开版的检索分数与裁决只用于演示同一条规则链路，不替代本地真实数据的预检结论。
- 档案馆的考据币只保存在浏览器 `localStorage`，不上传，也不影响研究记录或裁决；等级只反映查证次数，不代表研究质量或结论可信度。角色与场景采用组员手绘插画和本地 CSS/SVG，不加载远程素材。
- 公开站点已于 2026-10-28 更新为浏览器内动态版本；匿名桌面 1440×900 与手机 390×844 均完成写纸条→实时回执和完整预检，结果随输入变化，控制台 0 错误、无横向溢出。公开版仍不连接在线后端，真实资料与持久化验证需按本地 Compose 步骤运行。
- 档案馆只拦空输入；1 个字或 4 个字的短查询同样可以提交，界面提示“写得越具体，越容易翻到旧档”，不会静默忽略点击。
- 本地 PowerContext 配置关闭访问控制，仅绑定回环地址，不能直接暴露公网。
- 代码推送与仓库公开由账号持有人执行；Qoder 仅完成本地提交与远端内容复核，未更改仓库可见性。

## 账号持有人操作

- 推送已由账号持有人完成：远端 `2026-competition-ecosystem` HEAD 为 `1a2819c2`，与本地一致，三个提交均在远端，默认分支已指向该分支。
- 仓库已设为公开；2026-10-27 匿名访问 `https://github.com/AtoFuture/NullPath-Research-CI` 返回 200，无需授权即可查看。
- 2026-10-28 将 `qoder/` 项目提交到大赛登记的团队仓库 `juanzhi-gcb/powercontext` 的 `submit/qoder` 分支，未改动队友共用的 `2026-competition-ecosystem`；平台填报该分支的完整 Commit。
- 仍需在 Qoder 客户端补充 Qoder 账号 UID，以及关键开发环节的对话截图或录屏。
