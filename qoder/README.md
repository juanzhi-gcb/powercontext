# NullPath / Research CI

基于历史证据的研究决策回归系统。在投入大量时间、工程和算力之前，对候选路线执行混合检索、证据追溯、确定性预检、机器建议和固定时间点回放。

默认入口是「研究档案馆」：不需要先填写完整提案或资源配置，把想法写在纸条上推给夜班馆员老余，先拿到一张只标出处的检索回执。轻量检索是只读的，不保存提案、不生成裁决；查证动作会累积考据币与馆员等级，但结论本身不奖励。回执可以直接继续进入完整预检，获得正式机器建议和最小判别实验，检索分数、Run ID、cutoff 等审计信息默认收起。

机器建议只有 `NO_GO`、`CONDITIONAL_GO`、`INSUFFICIENT_EVIDENCE`。证据不足不等于弱 NO-GO；人工终审独立保存，不能改写机器建议。

研究资料导入后，「研究秘书」会扫描资料库并提出知识线、疑似重复或孤立资料提案；只有人工接受的知识线才写入 PowerContext，作为后续预检的上下文引用。秘书不新增或修改 seekdb 中的证据与裁决。

## 比赛提交

- 作品网站：<https://nullpath-research-ci-b4ket19m2lz.qoder.zone>
- 提交仓库：<https://github.com/juanzhi-gcb/powercontext>，分支 `submit/qoder`，项目目录 `qoder/`。
- 本地运行与验证：见下文「启动完整应用」与「验证」。
- 开发记录与验收材料：`evidence/qoder-development.md`、`evidence/`。

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
- 角色「老余」是组员手绘的插画（`web/src/assets/archivist.png`），眼睛、嘴部由 SVG 叠加：值班与听人写字时保留原画闭眼微笑，翻档、有出处、没翻到、出错时才睁开暖褐小眼并会随机眨眼，购章后单眼眨眼；心情用头顶的三连圆形思考气泡表示，大气泡内按状态只显示一个 emoji（💤 值班 / 👂 在听 / 🕵️ 翻档中 / 🥳 有出处 / 😔 没翻到 / 😰 出错 / 🎉 不错），中文状态标签只保留给屏读器，中、小圆点朝头部渐小；背景、灯、柜台与回执用 CSS/SVG 绘制，不加载远程素材。

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

