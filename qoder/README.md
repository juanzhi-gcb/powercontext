# NullPath / Research CI

基于历史证据的研究决策回归系统。在投入大量时间、工程和算力之前，对候选路线执行混合检索、证据追溯、确定性预检、机器建议和固定时间点回放。

默认入口是「研究档案馆」：不需要先填写完整提案或资源配置，把想法写在纸条上推给夜班馆员老余，先拿到一张只标出处的检索回执。轻量检索是只读的，不保存提案、不生成裁决；查证动作会累积考据币与馆员等级，但结论本身不奖励。回执可以直接继续进入完整预检，获得正式机器建议和最小判别实验，检索分数、Run ID、cutoff 等审计信息默认收起。

机器建议只有 `NO_GO`、`CONDITIONAL_GO`、`INSUFFICIENT_EVIDENCE`。证据不足不等于弱 NO-GO；人工终审独立保存，不能改写机器建议。

研究资料导入后，「研究秘书」会扫描资料库并提出知识线、疑似重复或孤立资料提案；只有人工接受的知识线才写入 PowerContext，作为后续预检的上下文引用。秘书不新增或修改 seekdb 中的证据与裁决。

## 技术分工

- **seekdb：研究事实源。** 保存研究尝试、证据、比较、检查、运行、实验和人工裁决；使用向量、全文和结构化过滤进行 RRF 混合召回。
- **PowerContext：连续工作台。** 用 Atomic Memory 保存研究约束、当前合同、活跃指针、Handoff，以及人工接受的知识线；运行只固定 Artifact ID、revision 与 SHA-256，不复制裁决正文。
- **研究秘书：提案型资料管理。** 扫描已导入资料，用词面重叠与向量相似度提出知识线、疑似重复和孤立资料；稳定提案 ID 保留人工审阅结果。只有接受后才写入 PowerContext，不修改证据、预检结论或人工裁决。
- **FastAPI：应用边界。** 执行确定性门槛、比较器输出校验、运行保存、秘书扫描和历史回放。
- **React：研究工作台。** 提供“档案馆大厅”游戏化查档回执、“研究资料库”“研究秘书”、完整预检、中文报告、证据链、历史回放、上下文和复现入口。

默认使用 `hashing-char-word-64-v1` 和 `deterministic-mechanism-v1`，无需 API Key 即可离线复现。可选 OpenAI-compatible 服务只负责嵌入或机制比较，不能直接写最终裁决。

## 启动完整应用

