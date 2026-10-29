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
13. 根据“补充数据库”的反馈，在表结构与规则版本不变的前提下把演示档案从 8 张扩到 20 张：新增检索增强生成、跨模态对齐、偏好优化、时序基础模型、科学机器学习与语音表示六条研究线，配套 `examples/sources/` 复核卡与 12 条可定位证据。新卡日期均晚于黄金与消融用例的 cutoff，既有裁决保持不变；`build-public-archive.py` 增加按任务注入的中文检索别名，公开馆藏从 10 条增至 22 条（9 条历史裁决、11 条带证据）。
14. 根据“不要按 research 分类、补充论文”的反馈，把 20 张卡从共用 `domain: "research"` 拆成九条研究线各自的 domain（`model-interpretability`、`multi-agent-systems`、`code-generation`、`information-retrieval`、`multimodal`、`preference-optimization`、`time-series`、`scientific-ml`、`speech`），并新增 12 篇 arXiv 基线论文（RAG、Lost in the Middle、CLIP、Mind the Gap、DPO、InstructGPT、TimesFM、Chronos、FNO、DeepONet、wav2vec 2.0、HuBERT），每篇带摘要、人工归纳机制、原始链接与可定位证据，不设历史裁决。预检按 `task` 或同一 `domain` 收敛；档案馆大厅与只读历史检索显式使用全馆范围，保持“一句话查全部旧档”。新增服务端共享别名表 `aliases.py`，中文查询先做别名扩展并推断研究方向；前端新增 `domains.ts`，完整预检与资料导入都从任务派生 domain。该轮完成后种子档案为 32 张（20 张重建卡 + 12 篇论文、31 条证据、9 条裁决），公开馆藏为 34 条（另含 2 篇既有资料库论文摘要、23 条带证据）；下一步补齐至 38 张。
15. 根据“增加内置论文、提高开箱即用性”的反馈，把覆盖面补齐为每个研究方向至少两篇真实论文：新增 Codex、SWE-bench（代码生成），ROME、In-context Learning and Induction Heads（模型可解释性），Generative Agents、Why Do Multi-Agent LLM Systems Fail?（多智能体）。六篇均来自 arXiv，保留完整摘要、人工归纳机制、原始链接和可定位证据；其中 Induction Heads 与 MAST 作为竞争解释/失败证据，SWE-bench 作为真实仓库级难度证据。同步扩展 `language-model-analysis`、`collaboration-analysis`、`code-alignment` 的中英文别名，公开馆藏增至 40 条（20 张重建卡 + 20 篇论文摘要、29 条带证据、9 条裁决）。新增论文没有改写任何历史裁决，golden 与 ablation 仍全部通过。
16. 根据“继续大量补论文”的反馈，再补 54 篇真实 arXiv 论文，本次九个研究方向各新增 6 篇：检索增强生成（DPR、ColBERT、BEIR、HyDE、Self-RAG、CRAG）、跨模态（ALIGN、Flamingo、BLIP-2、SigLIP、LLaVA、ImageBind）、偏好优化（Christiano RLHF、HH-RLHF、Constitutional AI、KTO、ORPO、SimPO）、时序（Informer、DLinear、TimesNet、PatchTST、Lag-Llama、Moirai）、科学机器学习（PINN、Neural ODE、MeshGraphNets、Neural Operator、PDEBench、GraphCast）、语音（SoundStream、w2v-BERT、EnCodec、Whisper、USM、SpeechTokenizer）、可解释性（Toy Models of Superposition、IOI、Grokking、SAE features、Scaling SAEs、Gemma Scope）、多智能体（CAMEL、Voyager、ChatDev、MetaGPT、AgentBench、AutoGen）、代码生成（CodeT5、AlphaCode、StarCoder、Code Llama、SWE-agent、Agentless）。每篇保留完整摘要、人工归纳机制、原始链接、可定位证据与发表日期，并明确标注外部来源没有候选失败条件。种子档案增至 92 张（72 篇论文、91 条证据、9 条裁决），公开馆藏增至 94 条（74 篇论文摘要、83 条带证据、版本 `public-archive-2026-10-28.5`）。同步扩展共享别名表并改为最长题名匹配，避免 ColBERT 继承 BERT 别名；公开构建对论文记录合并题名专属别名与任务别名。新增论文未改写任何历史裁决、cutoff 或时间边界。
17. 根据“公开演示要能解释真实历史、最小实验不要空话”的反馈，公开馆藏新增 215 条外部记录：ReScience C 复现、FReD 复现失败与 Retraction Watch 撤稿记录，每条保留来源、原始链接、许可状态、抓取日期与可定位证据；记录结构加入 `record_type/source/outcome/outcome_quote`，检索与预检仍在浏览器内执行。最小判别实验改为引用提案自己的差异声明、竞争解释、停止条件与首轮预算；只有相似度不低于 0.12 且有可定位证据的历史记录才作为参照，缺失项明确写“待补”。同时移除“没找到也不等于创新成立”“只换身份，不换结论”等防御性话术，并让移动端弹层底部为平台徽章留出安全距离。2026-10-29 以 action `09d1de74-7147-4010-8230-a4d3ec1d4f25` 发布到新公开地址 `https://nullpath-research-ci-b4ket19m2lz.qoder.zone`（原地址属于另一 Qoder 账号，无法继续更新）；匿名桌面 1280×900 与手机 390×844 均完成检索→预检→六行最小实验，控制台 0 错误、无横向溢出。

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
- 扩充档案后出现新的比较噪声：相对词面门槛在证据过滤之后计算，无证据的高分候选被移除后门槛回落，IBML 预检混入 Attention 与 BERT 的 0.03/0.04 弱比较。已把最高词面分与 25% 门槛改为在证据过滤前计算，IBML 预检恢复为 1 条历史比较；六个中英文查询仍各自只命中对应旧档。
- 初次加入论文时所有记录仍共用 `research` domain，导致每篇论文对任意提案全局可见；中文查询又因数据库没有中文别名、词面分为空而按向量噪声排序，例如“偏好优化中标注分歧”首先返回 DeepONet。修复分三层：重建九条独立 domain、检索按 task/domain 收敛（大厅与只读历史检索显式 `match_all`）、服务端对中文查询做确定性别名扩展并推断研究方向。六个查询族（RAG、偏好、时序、科学机器学习、MOON、CodeAlign）复测后均只返回对应方向记录。
- `import_archive` 原先发现同名记录就跳过，无法给既有 20 张卡补写新 domain；改为同名时比较并更新 `task`/`domain`，新增论文正常插入。验证库与主库均完成 32 张卡、31 条证据、9 条裁决的迁移。
- 用户反馈公开大厅堆了演示馆藏、研究秘书样例和小字说明；公开大厅移除静态 `LibrarySheet` / `SecretarySheet` 与「填入示例」，只保留实时检索、正式考据、旧裁决与技术档案，馆藏数字改读 `publicArchiveStats()`。散落说明收拢为羊皮卷「档案馆入棺须知」（原名「翻档偏方」）：写纸条、看回执、正式考据、翻旧案四步，上下卷轴与「老余」印章，打开时背景仍是大厅。
- 用户反馈指南名字不够档案馆气质、入口太隐蔽；指南更名为「档案馆入棺须知」，在顶部牌匾下方悬挂一块醒目木牌（挂绳与钉子细节），点击即开卷；老余两侧新增按钮组（左：查一件想法 / 正式考据，右：取回旧裁决 / 技术档案），桌面隐藏重复的底部操作条，手机保留四键底栏，窄屏与矮屏分别调整悬挂位置。
- 用户要求把馆员等级进度条改成可购买徽章的交互；移除按余额计算的等级与进度条，值班台改为六格徽章架，顶栏考据币按钮和档案柜「徽章铺」都能打开羊皮卷徽章铺。六枚徽章为夜灯初证 15、旧档耳目 30、回执验章 45、冷案猎手 60、卡尺与墨 80、首席考据官 120：购买扣币并自动佩戴，已购可佩戴/摘下，换章不退币、摘下不扣币；拥有与佩戴状态写入 `nullpath.badges.v1`，余额继续用 `nullpath.coins.v1`。徽章只作身份，不影响检索、证据与裁决；手机顶栏加勋章图标提示入口。
- 用户反馈馆内小字看不清、可见文案里还有 `·` 分隔，并希望老余能眨眼、变表情、冒心情气泡。馆内 8–11px 小字统一抬升（正文 12.5–13.5、标签与元数据 12、输入与气泡 14），`·` 全部改为 `/` 或中文逗号；360px 底栏隐藏重复的“查一件想法”，避免放大后横向溢出。老余原图不动，用 `viewBox="0 0 460 690"` 的 SVG 叠加眼白、虹膜、眼睑与嘴部：每 2.8–6.4 秒随机眨眼 150ms，在听、翻档、有出处、没翻到、出错、购章分别切换眼神、嘴形、腮红、星光与汗滴，脸侧或右上角显示对应气泡，`prefers-reduced-motion` 时不眨眼。验收时还发现慢检索晚到的结果会覆盖用户已输入的新状态，已用请求序号守卫丢弃过期结果。
- 用户反馈“这个眼睛好小好猥琐”；原叠加眼白只有 42×16，虹膜半径 8.2，加上下眼睑细纹，形态偏细长。现改为 52×28.5 圆杏眼白、虹膜半径 12、暖褐径向渐变与更大的双高光，去掉下眼睑细纹；眨眼与笑眼弧线同步加宽。翻档/查无/出错时原图笑容只用 6.5 宽肤色笔触盖不住，改为 11.5 宽、按嘴周像素取样调色的 `#e1ae82 → #daa579` 遮罩，消除双嘴残影。
- 用户仍反馈“还是好诡异”；排查发现睁眼时虹膜偏小且位置偏高，虹膜下方露出眼白（下三白），加上原画笑容形成“笑着凝视”的违和感。改为值班、聚焦纸条与听写时保留原画闭眼微笑，只在翻档、有出处、没翻到、出错时睁眼：眼白 46×15.8、虹膜 r=10.3，上缘压在上眼睑下、下缘被眼型裁掉，眼白改暖象牙色并加上眼睑阴影与第二点高光；翻档视线由向上翻改为向下偏右，眨眼与购章单眼笑眼保留。
- 用户反馈“别催是什么鬼？还有我要的是那种小圆形气泡 中圆形气泡 大圆形气泡延伸出去，放的是心情”；删掉 `ArchiveHall` 中全部长句心情文案与 14px 矩形气泡，改为三连圆形思考气泡：大气泡承载心情、中圆与小圆朝头部渐小，桌面在人物左侧、手机改到右上角并镜像圆点方向。最初大气泡里用 SVG 手绘小脸，用户追问“大气泡里不能放emoji吗”，遂换成原生彩色 emoji + 两字状态（😴 值班 / 😌 在听 / 🤔 翻档中 / 😄 有出处 / 😕 没翻到 / 😰 出错 / 😉 不错），emoji 加轻微投影融入羊皮纸；手机端同步放大到 68px 并保留标签，`prefers-reduced-motion` 下关闭漂浮与弹出动画。
- 用户要求列出候选、由自己挑选，最终选定 💤 值班 / 👂 在听 / 🕵️ 翻档中 / 🥳 有出处 / 😔 没翻到 / 😰 出错 / 🎉 不错，并问“能否不要中文”；于是把两字状态改为仅供屏读器的隐藏文本（`role="status"` 仍会朗读），大气泡视觉上只显示一个 emoji，桌面 34px、手机 30px。本地七态与 1440/390/360 复测后发布 action `4fd277c2-9208-4656-aa44-45b7340cd5ab`，匿名线上六态 emoji 全部命中、隐藏标签均 ≤1px、无横向溢出、控制台 0 错误、无失败请求；购章 🎉 与 wink 在本地清空 localStorage 后复测通过。

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
| 馆内仓库链接修复 | 2026-10-28 发布 action `314fef4f-0343-4e96-92b3-168a34598ee1`；当时线上引用 `index--PnxTbZK.js` / `index-DZ_-GYrD.css`，抽屉、技术档案和构建产物均只引用 `juanzhi-gcb/powercontext/tree/submit/qoder/qoder`；IBML 示例仍返回 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较，桌面无横向溢出、控制台 0 错误 |
| 演示数据库扩充 | 20 张重建卡、19 条可定位证据、9 条历史裁决；新卡已导入主库与验证库；`pytest` 20 passed、Ruff 通过、golden 5/5、ablation 15/15 |
| 扩充后公开检索 | RAG 重排、偏好算法替换、时序规模、神经算子、MOON、CodeAlign 六个中英文查询各命中 1 条对应旧档；IBML 预检 9 通过 / 0 失败 / 3 条证据 / 1 条比较，`CONDITIONAL_GO` |
| 研究方向拆分与论文导入 | 种子档案 32 张（20 张重建卡 + 12 篇 arXiv 论文）、31 条证据、9 条裁决，九个独立 domain；主库与验证库均完成迁移，既有 20 张卡的 domain 由 `research` 更新为各自研究线，12 篇论文插入成功 |
| 拆分后回归 | `pytest` 20 passed、Ruff check/format 通过；golden 5/5、ablation 15/15（vector/fulltext/hybrid 各 5/5）对更新后的 API 全部通过，既有裁决未因新论文或 domain 调整而变化 |
| 中文查询分域检索 | `POST /api/history-search` 的 RAG 重排、偏好标注分歧、时序规模、神经算子、MOON 先验角色、CodeAlign 六族中文查询均只返回对应研究方向记录；修复前偏好查询会先返回 DeepONet |
| 公开馆藏重建 | `build-public-archive.py` 生成 34 条记录、23 条带证据、9 条历史裁决、版本 `public-archive-2026-10-28.3`；浏览器内检索的 RAG/偏好/时序/算子/MOON/CodeAlign 查询各自命中对应馆藏，IBML 大厅预检仍为 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较 |
| 研究方向拆分发布 | 2026-10-28 发布 action `5a5635e3-c3a8-4679-aa8f-2cd7673a584c` 到 `https://nullpath-research-ci-5dqanvro27t.qoder.zone`；线上入口引用 `index-DXVIKjrY.js` / `index-UX8M9-dx.css`，构建产物含 34 条公开馆藏与九个 domain。匿名 1440×900 复测：RAG 查询命中 Lost in the Middle/RAG 论文、纯时序查询命中 Chronos/TimesFM 旧档、语音查询命中 wav2vec 2.0、神经算子查询命中 DeepONet；同一构建在本地预览另测偏好查询命中 DPO/InstructGPT。IBML 预检 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较。390×844 跨模态查询命中 CLIP/Mind the Gap，无横向溢出、控制台 0 错误 |
| 内置论文补齐 | 新增 6 篇真实 arXiv 论文：Codex `2107.03374`、SWE-bench `2310.06770`、ROME `2202.05262`、Induction Heads `2209.11895`、Generative Agents `2304.03442`、MAST `2503.13657`；种子档案 38 张、37 条证据、9 条裁决，公开馆藏 40 条、29 条带证据、20 篇论文摘要；九个方向均至少两篇论文 |
| 新论文导入与检索 | 主库与验证库各插入 6 篇论文；中文查询“多智能体协作为什么会失败”“归纳头能否解释上下文学习”“仓库级代码修复和单元测试基准”分别命中 MAST/IBML、Induction Heads/ROME、SWE-bench/Codex，且只返回对应方向；公开浏览器同一构建的桌面查询命中了六篇新论文，多智能体查询在 390px 无横向溢出 |
| 补论文后回归 | `pytest` 20 passed、Ruff check/format 通过；golden 5/5、ablation 15/15（vector/fulltext/hybrid 各 5/5）；新增论文未改变既有历史裁决或时间边界 |
| 内置论文补齐发布 | 2026-10-28 发布 action `08427d84-ed5f-4ebe-a076-35d0893c9514` 到 `https://nullpath-research-ci-5dqanvro27t.qoder.zone`；线上入口引用 `index-CKjZDuN0.js` / `index-DwXWwSZy.css`，构建产物含 `public-archive-2026-10-28.4`、40 条公开馆藏（20 张重建演示卡 + 20 篇 arXiv 论文摘要，29 条带可定位证据）。线上匿名 1440×900 复测多智能体、归纳头、仓库级代码三族中文查询分别命中 MAST/Generative Agents、Induction Heads/ROME、SWE-bench/Codex；IBML 预检 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较；390×844 多智能体查询无横向溢出、控制台 0 错误 |
| 五十四篇论文导入 | 54 个 arXiv ID 全部经 arXiv API 核对标题、日期与摘要；主库 103 条活跃 attempts、94 条证据、9 条裁决，验证库 92 条 attempts、91 条证据、9 条裁决；修复 ColBERT 继承 BERT 别名的问题，别名匹配改为最长题名优先 |
| 大量论文回归 | `pytest` 20 passed、Ruff check/format 通过；golden 5/5（MOON NO_GO、IBML broad NO_GO、IBML identifiability CONDITIONAL_GO、CodeAlign early CONDITIONAL_GO、CodeAlign late NO_GO），ablation 15/15（vector/fulltext/hybrid 各 5/5）；新增论文未改变既有裁决 |
| 大量论文公开检索 | 本地公开预览的 SAE、时序线性基线、图神经网络天气、神经音频编解码、代码补全、多智能体六族查询均返回对应研究方向旧档；IBML 预检 `CONDITIONAL_GO`、9 通过 / 0 失败 / 3 条证据 / 1 条比较；390×844 无横向溢出、控制台 0 错误 |
| 大量论文版本发布 | 2026-10-28 发布 action `28D0E78A-90BD-4BB2-8F14-823FB2A27DEB` 到 `https://nullpath-research-ci-5dqanvro27t.qoder.zone`；线上入口引用 `index-DVwb9xbV.js` / `index-CQXp-ogJ.css`，构建产物含 `public-archive-2026-10-28.5`、94 条公开馆藏（20 张重建演示卡 + 74 篇论文摘要，83 条带可定位证据），技术档案纸页同步标注。线上匿名 1440×900 六族中文查询均返回对应研究方向旧档；SAE 查询命中 Scaling SAE/Toy Models/Gemma Scope，天气命中 GraphCast/DeepONet/PINN，音频命中 USM/SoundStream，代码命中 SWE-bench/CodeT5/Code Llama，多智能体命中 Generative Agents/Voyager/ChatDev；390×844 SAE 与线性基线查询结果同桌面，均无横向溢出、控制台 0 错误。线性基线查询未把 DLinear 排进前三，记录为当前词面/向量融合的排序边界 |
| 大厅清理与羊皮卷指南（历史） | 2026-10-28 发布 action `9F2F068B-9B7D-42F1-853D-75E1484EEE75`；线上入口引用 `index-D7RjmsdJ.js` / `index-C-DBVUbY.css`。匿名 1440×900 与 390×844：首屏无「演示 / 样例」字样，馆藏数字 94 / 83 / 9，四步指南与上下卷轴正常，背景大厅可见；实时回执、正式考据（`CONDITIONAL_GO`，8 通过 / 0 失败 / 3 条证据 / 6 条比较）、9 条旧裁决与技术档案均可打开；无横向溢出、控制台 0 错误 |
| 入棺须知导览强化 | 2026-10-28 发布 action `B81D82BB-725C-42B7-9507-8B0C8B77FCFC`；线上入口引用 `index-DSFAOskM.js` / `index-Bj394_nS.css`。匿名 1440×900：牌匾下悬挂木牌 256×62（x592, y243），与牌匾（底 226）和人物（顶 312）均不重叠；两侧按钮组 150×84（x320 / x970, y636），左侧「查一件想法 / 正式考据」、右侧「取回旧裁决 / 技术档案」均可打开；桌面底部操作条隐藏。390×844：木牌 201×47（x95, y194）不压牌匾与人物，两侧按钮隐藏、四键底栏可见。指南标题为「档案馆入棺须知」，四步便签、2 个卷轴，背景大厅可见；实时回执命中 Scaling SAE / Toy Models / Gemma Scope，继续预检得到 `CONDITIONAL_GO`（8 通过 / 0 失败 / 3 条证据 / 6 条比较），9 条旧裁决与技术档案正常；两档均无横向溢出、控制台 0 错误 |
| 考据徽章铺 | 2026-10-28 发布 action `FDA96E25-853A-4E93-B880-2E596EAD1914`；线上入口引用 `index-17pruGaH.js` / `index-DaV8dsuV.css`。等级进度条已移除（页面上 `.hall-rank` 数量为 0），值班台六格徽章架、顶栏考据币按钮与档案柜「徽章铺」都能打开羊皮卷铺。匿名 1440×900 初始 20 枚：15 枚的「夜灯初证」可购，120 枚的「首席考据官」显示还差 100；购后余额 5、自动佩戴、写为 `{"owned":["night-lamp"],"equipped":"night-lamp"}`，铺内提示余 5；刷新后余额与佩戴保持；再查稀疏自编码器 +15 回到 20，回执正常命中 Scaling SAE / Toy Models / Gemma Scope。390×844：顶栏勋章入口可见、六张卡片单列完整展开、铺内和页面均无横向溢出；控制台 0 错误。Escape 关闭、焦点落在关闭按钮、背景滚动锁定，以及损坏徽章存档回退空收藏，另在本地预览复测。 |
| 可读性与老余表情 | 2026-10-28 发布 action `FDDE8FAB-22D5-46EF-9374-5F7A21782B84`；线上入口引用 `index-CfKRByMn.js` / `index-DgOQ4ohE.css`。匿名 1440×900 实测侧栏日期 12px、标题 13px、心情气泡与输入 14px、底栏按钮 12.5px，正文 `·` 计数为 0；9 秒内捕获 2 次闭眼，截图见 `published-expressions-blink-desktop.png`。`自注意力替代循环结构…` 得到 `mood-found` 与 1 条证据，`火山口熔岩里的橙子味橡皮鸭` 得到 `mood-blank`，空纸条得到 `mood-error`；390×844 无横向溢出、指南正文 13.5px，360px 底栏 `scrollWidth == clientWidth`；控制台 0 错误、无失败请求。 |
| 老余眼神重绘 | 2026-10-28 发布 action `4a041fe2-8f9b-48e6-83ec-00b43b50dd6c`；线上入口引用 `index-eMrBRQWe.js` / `index-DgOQ4ohE.css`。眼白由 42×16 细缝改为 52×28.5 圆杏，虹膜 r=12 暖褐渐变、双高光，删除下眼睑细纹；翻档/查无/出错改用嘴周同色遮罩，消除旧笑容残影。匿名 1440×900 与 390×844 的首屏、闭眼、翻档、有出处均正常，360px 无横向溢出，控制台 0 错误、无失败请求；截图见 `published-eyes-idle-desktop.png`、`published-eyes-blink-desktop.png`、`published-eyes-think-desktop.png`、`published-eyes-idle-mobile.png`。 |
| 闭眼值班与开眼收敛 | 2026-10-28 发布 action `c17d4835-5377-4fe8-9069-133924a8a1ce`；线上入口引用 `index-DKDZavJm.js` / `index-CTiPw-SZ.css`。值班 `.mood-idle` 与聚焦 `.mood-listen` 的 `.hero-eye` 数量均为 0（保留原画闭眼微笑），仅有出处等结果状态为 2 只睁眼；翻档与查无/出错为 2 只，购章为 1 只笑眼 + 1 只睁眼。眼白改为 46×15.8，虹膜 r=10.3 压在上眼睑下，去除下三白，翻档视线改为向下偏右。本地 1440/390/360 全状态截图见 `face-*.png`（含眨眼 `face-blink.png`、翻档 `face-open-think.png`、笑眼 `face-wink.png`）；匿名线上 1440×900 与 390×844 命中新资源，首屏/聚焦/有出处/手机布局正常，无横向溢出，控制台 0 错误、无失败请求；截图见 `published-face-*.png`。 |
| 思考气泡与 emoji 心情 | 2026-10-28 发布 action `59ccf8cd-625e-4bca-b4c0-62b5cdfca1af`；线上入口引用 `index-D8UmKMcZ.js` / `index-CQ47IB-t.css`。删除全部长句心情文案，矩形气泡改为三连圆：大气泡 74px（手机 68px）+ 中圆 17px + 小圆 9px 朝头部渐小，大气泡内为 emoji + 两字状态。匿名 1440×900 六态（😴 值班 / 😌 在听 / 🤔 翻档中 / 😄 有出处 / 😕 没翻到 / 😰 出错）标签、emoji 与两个圆点均正确，moodBox 112×108、大气泡 74×74；390×844 与 360×800 无横向溢出、气泡不压人物，控制台 0 错误、无失败请求；购章 wink 的 😉“不错”在本地清空 localStorage 后购章复测通过。截图见 `published-thought-*.png`、`thought-pleased-local.png`。 |
| emoji-only 心情气泡 | 2026-10-28 发布 action `4fd277c2-9208-4656-aa44-45b7340cd5ab`；线上入口引用 `index-C9xgt6t0.js` / `index-D1WaT99h.css`。按用户选定改为 💤 值班 / 👂 在听 / 🕵️ 翻档中 / 🥳 有出处 / 😔 没翻到 / 😰 出错 / 🎉 不错，去掉气泡内可见中文，两字状态只留给屏读器（隐藏文本 ≤1px），大气泡只显示一个 emoji（桌面 34px、手机 30px）。匿名 1440×900 六态 emoji 与 `labelHidden` 全部正确、390×844 与 360×800 无横向溢出，控制台 0 错误、无失败请求；购章 🎉 与 wink 在本地清空 localStorage 后复测通过。截图见 `published-mood-icons-*.png`、`mood-icons-pleased-local.png`。 |

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
- `published-domain-search-desktop.png`：2026-10-28 研究方向拆分发布后，公开站点 1440×900 RAG 查询回执，命中 Lost in the Middle、RAG 论文与 RAG reranking 旧档。
- `published-domain-report-desktop.png`：同一次发布的 1440×900 IBML 预检报告，仍为 `CONDITIONAL_GO`、9 通过/0 失败、3 条证据、1 条历史比较。
- `published-domain-search-mobile.png`：同一次发布的 390×844 跨模态查询回执，命中 CLIP 与 Modality gap 旧档。
- `published-new-papers-desktop.png`：2026-10-28 内置论文补齐发布后，公开站点 1440×900 多智能体查询回执，命中 MAST 与 Generative Agents。
- `published-new-papers-mobile.png`：同一次发布的 390×844 多智能体查询回执，结果与桌面一致且无横向溢出。
- `published-new-papers-precheck.png`：同一次发布的 1440×900 IBML 预检报告，仍为 `CONDITIONAL_GO`、9 通过 / 0 失败、3 条证据、1 条历史比较。
- `published-many-papers-desktop.png`：2026-10-28 大量论文版本发布后，公开站点 1440×900 稀疏自编码器查询回执，命中 Scaling SAE、Toy Models 与 Gemma Scope，3 条可定位证据。
- `published-many-papers-mobile.png`：同一次发布的 390×844 稀疏自编码器查询回执，结果与桌面一致且无横向溢出。
- `published-many-papers-precheck.png`：同一次发布的 1440×900 IBML 预检报告，仍为 `CONDITIONAL_GO`、9 通过 / 0 失败、3 条证据、1 条历史比较。
- `published-many-papers-archive.png`：同一次发布的技术档案纸页，标注 94 条公开馆藏、74 篇论文摘要与 83 条可定位证据。
- `published-notice-desktop.png`、`published-notice-mobile.png`：2026-10-28 导览强化版公开首屏；牌匾下悬挂「档案馆入棺须知」木牌，老余两侧分列操作按钮；桌面隐藏底部操作条，手机保留四键底栏；左右面板显示真实 94 / 83 / 9。
- `published-notice-guide-desktop.png`、`published-notice-guide-mobile.png`：同一次发布的羊皮卷指南「档案馆入棺须知」，四步便签、上下卷轴与「老余」印章，背景仍是大厅。
- `published-notice-precheck.png`：同一次发布中从大厅完成的浏览器内预检报告（CONDITIONAL_GO，8 通过 / 0 失败 / 3 条证据 / 6 条比较）。
- `published-badges-hall-desktop.png`、`published-badges-hall-mobile.png`：2026-10-28 徽章版公开首屏；值班台六格徽章架点亮并佩戴「夜灯初证」，顶栏显示佩戴中的徽章，手机顶栏保留勋章入口。
- `published-badges-shop-desktop.png`、`published-badges-shop-mobile.png`：同一次发布的羊皮卷徽章铺；20 枚初始余额下只有 15 枚的夜灯初证可购，其余显示还差多少，手机单列展示六枚。
- `published-badges-owned-desktop.png`：购下并自动佩戴夜灯初证后的铺内状态，余额 5、购买提示与「摘下」按钮。
- `published-eyes-idle-desktop.png`、`published-eyes-blink-desktop.png`、`published-eyes-think-desktop.png`：2026-10-28 放大眼睛版的公开首屏、闭眼瞬间与翻档表情，虹膜与高光更明显，撇嘴不再带旧笑容残影。
- `published-eyes-idle-mobile.png`：同一次发布的 390×844 首屏，大眼与圆框眼镜比例正常、无横向溢出。
- `published-face-idle-desktop.png`、`published-face-idle-face.png`、`published-face-listen-face.png`、`published-face-idle-mobile.png`：2026-10-28 闭眼值班版公开首屏、面部特写与 390px 首屏；值班和聚焦听写时保留原画闭眼微笑。
- `published-face-found-face.png`、`published-face-found-mobile.png`：同一次发布的“有出处”睁眼特写，桌面与手机各一张。
- `face-blink.png`、`face-open-think.png`、`face-open-found.png`、`face-wink.png`、`face-hall-desktop.png`、`face-hall-mobile.png`：同一构建的本地状态矩阵，用于逐状态比对眨眼、翻档、有出处、购章笑眼与桌面/手机大厅。
- `published-thought-idle-desktop.png`、`published-thought-listen-desktop.png`、`published-thought-found-desktop.png`、`published-thought-blank-desktop.png`、`published-thought-error-desktop.png`：2026-10-28 思考气泡带两字标签版（历史留档）的公开首屏与在听、有出处、没翻到、出错场景；大气泡为 emoji 与两字状态，中、小圆点朝头部渐小。
- `published-thought-idle-mobile.png`、`published-thought-found-mobile.png`：同一次发布的 390×844 首屏与“有出处”，手机大气泡 68px、标签完整落在圆内。
- `thought-pleased-local.png`：标签版本地购章后的 wink 与“不错 😉”气泡。
- `published-mood-icons-idle-desktop.png`、`published-mood-icons-listen-desktop.png`、`published-mood-icons-think-desktop.png`、`published-mood-icons-found-desktop.png`、`published-mood-icons-blank-desktop.png`、`published-mood-icons-error-desktop.png`：2026-10-28 emoji-only 版的公开首屏与六种心情场景，气泡内只显示 💤 / 👂 / 🕵️ / 🥳 / 😔 / 😰，可见中文已移除。
- `published-mood-icons-idle-mobile.png`、`published-mood-icons-found-mobile.png`：同一次发布的 390×844 首屏与“有出处（🥳）”，气泡位置与尺寸不变。
- `mood-icons-pleased-local.png`：emoji-only 版本地购章后的 wink 与 🎉 气泡。
- `published-hall-clean-desktop.png`、`published-hall-clean-mobile.png`、`published-guide-desktop.png`、`published-guide-mobile.png`、`published-guide-precheck.png`：同日上一版大厅清理与旧名指南的历史留档。
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
- Qoder Sites 公开版现在在浏览器内执行真实检索与确定性预检，但只针对随构建打包的 94 条公开馆藏（20 张重建演示卡 + 74 篇论文摘要，其中 83 条带可定位证据）；不会读取或上传访问者资料，结果不写入 seekdb、不读取 PowerContext、不能执行人工终审。资料导入、秘书扫描与审阅、持久化提交、终审、实验回流和可写回放仍需本地 Compose 服务。
- 公开大厅已移除静态演示馆藏、研究秘书样例与「填入示例」；我的馆藏、研究秘书与持久化操作只在本地真实服务模式出现。公开大厅保留实时检索、正式考据、旧裁决与技术档案，操作说明集中在羊皮卷「档案馆入棺须知」，入口为牌匾下方的悬挂木牌，老余两侧另有快捷按钮。
- 研究方向拆分后，完整预检只比较同一 `task` 或同一 `domain` 的记录；档案馆大厅与只读历史检索仍显式查全馆。`general`、`research`、`all` 和空值仅作为“全馆范围”输入保留，不再写入任何档案记录。跨方向研究仍需手动选择 `general` 才会看到全馆结果。
- 大厅与只读检索按全馆范围设计，查询若同时包含另一研究线的别名（例如“时序……泛化”里的“泛化”也是科学机器学习别名），可能先返回那条线的旧档；这不是分域失效，完整预检仍按 task/domain 收敛。实际复测中纯时序查询只返回时序档。
- 公开馆藏是重建演示卡与公开论文摘要，不是访问者自己的实验日志；浏览器内引擎使用与服务端相同的算法版本标识，但公开版的检索分数与裁决只用于演示同一条规则链路，不替代本地真实数据的预检结论。
- 档案馆的考据币与已购徽章只保存在浏览器 `localStorage`，不上传；购买不退币、摘下不扣币。角色与场景采用组员手绘插画和本地 CSS/SVG，不加载远程素材。
- 公开站点已于 2026-10-28 更新为浏览器内动态版本，并发布大量论文版本（72 篇种子论文 + 2 篇验收论文摘要，94 条公开馆藏，本次每个研究方向各新增 6 篇）；匿名桌面 1440×900 与手机 390×844 均完成写纸条→实时回执和完整预检，结果随输入变化，控制台 0 错误、无横向溢出。公开版仍不连接在线后端，真实资料与持久化验证需按本地 Compose 步骤运行。
- 档案馆只拦空输入；1 个字或 4 个字的短查询同样可以提交，不会静默忽略点击。
- 本地 PowerContext 配置关闭访问控制，仅绑定回环地址，不能直接暴露公网。
- 代码推送与仓库公开由账号持有人授权执行；Qoder 使用账号持有人已登录的 GitHub 凭据完成推送与远端内容复核，未更改仓库可见性。

## 账号持有人操作

- 推送已由账号持有人授权完成：个人仓库 `2026-competition-ecosystem` 与团队仓库 `submit/qoder` 均已同步 2026-10-29 的收尾提交；平台填报团队分支的完整 Commit。
- 仓库已设为公开；2026-10-27 匿名访问 `https://github.com/AtoFuture/NullPath-Research-CI` 返回 200，无需授权即可查看。
- 2026-10-28 将 `qoder/` 项目提交到大赛登记的团队仓库 `juanzhi-gcb/powercontext` 的 `submit/qoder` 分支，未改动队友共用的 `2026-competition-ecosystem`；平台填报该分支的完整 Commit。
- 仍需在 Qoder 客户端补充 Qoder 账号 UID，以及关键开发环节的对话截图或录屏。
