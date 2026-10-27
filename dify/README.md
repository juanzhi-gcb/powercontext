# 烦恼典当行

一个由 Dify Chatflow 驱动的文字叙事游戏：玩家把烦恼交给老板老余，鉴定成一件奇幻物品；玩家可以纠正鉴定、明确确认典当，之后在新会话里凭记忆回访，让物品随经历变化，再查货架或取回。奇幻物品与老余的台词是游戏叙事，不是对玩家作诊断或预言。

## 组件分工

- **Dify 1.17.1** 运行模型、提示词和分支编排。玩家身份、会话、原话及账本和记忆返回值都由 Chatflow 明确传递。
- **PowerContext** 保存已确认的物品故事、玩家纠正和回访经历；新会话时由后端读取，为老余提供跨会话回忆。它承担持久记忆，不是 Dify 的向量知识库，也不替代交易账本。
- **FastAPI + SQLite** 校验玩家身份、物品版本、确认语句和状态转换，保存权威账本，并返回可展示的交易回执。

工作流、原型和提示词为本项目原创。实现不依赖自定义 Dify 插件、Embedding 或 Rerank；模型由使用者在 Dify 配置兼容的 provider。Dify 使用官方默认部署数据服务，本项目不声称使用 seekdb。

## 快速开始

部署细节、模型配置、DSL 导入、网络和排错见[运行手册](docs/runbook.md)。验收步骤和证据边界见[验收说明](docs/acceptance.md)；许可与来源见[归属说明](docs/attribution.md)。

在 Windows PowerShell 中进入仓库的 `dify/` 目录，确认 Docker Desktop 正在运行，并安装 Python 3.12、`uv`、Git 和 Docker Desktop（其 Linux 容器由 Docker Desktop 的 WSL2 后端运行）：

```powershell
Set-Location D:/DifyPawnshop/submission/dify
uv run --no-project --python 3.12 python scripts/bootstrap.py --root D:/DifyPawnshop
uv run --no-project --python 3.12 python scripts/manage.py up --root D:/DifyPawnshop
```

访问 Dify：<http://localhost:18080>；游戏后端健康检查：<http://localhost:18081/health>；PowerContext：<http://localhost:18082>。首次使用请按运行手册在 Dify 完成初始化、配置模型 provider、导入 DSL 并设置密钥。

也可用 `uv run --project backend --group dev python scripts/configure_dify.py --root D:/DifyPawnshop` 自动创建本地 Dify 管理员凭据并导入项目生成的 DSL；新应用重复导入验证可加 `--new-app`。脚本不会配置模型、发布应用或执行对话，真实导入结果仍须查看验收记录。

`bootstrap.py` 会将固定版本的上游源码和运行数据放在 `D:/DifyPawnshop`，并在项目 `dify/deploy/.env` 自动生成本地密钥。该文件和 `D:/DifyPawnshop/model.env` 都是本机配置，禁止提交或分享。停止服务用 `uv run --no-project --python 3.12 python scripts/manage.py down --root D:/DifyPawnshop`；数据保留。每次演示请使用新的稳定玩家 ID，重置不需要删除数据库。

## 当前验收状态

2026-10-27 在本机实际执行并通过：后端测试 23 项、DSL 检查 61 项、真实后端 + PowerContext 集成、真实 Dify 1.17.1 导入与干净重导入、应用发布，以及使用真实模型的 Dify 端到端脚本（鉴定 → 纠正 → 确认典当 → 新会话召回 → 回访转化 → 玩家隔离）。逐项命令、环境与证据文件见[验收说明](docs/acceptance.md)，原始记录在 `docs/evidence/`。

端到端脚本会读回每轮 workflow 的节点执行记录，证据里的 `memory_context` 是 prepare 节点实际交给模型的内容，不只是模型回答。尚未执行的项目（浏览器身份连续性、换机复现）在验收说明中单独列为待执行。