要求：Docker Desktop；本地验证另需 Python 3.11–3.13 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd qoder
cp .env.example .env
# .env 中的凭据默认留空；不要提交真实密钥。
docker compose -f deploy/compose.yaml up --build
```

启动顺序为 seekdb + PowerContext → bootstrap 导入演示卡并写研究约束 → API → Web。启用 validation profile 时，验证 bootstrap 在主 bootstrap 后串行执行，避免并发更新同一 PowerContext 研究约束产生 ETag 冲突。

- 工作台：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8080/docs
- 健康检查：http://127.0.0.1:8080/api/health
- PowerContext：http://127.0.0.1:8000

所有宿主机端口仅绑定 `127.0.0.1`。PowerContext 在此本地 Compose 中关闭访问控制，不能将该配置直接暴露到公网。

## 主要使用流程

1. 打开「档案馆大厅」，在纸条上写下研究想法，按 Enter 或点「推过去」。本地版真实调用 `POST /api/history-search` 和 seekdb 混合检索，只读查询，不保存提案、不生成裁决；公开版没有在线 API，改由浏览器内引擎对打包的公开馆藏执行同样的混合检索。
2. 收到「检索回执」：命中旧档会列出机制摘要和可定位证据，盖章为「有出处」「待补出处」或「查无旧档」；展开证据条可看原文与稳定 locator。每完成一次查证会加考据币，找到出处额外加成，结论本身不奖励。
3. 如需正式建议，在回执点「继续正式考据」，想法会带入完整预检；补充“为什么可能有效”、与历史的差异和最小实验条件。
4. 点「生成避坑报告」，查看中文建议、检查依据和最小判别实验；展开技术详情可核对检索分数、快照与 Run ID。
5. 可选：打开「研究资料库」，导入自己的论文笔记、复现记录或技术报告；填写原文日期，单文件还可填写原始链接。重复内容会自动跳过，导入资料会进入同一条召回路径。
6. 可选：打开「研究秘书」，点击「重新扫描资料」，逐条审阅知识线、疑似重复或孤立资料提案。接受的知识线会写入 PowerContext，并成为后续预检的上下文引用。

如果没有导入资料，仍可使用内置演示卡体验同一条检索与预检链路。公开 Qoder Sites 不返回固定样例：它在浏览器内对随构建打包的公开馆藏执行真实的 64 维哈希嵌入、词面+向量 RRF 检索和同一套确定性预检规则，结果随输入变化。公开版仍不连接在线后端，也不读取或上传访问者资料；资料导入、秘书、PowerContext、人工终审与可写回放需要本地 Compose。

### 档案馆大厅与考据币

- 首次进入赠送 20 考据币；每完成一次查证 +10，查到可定位出处再 +5。等级依次为见习馆员（0）、夜班馆员（50）、考据员（120）、首席考据官（240）。
- 考据币只保存在浏览器 `localStorage` 的 `nullpath.coins.v1`，不上传，不影响研究记录；更换浏览器或清理站点数据会重置。
- 回执只说明“查到了什么”，不替用户做决定；「继续正式考据」仍进入同一套确定性预检与独立人工终审。
- 角色「老余」是组员手绘的静态插画（`web/src/assets/archivist.png`）；背景、灯、柜台与回执用 CSS/SVG 绘制，不加载远程素材。

## 连接自己的研究资料

- 第一版支持 `.md`、`.markdown`、`.txt`，每次最多 10 份、每份不超过 50,000 字符。文件在浏览器读取，内容只发送到当前本地 API 和你的 seekdb。
- 长文按段落边界自动分段；每段保留原文、标题、locator、资料日期和来源类型。重复分段的稳定 ID 相同，因此重复导入只返回 `skipped`，不会重复写入。
- 资料日期写入该记录的 `available_at` 与证据 `published_at`，早于该日期的 cutoff 不会召回它。导入记录会参与快照哈希，可被历史回放复核。
- 单文件可填写论文或报告的原始 HTTP 链接，检索结果中的出处可直接打开；留空或批量导入时使用 `local-library/<path>`，不会伪造外部链接。
- 导入资料进入同一条 seekdb 向量 + 全文 + 时间过滤召回路径。实际验收中，arXiv 论文摘要在相关想法检索和合法 cutoff 的完整预检中都被召回，并带回原始链接。

## 研究秘书

秘书是一个确定性的资料管理员，不是会改写研究结论的自动代理：

- 扫描 `source-…` 命名空间下的已导入资料，用词面 Jaccard 与 64 维向量余弦提出 `knowledge_line`、`near_duplicate`、`orphan` 提案。
- 提案 ID 由排序后的资料 ID 哈希生成；标题或摘要变化不会丢失已有审阅结果。
- 审阅状态有 `proposed`、`accepted`、`rejected`、`snoozed`。只有 `accepted` 的知识线写入 PowerContext 的 `secretary_context` artifact；被拒绝或暂缓的提案不会进入预检上下文。
- seekdb 仍是唯一研究事实源。秘书不写 attempt、evidence 或 decision，也不改动机器建议。

真实验收中，资料库包含两篇公开论文摘要（Attention Is All You Need、BERT），秘书提出 1 条知识线 `knowledge_line-b07ab29f327216a0`，人工接受后：

- workspace artifact：`art_59cb2c983ba4459282e7da58b9c080f8`，revision 9；
- accepted context：`art_a7ea3aa28b9e42d68281641990de61dd`，revision 5；
- 后续真实预检 `d7c41dfc-1a2c-4aae-b9f2-01634ed9bd40` 的 `context_refs` 包含 `secretary_context` revision 5，并召回了 Attention 论文作为比较。

### 夜间扫描

`evaluation/run_secretary.py` 只调用一次 `POST /api/secretary/runs`，并写一份不含原文摘录的回执，默认保存到 `~/.local/state/nullpath/secretary-last-run.json`，避免把本地资料标题提交进仓库。

```bash
cd qoder/server
uv run python ../evaluation/run_secretary.py
# Secretary secretary-20261027T082231Z: 2 sources, 0 new, 1 proposals, 1 accepted.
```

可放入 cron（示例，需替换路径）：

```cron
30 2 * * * cd /path/to/nullpath-research-ci/qoder/server && /path/to/uv run python ../evaluation/run_secretary.py >> ~/.local/state/nullpath/secretary.log 2>&1
```

这一版秘书是确定性实现，没有任何模型调用，也没有 token 成本，因此“夜间低价时段”不会改变费用；定时运行的意义只是让资料扫描与提案刷新发生在空闲时段。真正需要夜间省 token 的是未来可选的 LLM 摘要环节。定时任务还要求机器保持唤醒且本地 API 已启动；macOS 可使用 launchd，睡眠期间 cron 不会补跑。

验收回执 `evidence/secretary-last-run.json` 是在确认只包含公开论文标题和计数、不含原文摘录后，单独复制进仓库的；日常运行仍默认写到仓库外。

## 验证

```bash
cd qoder
docker compose -f deploy/compose.yaml --profile validation up -d --build validation-api
cd server
uv sync --extra dev
uv run ruff check .
uv run pytest
uv run python ../evaluation/run_golden.py
uv run python ../evaluation/run_ablation.py
uv run python ../evaluation/run_secretary.py
```

验证 profile 使用独立的 `nullpath_validation` 数据库和 `127.0.0.1:8081` API，避免工作台新增的历史提案进入黄金 cutoff；它仍使用真实 PowerContext 精确修订。主应用数据库与交互记录不会被验证脚本清空或改写。

当前后端验证为 `pytest` 20 passed，Ruff check 与 format check 通过。秘书脚本默认连接主 API `127.0.0.1:8080`，可用 `--api` 指向其他实例。

黄金脚本通过真实验证 API 运行五个案例，并再次创建固定原 cutoff 与上下文修订的回放。结果写入 `evidence/golden-results.json`；任一裁决、必需证据、禁止证据或时间边界断言失败都会返回非零状态。可用 `NULLPATH_API_URL` 覆盖验证 API 地址。

资料库闭环通过真实主 API 验收：导入 `evidence/library-import-fixture.md`（arXiv:1706.03762 的公开摘要与原始链接），第一次返回 `imported=1, skipped=0`，重复导入返回 `imported=0, skipped=1`；`GET /api/sources` 保留 `2017-06-12`、`https://arxiv.org/abs/1706.03762` 和稳定 `source-…` ID。相关想法检索将论文排在首位；在 `2026-03-01` cutoff 的真实预检中，论文作为第 2 个比较出现并带回原始出处。

