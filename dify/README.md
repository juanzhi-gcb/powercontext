# 烦恼典当行

一个由 Dify Chatflow 驱动的文字叙事游戏：玩家把烦恼交给老板老余，鉴定成一件奇幻物品；玩家可以纠正鉴定、明确确认典当，之后在新会话里凭记忆回访，让物品随经历变化，再查货架或取回。奇幻物品与老余的台词是游戏叙事，不是对玩家作诊断或预言。

## 组件分工

- **Dify 1.17.1** 运行模型、提示词和分支编排。玩家身份、会话、原话及账本和记忆返回值都由 Chatflow 明确传递。
- **PowerContext** 保存已确认的物品故事、玩家纠正和回访经历；新会话时由后端读取，为老余提供跨会话回忆。它承担持久记忆，不是 Dify 的向量知识库，也不替代交易账本。
- **FastAPI + SQLite** 校验玩家身份、物品版本、确认语句和状态转换，保存权威账本，并返回可展示的交易回执。
- **自定义前端（`frontend/`）** 是柜台场景与人物交互界面。它只负责展示和输入，通过后端 BFF 转发到同一个已发布的 Dify 应用；模型和编排仍在 Dify，Dify 自带 WebApp 也仍可直接使用。

工作流、原型和提示词为本项目原创。实现不依赖自定义 Dify 插件、Embedding 或 Rerank；模型由使用者在 Dify 配置兼容的 provider。Dify 使用官方默认部署数据服务，本项目不声称使用 seekdb。

## 快速开始

一次真实运行的完整摘录见[体验记录](docs/demo.md)。部署细节、模型配置、DSL 导入、网络和排错见[运行手册](docs/runbook.md)；验收步骤和证据边界见[验收说明](docs/acceptance.md)；许可与来源见[归属说明](docs/attribution.md)。

在 Windows PowerShell 中进入仓库的 `dify/` 目录，确认 Docker Desktop 正在运行，并安装 Python 3.12、`uv`、Git 和 Docker Desktop（其 Linux 容器由 Docker Desktop 的 WSL2 后端运行）：

```powershell
Set-Location D:/DifyPawnshop/submission/dify
uv run --no-project --python 3.12 python scripts/bootstrap.py --root D:/DifyPawnshop
uv run --no-project --python 3.12 python scripts/manage.py up --root D:/DifyPawnshop
```

访问自定义柜台界面：<http://localhost:18081/>；Dify 控制台与自带 WebApp：<http://localhost:18080>；健康检查：<http://localhost:18081/health>；PowerContext：<http://localhost:18082>。首次使用请按运行手册在 Dify 完成初始化、配置模型 provider、导入并发布 DSL，再把该应用的 API 密钥填入本机 `deploy/.env` 的 `DIFY_APP_API_KEY`（前端 BFF 用它转发到同一应用）。

也可用 `uv run --project backend --group dev python scripts/configure_dify.py --root D:/DifyPawnshop` 自动创建本地 Dify 管理员凭据并导入项目生成的 DSL；新应用重复导入验证可加 `--new-app`。脚本不会配置模型、发布应用或执行对话，真实导入结果仍须查看验收记录。

`bootstrap.py` 会将固定版本的上游源码和运行数据放在 `D:/DifyPawnshop`，并在项目 `dify/deploy/.env` 自动生成本地密钥。该文件和 `D:/DifyPawnshop/model.env` 都是本机配置，禁止提交或分享。停止服务用 `uv run --no-project --python 3.12 python scripts/manage.py down --root D:/DifyPawnshop`；数据保留。每次演示请使用新的稳定玩家 ID，重置不需要删除数据库。

## 自定义前端

界面按“赛博深夜便利店 + 纸 + 暖黄 + 铅字 + 立绘”的方向绘制：雨夜街景、木柜台、纸票据、盖章动效，以及灰白卷发、圆眼镜、围裙上别着「老余」名牌的掌柜。所有美术为项目内原创的 CSS/SVG，不依赖外部图片或 CDN。

店面有明确的分区：货架和玻璃冷柜在上半区，受理单和藏品卡固定在底部纸带区，两者不重叠；窗口高度不足时会自动收紧纸带高度，靠内部滚动而不是压住货架。招牌、挂签、挂钟、旧纸条、勇气币牌、日历、绿植、算盘、账本、硬币盘、茶缸和猫分布在四周；鼠标移动时各层有轻微视差，整体像在柜台前微微换角度。冷柜、货架、受理单和藏品卡都有各自的透视与投影。

- **身份**：首次进店生成一张当票（如 `H63FN-J4FGG`），存在签名 Cookie 里；换浏览器或手机后用当票认领同一份存档。当票就是玩家标识，不要公开。
- **交互**：你写的话会以纸条飞向柜台，并留在受理单上；等待时账本翻页、老余的灯会暗一点；老板台词逐字打印，受理单会像刚打印出来一样落下；藏品卡从柜台侧边出现，印章带墨迹压上去。点卡片或「这件的来历」可以看这一件的每次事件、记忆编号和来源编号。冷柜里的瓶子和货架上的价签可以点，老余会补一句柜台旁白。
- **表情与动作**：老余有四套表情（平静、琢磨、温和、认真），发送时低头翻账本，回复时抬眼，出错时皱眉；确认典当会有一次盖章的手部动作。立绘内联在页面里，所以这些表情是可切换的 SVG 分组，不是换图片。
- **勇气币**：由后端真实发放并持久保存——鉴定 +10、纠正 +15、确认典当 +25、回访 +30、取回 +5；重复提交同一 turn 不会重复发放。柜台右侧的牌子列出同一套规则，界面底部显示余额，发放时有一枚飘起的 +N。它记录你做过的事，目前不作为购买力，也不按烦恼的轻重给分。
- **架构**：浏览器只与游戏后端的 `/api/*` 通信；BFF 用服务端保存的 Dify 应用密钥转发 `/v1/chat-messages`，并把 `user` 固定为当票玩家。模型调用、分支和记忆召回仍在 Dify 与后端内完成，浏览器拿不到任何密钥。
- **换立绘**：老余现在是 `index.html` 里内联的 SVG（表情分组需要内联）。要换成正式立绘，用 `<img src="assets/你的立绘.png" alt="老余">` 替换 `.laoyu` 里的整段 `<svg>`；表情切换会失效，但柜台其余部分不受影响。静态导出仍保留在 `frontend/assets/laoyu.svg` 供参考。
- **验证**：`npm install && npm run verify:ui` 会用本机 Edge 跑一遍真实界面流程（鉴定、纠正、典当、货架、记忆来历、第二浏览器认领、手机布局），截图写到 `docs/evidence/`。

## 当前验收状态

2026-10-27 在本机实际执行并通过：后端与 DSL 测试 97 项、真实后端 + PowerContext 集成、真实 Dify 1.17.1 导入与干净重导入、应用发布、使用真实模型的 Dify 端到端脚本（鉴定 → 纠正 → 确认典当 → 新会话召回 → 回访转化 → 玩家隔离），以及用无头 Edge 驱动的自定义前端全流程、勇气币累计与表情切换、跨浏览器当票认领。逐项命令、环境与证据文件见[验收说明](docs/acceptance.md)，原始记录与界面截图在 `docs/evidence/`。

端到端脚本会读回每轮 workflow 的节点执行记录，证据里的 `memory_context` 是 prepare 节点实际交给模型的内容，不只是模型回答。尚未执行的项目（换机复现等）在验收说明中单独列为待执行。