档案馆首屏通过真实主 API 验收：输入 “Replace recurrence with self-attention to model long-range dependencies” 后，回执展示 Attention 与 BERT 两条真实召回及各自可定位出处，盖章「有出处」，考据币从 20 增至 35；点「继续正式考据」会把想法带入表单，机制字段留空等待补充。桌面 1440×900、1024×768 与手机 390×844 三档均完成“写纸条 → 回执”，390×844 另验证了继续预检与表单带入；控制台无错误，手机无横向溢出。公开静态构建现在改用浏览器内引擎：同一份输入会执行真实的哈希嵌入、词面+向量 RRF 检索与确定性预检，不再回放固定样例。2026-10-28 发布动态版到公开站点；`confirmation bias` 召回 MOON original（2 条证据），`self-attention transformer` 召回 Attention 与 BERT，`今天天气` 返回「查无旧档」且不提供继续按钮；IBML 示例在浏览器内得到 `CONDITIONAL_GO`、9 项通过、0 项失败、3 条证据和 1 条历史比较。桌面 1440×900 与手机 390×844 均无横向溢出、控制台 0 错误。纸条只要非空就能提交，1–4 个字的短查询也会照常查档；空纸条会在上方提示先写一句，不会静默忽略点击，输入框旁只保留“写得越具体，越容易翻到旧档”的软提示。公开大厅的次级入口也收进了馆内：底部「我的馆藏 / 取回旧裁决 / 技术档案」、侧边与研究秘书、今日归档和抽屉菜单都会在当前大厅打开纸页式档案，不再跳回浅色工作台；「正式考据」在馆内打开浏览器预检表单，报告同样以纸页呈现。同日先以 action `cd59dd92-93bb-40d3-be4b-11d1959b630f` 发布馆内导航修复（当时线上引用 `index-BRBSUW2S.js` / `index-DZ_-GYrD.css`）。随后以 action `314fef4f-0343-4e96-92b3-168a34598ee1` 发布仓库链接修复（当时线上引用 `index--PnxTbZK.js` / `index-DZ_-GYrD.css`）；馆内「代码仓库」与抽屉入口统一指向大赛团队仓库的 `submit/qoder` 分支。匿名桌面与手机复测五个入口和 IBML 报告，均无横向溢出、控制台 0 错误，线上预检返回 `CONDITIONAL_GO`（9 通过 / 0 失败 / 3 条证据 / 1 条比较）。2026-10-28 又以 action `5a5635e3-c3a8-4679-aa8f-2cd7673a584c` 发布研究方向拆分与 12 篇论文版本（历史版本）。同日以 action `08427d84-ed5f-4ebe-a076-35d0893c9514` 发布补齐内置论文版本（历史版本）。2026-10-28 再以 action `28D0E78A-90BD-4BB2-8F14-823FB2A27DEB` 发布大量论文版本（历史版本），当时线上入口引用 `index-DVwb9xbV.js` / `index-CQXp-ogJ.css`，构建产物含 `public-archive-2026-10-28.5`；公开馆藏 94 条（20 张重建演示卡、74 篇 arXiv 论文摘要，其中 83 条带可定位证据），种子档案 92 张（91 条证据、9 条历史裁决），本次九个研究方向各新增 6 篇论文。线上匿名 1440×900 复测稀疏自编码器、时序线性基线、图神经网络天气、神经音频编解码、仓库级代码补全与多智能体角色扮演六族中文查询，均返回同一研究方向旧档并带可定位证据；其中 SAE 查询命中 Scaling SAE/Toy Models/Gemma Scope，天气查询命中 GraphCast/DeepONet/PINN，音频查询命中 USM/SoundStream，代码查询命中 SWE-bench/CodeT5/Code Llama，多智能体查询命中 Generative Agents/Voyager/ChatDev。线性基线查询返回时序基础模型旧档，DLinear 未进前三，是当前词面/向量融合的排序边界。IBML 预检仍为 `CONDITIONAL_GO`（9 通过 / 0 失败 / 3 条证据 / 1 条比较）；390×844 稀疏自编码器与线性基线查询结果与桌面一致，均无横向溢出、控制台 0 错误。

2026-10-28 最新 action `B81D82BB-725C-42B7-9507-8B0C8B77FCFC` 发布导览强化版，线上入口引用 `index-DSFAOskM.js` / `index-Bj394_nS.css`：公开大厅移除静态演示馆藏、研究秘书样例与「填入示例」按钮，馆藏、带证据与旧裁决数字改读真实公开档案（94 / 83 / 9），散落的小字说明收拢为羊皮卷「档案馆入棺须知」四步指南（写纸条 / 看回执 / 正式考据 / 翻旧案）。指南不再藏在角落：顶部牌匾下方悬挂一块醒目的「档案馆入棺须知」木牌，点击即在 hall 背景上展开羊皮卷；老余两侧新增按钮组，左侧「查一件想法 / 正式考据」，右侧「取回旧裁决 / 技术档案」，桌面隐藏底部重复操作条，手机保留四键底栏。公开大厅当前只保留正式考据、入棺须知、取回旧裁决与技术档案；我的馆藏与研究秘书页只在本地真实服务模式出现。匿名桌面 1440×900 与手机 390×844 验收：木牌与牌匾、人物均不重叠，两侧按钮可用，指南打开时背景仍是大厅，实时回执、正式考据表单与报告、9 条旧裁决、技术档案均正常，页面无「演示 / 样例」字样、无横向溢出、控制台 0 错误。此前同日的 action `9F2F068B-9B7D-42F1-853D-75E1484EEE75` 为首版大厅清理（历史版本，指南原名「翻档偏方」，藏于底部操作条）。