档案馆首屏通过真实主 API 验收：输入 “Replace recurrence with self-attention to model long-range dependencies” 后，回执展示 Attention 与 BERT 两条真实召回及各自可定位出处，盖章「有出处」，考据币从 20 增至 35；点「继续正式考据」会把想法带入表单，机制字段留空等待补充。桌面 1440×900、1024×768 与手机 390×844 三档均完成“写纸条 → 回执”，390×844 另验证了继续预检与表单带入；控制台无错误，手机无横向溢出。公开静态构建现在改用浏览器内引擎：同一份输入会执行真实的哈希嵌入、词面+向量 RRF 检索与确定性预检，不再回放固定样例。2026-10-28 发布动态版到公开站点；`confirmation bias` 召回 MOON original（2 条证据），`self-attention transformer` 召回 Attention 与 BERT，`今天天气` 返回「查无旧档」且不提供继续按钮；IBML 示例在浏览器内得到 `CONDITIONAL_GO`、9 项通过、0 项失败、3 条证据和 1 条历史比较。桌面 1440×900 与手机 390×844 均无横向溢出、控制台 0 错误。纸条只要非空就能提交，1–4 个字的短查询也会照常查档；空纸条会在上方提示先写一句，不会静默忽略点击，输入框旁只保留“写得越具体，越容易翻到旧档”的软提示。公开大厅的次级入口也收进了馆内：底部「我的馆藏 / 取回旧裁决 / 技术档案」、侧边与研究秘书、今日归档和抽屉菜单都会在当前大厅打开纸页式档案，不再跳回浅色工作台；「正式考据」在馆内打开浏览器预检表单，报告同样以纸页呈现。同日以 action `cd59dd92-93bb-40d3-be4b-11d1959b630f` 重新发布馆内导航修复，线上入口引用 `index-BRBSUW2S.js` / `index-DZ_-GYrD.css`；匿名桌面与手机复测五个入口和 IBML 报告，均无横向溢出、控制台 0 错误，线上预检返回 `CONDITIONAL_GO`（9 通过 / 0 失败 / 3 条证据 / 1 条比较）。

