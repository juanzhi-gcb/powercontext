# 归属与许可说明

## 本项目原创内容

“烦恼典当行”的游戏概念、中文老余角色与对话规则、原创奇幻物品原型、提示词、Dify Chatflow 构建代码、游戏后端与验收脚本由本项目创作。玩家故事内容应由玩家明确提供；AI 生成的虚构意象不能作为真实个人经历的证据。

前端界面（雨夜便利店柜台场景、纸张与铅字排版、CSS/SVG 立绘《老余》）为本项目原创绘制，不含第三方图片或字体文件。用于确定风格的参考图由项目作者提供，仅作设计参考，不随项目分发。

## 上游软件

本项目部署脚本从官方仓库获取上游软件，相关源码不包含在提交目录中：

- Dify 官方仓库：<https://github.com/langgenius/dify>。部署固定到 Dify 1.17.1，commit `8387590ace4a094de812b7847fc6a4c3a27cd52b`。Dify 依据其仓库所附许可证及各组件自身许可分发；使用者应查看对应固定版本源码中的许可证和通知。
- PowerContext 官方仓库：<https://github.com/oceanbase/powercontext>。部署固定到 commit `31ecdd61beadb7ac8de5da20998dead9a9e07845`。PowerContext 依据其仓库所附许可证及各组件自身许可分发；使用者应查看对应固定版本源码中的许可证和通知。

该部署使用 PowerContext 的 HTTP 服务及其 Source、Memory、PreparedContext 记忆流程。Dify 自身的默认部署数据库由 Dify 管理；游戏账本另由本项目 SQLite 后端管理。项目不声称 Dify 使用 seekdb，也不将 PowerContext 称为 Dify 的向量知识库。

## 模型服务与凭据

模型 provider 尚未由本项目预配置。部署者在 Dify 中自行选择兼容 provider，并按其服务条款、内容政策、数据处理和许可要求使用。API 凭据及本地部署密钥不得提交到仓库、DSL、证据文件或截图。

## 竞赛提交边界

提交交付物限于本目录 `dify/`。`bootstrap.py` 从官方仓库下载固定版本源码至 `--root` 外部路径；本地 `.env`、模型配置、数据库、镜像、日志和凭据均为运行环境文件，不是提交资产。上游项目商标和名称仍属于其各自权利人。