2026-10-28 最新 action `FDA96E25-853A-4E93-B880-2E596EAD1914` 把值班台的等级进度条改成可购买徽章，线上入口引用 `index-17pruGaH.js` / `index-DaV8dsuV.css`：右侧值班台改为六格徽章架，点任意格或顶栏考据币按钮都会打开羊皮卷「考据徽章」铺；六枚徽章为夜灯初证 15、旧档耳目 30、回执验章 45、冷案猎手 60、卡尺与墨 80、首席考据官 120 考据币。购买会扣币并自动佩戴，已购徽章可随时佩戴或摘下，换章不退币、摘下不扣币；拥有的徽章与佩戴状态保存在浏览器 localStorage，顶栏显示当前佩戴的徽章，手机顶栏用勋章图标提示入口，档案柜也新增「徽章铺」。徽章只作馆内身份，不影响检索、证据与裁决。匿名线上验收：初始 20 枚可买 15 枚的夜灯初证，余额变 5，购后自动佩戴并写入 `nullpath.badges.v1`；刷新后余额与佩戴保持；再查一次稀疏自编码器得 +15，余额回到 20；桌面 1440×900 与手机 390×844 的徽章铺均无横向溢出，6 张卡片在手机单列完整展开，控制台 0 错误。

2026-10-28 最新 action `FDDE8FAB-22D5-46EF-9374-5F7A21782B84` 发布可读性与老余表情版，线上入口引用 `index-CfKRByMn.js` / `index-DgOQ4ohE.css`：馆内 8–11px 小字统一抬升，正文 12.5–13.5px、字段标签与案卷元数据 12px、主标题 13–14px、纸条输入与心情气泡 14px，桌面侧栏日期、回执机制与证据行、九条旧裁决、徽章铺和羊皮卷指南同步放大；360px 手机隐藏重复的「查一件想法」按钮，其余三键完整落在底栏内；页面可见文案中的 `·` 分隔统一改为 `/` 或中文逗号。老余在静态手绘插画上叠加 SVG 眼睑、虹膜与嘴部：每 2.8–6.4 秒随机眨眼约 150ms，在听时眼神放低、翻档时眼珠偏向灯下、有出处时腮红与星光、没翻到与出错时换成平嘴或撇嘴、出错另加脸颊汗滴、购章后单眼眨眼并冒气泡；气泡桌面在脸侧、手机为右上角短标签，系统开启“减少动态效果”时关闭动画。另修复慢检索结果晚到时覆盖新输入状态的问题。匿名线上验收：1440×900 首次加载引用新 JS/CSS，正文无 `·`，实测字体 12 / 13 / 14 / 14 / 12.5px；9 秒内捕获 2 次闭眼；`自注意力替代循环结构…` 得到 `mood-found`（1 条证据），无对应馆藏的问题得到 `mood-blank`，空纸条得到 `mood-error`；390×844 无横向溢出、指南正文 13.5px，360px 底栏 `scrollWidth` 与 `clientWidth` 相等；控制台 0 错误、无失败请求。留档见 `evidence/published-expressions-*.png`。

2026-10-28 action `4a041fe2-8f9b-48e6-83ec-00b43b50dd6c` 回应“眼睛好小好猥琐”，重绘老余的 SVG 眼睛，线上入口引用 `index-eMrBRQWe.js` / `index-DgOQ4ohE.css`：眼白从 42×16 的细缝扩为 52×28.5 的圆杏形，虹膜半径 8.2→12、改用暖褐径向渐变并放大双高光，删除下眼睑细纹；眨眼与单眼笑眼弧线同步加宽。翻档、查无与出错的撇嘴遮罩改为与嘴周取样一致的肤色并加宽，消除原插画笑容残影。匿名 1440×900 与 390×844 验收：首屏、闭眼、翻档、有出处与手机布局正常，360px 无横向溢出，控制台 0 错误、无失败请求。留档见 `evidence/published-eyes-*.png`。该版在线反馈为“还是好诡异”，由下一版改为闭眼值班。