第二份验收材料 `evidence/library-import-fixture-bert.md`（arXiv:1810.04805 的公开摘要）同样首次导入 1 段、重复导入跳过 1 段；两篇论文共同进入秘书扫描。秘书闭环使用真实主 API 验收：2 个资料分段生成 1 条 `knowledge_line` 提案，人工接受后上下文 revision 为 5；随后的真实预检 `d7c41dfc-1a2c-4aae-b9f2-01634ed9bd40` 在 `context_refs` 中固定该 revision，并召回 Attention 论文。该预检中 BERT 未进入 top-6 融合比较，这是当前召回上限与 RRF 权重的已知边界，未为演示调高上限。回执见 `evidence/secretary-last-run.json`。

消融脚本直接复用真实 seekdb 检索路径，分别运行 vector-only、fulltext-only 和 hybrid，记录每个案例的召回与裁决。结果写入 `evidence/ablation-results.json`；只有 hybrid 的全部案例通过时才返回成功，不用预设其他两路必须失败。可用 `NULLPATH_VALIDATION_DATABASE` 覆盖独立验证数据库名。

验证材料：

- `examples/archive.json`：MOON、IBML/ARL、CodeAlign 的八张重建演示卡。
- `examples/sources/`：可定位的演示出处。
- `evidence/library-import-fixture.md`、`evidence/library-import-fixture-bert.md`：资料库与秘书验收使用的真实公开论文摘要，不是用户实验结果。
- `evidence/secretary-last-run.json`：秘书夜间脚本的无摘录回执，包含扫描计数、提案 ID 与 PowerContext artifact 修订。
- `evidence/hall-*.png`：档案馆首屏、真实检索回执、移动端回执、档案柜和静态演示回执的界面留档。
- `evidence/published-dynamic-hall-desktop.png`、`evidence/published-dynamic-hall-mobile.png`：2026-10-28 公开站点桌面与手机端动态检索回执（Attention + BERT）。
- `evidence/published-dynamic-report-desktop.png`：公开站点浏览器内预检报告（IBML 示例，CONDITIONAL_GO）。
- `evidence/published-hall-sheets-desktop.png`、`evidence/published-hall-sheets-mobile.png`：2026-10-28 馆内导航修复后的公开站点历史裁决纸页（桌面与手机）。
- `evidence/published-hall-sheets-report.png`：同一次发布中，公开站点浏览器内 IBML 预检报告（9 通过 / 0 失败 / 3 条证据 / 1 条比较）。
- `evidence/published-hall-desktop.png`、`evidence/published-hall-mobile.png`：早先固定样例版公开回执留档。
- `evaluation/golden_cases.json`：预期裁决、必需证据和禁止的未来证据。
- `evidence/`：实际运行结果、界面截图与 Qoder 开发记录。

这些材料用于功能验证，不是原始实验日志，也不声称对应外部论文的真实结论。