2026-10-28 最新 action `4fd277c2-9208-4656-aa44-45b7340cd5ab` 按用户选定的 emoji 收尾：心情只保留 💤 值班 / 👂 在听 / 🕵️ 翻档中 / 🥳 有出处 / 😔 没翻到 / 😰 出错 / 🎉 不错，并去掉气泡内可见中文，两字状态改为仅供屏读器的隐藏文本（`role="status"` 仍会朗读），大气泡只显示一个 emoji，桌面 34px、手机 30px。线上入口引用 `index-C9xgt6t0.js` / `index-D1WaT99h.css`；匿名 1440×900 六态逐一命中对应 emoji、隐藏标签尺寸均为 1px 以内，390×844 与 360×800 无横向溢出、气泡不压人物，控制台 0 错误、无失败请求；购章后的 🎉 与 wink 在本地清空 localStorage 后复测通过。留档见 `evidence/published-mood-icons-*.png` 与 `evidence/mood-icons-pleased-local.png`。

2026-10-28 action `59ccf8cd-625e-4bca-b4c0-62b5cdfca1af` 回应“别催是什么鬼？还有我要的是那种小圆形气泡 中圆形气泡 大圆形气泡延伸出去，放的是心情”，删掉全部长句心情文案（含“灯下翻档，别催……”），心情气泡改成经典思考气泡三连圆：大气泡 74px（手机 68px）贴着头侧，中圆 17px、小圆 9px 朝头部渐小并轻微漂浮；大气泡内放原生彩色 emoji 与两字状态，随状态切换为 😴 值班 / 😌 在听 / 🤔 翻档中 / 😄 有出处 / 😕 没翻到 / 😰 出错 / 😉 不错，购买徽章后 wink 与星光同步出现。桌面气泡在人物左侧、手机在右上角，`prefers-reduced-motion` 下停止漂浮与弹出动画。线上入口引用 `index-D8UmKMcZ.js` / `index-CQ47IB-t.css`；匿名 1440×900 验收六种心情标签与 emoji 全部正确、回执仍返回 94 / 83 / 9 的真实馆藏数字，390×844 与 360×800 无横向溢出、气泡与人物不重叠，控制台 0 错误、无失败请求。留档见 `evidence/published-thought-*.png`。

2026-10-28 action `c17d4835-5377-4fe8-9069-133924a8a1ce` 回应“还是好诡异”，停止在值班状态叠加睁眼：首页、聚焦纸条与听人写字时都保留原画的闭眼微笑，只有翻档、有出处、没翻到、出错时才用 SVG 睁开一双眼白 46×15.8、虹膜 r=10.3 的暖褐小眼（虹膜上缘压在上眼睑下，下缘被眼型裁掉，不再露出下三白），并配暖象牙眼白、上眼睑阴影与双高光；翻档视线改为向下偏右，不再向上翻。眨眼与单眼笑眼弧线保留，`prefers-reduced-motion` 下关闭动画；嘴部遮罩逻辑不变。匿名 1440×900 与 390×844 验收：首屏、聚焦、有出处与手机布局正常；同一构建在本地 1440/390/360 下逐个截取值班、聚焦、眨眼、翻档、有出处、查无、出错与购章笑眼，未再出现睁眼凝视感。线上入口引用 `index-DKDZavJm.js` / `index-CTiPw-SZ.css`，390px 与本地 360px 无横向溢出，控制台 0 错误、无失败请求。留档见 `evidence/published-face-*.png`。

第二份验收材料 `evidence/library-import-fixture-bert.md`（arXiv:1810.04805 的公开摘要）同样首次导入 1 段、重复导入跳过 1 段；两篇论文共同进入秘书扫描。秘书闭环使用真实主 API 验收：2 个资料分段生成 1 条 `knowledge_line` 提案，人工接受后上下文 revision 为 5；随后的真实预检 `d7c41dfc-1a2c-4aae-b9f2-01634ed9bd40` 在 `context_refs` 中固定该 revision，并召回 Attention 论文。该预检中 BERT 未进入 top-6 融合比较，这是当前召回上限与 RRF 权重的已知边界，未为演示调高上限。回执见 `evidence/secretary-last-run.json`。

消融脚本直接复用真实 seekdb 检索路径，分别运行 vector-only、fulltext-only 和 hybrid，记录每个案例的召回与裁决。结果写入 `evidence/ablation-results.json`；只有 hybrid 的全部案例通过时才返回成功，不用预设其他两路必须失败。可用 `NULLPATH_VALIDATION_DATABASE` 覆盖独立验证数据库名。

验证材料：

- `examples/archive.json`：九十二张历史档案，覆盖 MOON、IBML/ARL、CodeAlign，以及检索增强生成、跨模态对齐、偏好优化、时序基础模型、科学机器学习与语音表示；其中 20 张重建演示卡、72 篇 arXiv 论文，9 张带历史裁决、91 条可定位证据，本次每个研究方向各新增 6 篇。九条研究线各自使用独立 `domain`（如 `model-interpretability`、`information-retrieval`、`multimodal`），不再共用 `research`。
- `examples/sources/`：可定位的演示出处。
- `evidence/library-import-fixture.md`、`evidence/library-import-fixture-bert.md`：资料库与秘书验收使用的真实公开论文摘要，不是用户实验结果。
- `evidence/secretary-last-run.json`：秘书夜间脚本的无摘录回执，包含扫描计数、提案 ID 与 PowerContext artifact 修订。
- `evidence/hall-*.png`：档案馆首屏、真实检索回执、移动端回执、档案柜和静态演示回执的界面留档。
- `evidence/published-dynamic-hall-desktop.png`、`evidence/published-dynamic-hall-mobile.png`：2026-10-28 公开站点桌面与手机端动态检索回执（Attention + BERT）。
- `evidence/published-dynamic-report-desktop.png`：公开站点浏览器内预检报告（IBML 示例，CONDITIONAL_GO）。
- `evidence/published-hall-sheets-desktop.png`、`evidence/published-hall-sheets-mobile.png`：2026-10-28 馆内导航修复后的公开站点历史裁决纸页（桌面与手机）。
- `evidence/published-hall-sheets-report.png`：同一次发布中，公开站点浏览器内 IBML 预检报告（9 通过 / 0 失败 / 3 条证据 / 1 条比较）。
- `evidence/published-domain-search-desktop.png`、`evidence/published-domain-search-mobile.png`：2026-10-28 研究方向拆分发布后的公开站点回执；桌面 RAG 查询命中 Lost in the Middle/RAG 论文，手机跨模态查询命中 CLIP/Modality gap。
- `evidence/published-domain-report-desktop.png`：同一次发布的公开站点 IBML 预检报告（CONDITIONAL_GO，9 通过 / 0 失败 / 3 条证据 / 1 条比较）。
- `evidence/published-new-papers-desktop.png`、`evidence/published-new-papers-mobile.png`：2026-10-28 内置论文补齐发布后的公开站点回执；“多智能体协作为什么会失败？”在桌面与手机均命中 MAST 与 Generative Agents，各带 1 条可定位证据。
- `evidence/published-new-papers-precheck.png`：同一次发布中，公开站点 IBML 预检报告（CONDITIONAL_GO，9 通过 / 0 失败 / 3 条证据 / 1 条比较）。
- `evidence/published-many-papers-desktop.png`、`evidence/published-many-papers-mobile.png`：2026-10-28 大量论文版本发布后的公开站点回执；稀疏自编码器查询在桌面与手机均命中 Scaling SAE、Toy Models 与 Gemma Scope。
- `evidence/published-many-papers-precheck.png`：同一次发布的公开站点 IBML 预检报告（CONDITIONAL_GO，9 通过 / 0 失败 / 3 条证据 / 1 条比较）。
- `evidence/published-many-papers-archive.png`：同一次发布的技术档案纸页，标注 94 条公开馆藏（20 张重建演示卡、74 篇论文摘要，其中 83 条带可定位证据）。
- `evidence/published-notice-desktop.png`、`evidence/published-notice-mobile.png`：2026-10-28 导览强化版公开站点首屏；牌匾下悬挂「档案馆入棺须知」木牌，老余两侧分列「查一件想法 / 正式考据」与「取回旧裁决 / 技术档案」，桌面隐藏底部操作条、手机保留四键底栏，左右面板显示真实 94 / 83 / 9。
- `evidence/published-notice-guide-desktop.png`、`evidence/published-notice-guide-mobile.png`：同一次发布的羊皮卷指南「档案馆入棺须知」；四步便签、上下卷轴与「老余」印章，打开时背景仍是大厅。
- `evidence/published-notice-precheck.png`：同一次发布中从大厅完成的浏览器内预检报告（CONDITIONAL_GO，8 通过 / 0 失败 / 3 条证据 / 6 条比较）。
- `evidence/published-badges-hall-desktop.png`、`evidence/published-badges-hall-mobile.png`：2026-10-28 徽章版公开首屏；值班台六格徽章架已点亮并佩戴「夜灯初证」，顶栏显示佩戴中的徽章，手机顶栏保留勋章入口。
- `evidence/published-badges-shop-desktop.png`、`evidence/published-badges-shop-mobile.png`：同一次发布的羊皮卷徽章铺；初始 20 枚考据币下只有 15 枚的「夜灯初证」可购，其余显示还差多少，手机单列展示六枚徽章。
- `evidence/published-badges-owned-desktop.png`：购下并自动佩戴「夜灯初证」后的铺内状态，余额 5 枚、回执提示与「摘下」按钮。
- `evidence/published-expressions-hall-desktop.png`、`evidence/published-expressions-blink-desktop.png`、`evidence/published-expressions-error-desktop.png`、`evidence/published-expressions-found-desktop.png`、`evidence/published-expressions-blank-desktop.png`：2026-10-28 可读性与表情版的公开首屏、闭眼瞬间、空纸条出错、查到出处与查无旧档五种状态。
- `evidence/published-expressions-guide-mobile.png`：同一次发布的 390px 羊皮卷指南，正文放大后仍完整落在卷轴内。
- `evidence/published-eyes-idle-desktop.png`、`evidence/published-eyes-blink-desktop.png`、`evidence/published-eyes-think-desktop.png`：2026-10-28 放大眼睛版的公开首屏、闭眼瞬间与翻档表情；眼白与虹膜明显放大，闭眼和撇嘴不再带旧笑容残影。
- `evidence/published-eyes-idle-mobile.png`：同一次发布的 390px 首屏，大眼与圆框眼镜的比例保持正常。
- `evidence/published-face-idle-desktop.png`、`evidence/published-face-idle-face.png`、`evidence/published-face-listen-face.png`、`evidence/published-face-idle-mobile.png`：2026-10-28 闭眼值班版的公开首屏、面部特写与 390px 首屏；值班和聚焦听写时保留原画闭眼微笑，不再叠加睁眼。
- `evidence/published-face-found-face.png`、`evidence/published-face-found-mobile.png`：同一次发布的“有出处”睁眼表情桌面与手机留档，虹膜填满眼型、不再露出下三白。
- `evidence/face-blink.png`、`evidence/face-open-think.png`、`evidence/face-wink.png`、`evidence/face-hall-desktop.png`、`evidence/face-hall-mobile.png`：同一构建的本地状态矩阵（眨眼、翻档、购章笑眼与桌面/手机大厅），用于逐状态比对。
- `evidence/published-thought-idle-desktop.png`、`published-thought-listen-desktop.png`、`published-thought-found-desktop.png`、`published-thought-blank-desktop.png`、`published-thought-error-desktop.png`：2026-10-28 思考气泡带两字标签版（历史留档）的公开首屏与在听、有出处、没翻到、出错场景；大气泡内为 emoji 与两字状态，中、小圆点朝头部渐小。
- `evidence/published-thought-idle-mobile.png`、`published-thought-found-mobile.png`：同一次发布的 390×844 手机首屏与“有出处”状态，气泡在人物右上角、标签完整落在圆内。
- `evidence/thought-pleased-local.png`：标签版本地购章后的 wink 与“不错 😉”气泡留档。
- `evidence/published-mood-icons-idle-desktop.png`、`published-mood-icons-listen-desktop.png`、`published-mood-icons-think-desktop.png`、`published-mood-icons-found-desktop.png`、`published-mood-icons-blank-desktop.png`、`published-mood-icons-error-desktop.png`：2026-10-28 emoji-only 版的公开首屏与六种心情场景，气泡内只显示 💤 / 👂 / 🕵️ / 🥳 / 😔 / 😰，可见中文已移除。
- `evidence/published-mood-icons-idle-mobile.png`、`published-mood-icons-found-mobile.png`：同一次发布的 390×844 手机首屏与“有出处（🥳）”，气泡位置与尺寸不变。
- `evidence/mood-icons-pleased-local.png`：emoji-only 版本地购章后的 wink 与 🎉 气泡。
- `evidence/published-hall-clean-desktop.png`、`evidence/published-hall-clean-mobile.png`、`evidence/published-guide-desktop.png`、`evidence/published-guide-mobile.png`、`evidence/published-guide-precheck.png`：同日上一版大厅清理与旧名指南的历史留档。
- `evidence/published-hall-desktop.png`、`evidence/published-hall-mobile.png`：早先固定样例版公开回执留档。
- `evaluation/golden_cases.json`：预期裁决、必需证据和禁止的未来证据。
- `evidence/`：实际运行结果、界面截图与 Qoder 开发记录。