## 静态网站与本地应用的边界

Qoder Sites 发布的是 `web/dist` 静态版本，但公开版不是截图或固定回执。`web/.env.production` 启用公开演示模式（`VITE_DEMO_MODE=true`），前端通过 `web/src/publicEngine.ts` 在浏览器内执行：

- 与服务端一致的 BLAKE2b 64 维哈希嵌入（`web/src/blake2b.ts`），以及中文二元词、停用词和复数归一后的词面评分；
- 词面与向量两路 RRF 融合（权重 0.6/0.4、k=60、每路 8、融合 6），并只保留与最高词面分相对差距不超过 25% 的记录；
- 同一套 `research-ci-rules-v1` 确定性检查、机制 Jaccard 比较、候选时间边界和快照哈希。

公开馆藏由 `web/scripts/build-public-archive.py` 从 `examples/archive.json` 与两篇公开论文摘要生成，共 10 条记录，其中 5 条带可定位证据；嵌入向量在构建时生成，随静态资源一起发布。报告和回执中的版本号会标明 `browser-vector-fts-rrf-v1` 等公开版实现。

公开版仍然不连接在线后端：结果不写入 seekdb、不读取 PowerContext、不能执行人工终审，也不导入访问者文件。资料导入、秘书扫描与审阅、持久化提交、终审、实验回流和可写回放需要本地服务，不会伪造在线摄取。

公开站点：https://nullpath-research-ci-5dqanvro27t.qoder.zone

Compose 的 Web 构建显式设置 `VITE_DEMO_MODE=false`，覆盖静态演示配置并连接真实 API。

```bash
cd qoder/web
npm ci
npm run dev       # 本地开发；/api 代理到 127.0.0.1:8080
npm run build     # 静态展示产物
npm run preview
```

## API 闭环

1. `POST /api/history-search` 用自然语言执行只读混合检索，返回有原始证据的历史记录；不创建提案、运行或裁决。
2. `POST /api/imports/sources` 将 Markdown/TXT 文本分段写入 seekdb，保留资料日期和 locator；稳定 ID 保证重复导入幂等。`GET /api/sources` 列出已导入资料。
3. `POST /api/secretary/runs` 扫描已导入资料并生成或刷新提案；`GET /api/secretary` 读取工作区、提案和已接受上下文；`POST /api/secretary/reviews` 保存接受、拒绝或暂缓。只有接受的知识线写入 PowerContext。
4. `POST /api/attempts` 创建候选研究。
5. `POST /api/evaluation-runs` 校验候选 `available_at <= cutoff`，固定快照、版本和上下文修订并生成机器建议；未来候选不能回放到过去。
6. `GET /api/attempts/{id}/lineage` 查看证据、比较、运行、实验与人工裁决。
7. `POST /api/decisions` 保存独立人工终审，再更新 PowerContext 指针和 Handoff。
8. `POST /api/experiments` 将最小实验结果在同一事务中写为实验和可检索证据。
9. `POST /api/replays` 使用原运行的时间与上下文修订执行回归断言。

PowerContext 更新失败会返回 `context_warning`；已经提交到 seekdb 的研究事实不会被静默回滚或伪装成功。

## 来源与改动

- PowerContext 服务使用 `oceanbase/powercontext` 的 `powercontext-v1.4.1` 镜像构建上下文。
- seekdb 使用 `oceanbase/seekdb:latest`。
- Web 基于 Qoder Sites React starter，替换为 NullPath 的九视图工作台、视觉系统、API 客户端和 Nginx 配置。
- 档案馆角色「老余」由组员手绘提供，用于本项目首屏与回执场景；页面其余背景、灯与柜台为 CSS/SVG 绘制。
- 公开版浏览器内检索引擎（BLAKE2b、哈希嵌入、中文 bigram、RRF 与确定性规则）为本项目实现，版本标识与服务端保持一致。
- 项目应用代码、数据库模式、演示卡与黄金验证为本项目实现。外部依赖保留各自许可证。