这些材料用于功能验证，不是原始实验日志，也不声称对应外部论文的真实结论。

## 静态网站与本地应用的边界

Qoder Sites 发布的是 `web/dist` 静态版本，但公开版不是截图或固定回执。`web/.env.production` 启用公开演示模式（`VITE_DEMO_MODE=true`），前端通过 `web/src/publicEngine.ts` 在浏览器内执行：

- 与服务端一致的 BLAKE2b 64 维哈希嵌入（`web/src/blake2b.ts`），以及中文二元词、停用词和复数归一后的词面评分；
- 词面与向量两路 RRF 融合（权重 0.6/0.4、k=60、每路 8、融合 6）；预检按任务或同一研究方向 domain 收敛，大厅与只读历史搜索才执行显式全馆检索；相对相关度门槛先按全部候选的最高词面分计算，再做证据过滤，只保留不低于该最高分 25% 的记录；
- 同一套 `research-ci-rules-v1` 确定性检查、机制 Jaccard 比较、候选时间边界和快照哈希。

公开馆藏由 `web/scripts/build-public-archive.py` 从 `examples/archive.json`（含 72 篇 arXiv 论文）与资料库验收用的两篇论文摘要生成，共 94 条记录（20 张重建演示卡、74 篇论文摘要、9 条历史裁决），其中 83 条带可定位证据；构建脚本复用服务端的中文检索别名表，论文记录同时注入题名专属别名与任务别名，嵌入向量在构建时生成，随静态资源一起发布。服务端中文查询也会先做别名扩展并推断研究方向，再进入对应 domain 的检索，避免跨方向噪声。报告和回执中的版本号会标明 `browser-vector-fts-rrf-v1` 等公开版实现。

公开版仍然不连接在线后端：结果不写入 seekdb、不读取 PowerContext、不能执行人工终审，也不导入访问者文件。资料导入、秘书扫描与审阅、持久化提交、终审、实验回流和可写回放需要本地服务，不会伪造在线摄取。

公开站点：https://nullpath-research-ci-b4ket19m2lz.qoder.zone

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
