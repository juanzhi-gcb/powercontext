# Chatflow 构建与验证

导入文件：`pawnshop-chatflow.yml`。目标为 Dify 1.17.1（`8387590ace4a094de812b7847fc6a4c3a27cd52b`），其源码 `api/constants/dsl_version.py` 指定 DSL `0.7.0`，`api/pyproject.toml` 固定 `graphon==0.7.0`。

在仓库根目录运行：

```powershell
uv run --project dify/backend --group dev python dify/scripts/build_dsl.py
uv run --project dify/backend --group dev pytest dify/tests/test_dsl.py -q
```

模型配置可重新绑定，无需手改节点：

```powershell
uv run --project dify/backend --group dev python dify/scripts/build_dsl.py --provider langgenius/openai_api_compatible/openai_api_compatible --model deepseek-v4.1-flash-1017 --service-url http://pawnshop:8080 --output dify/dsl/pawnshop-chatflow.yml
```

使用默认兼容提供商时，DSL 固定依赖已有的官方模型提供商插件 `langgenius/openai_api_compatible:0.0.72@87f3c4c7acee9ff03ac2c04ba8191edc5ea87cd53e36af1bbf1ccd13f00352a4`。请通过 Dify 官方 Marketplace 安装；本项目无需自定义插件。实际模型与凭据在 Dify 中配置，凭据不放入 DSL。导入后将 Dify 的 `PAWNSHOP_API_KEY` 秘密环境变量设为与后端一致的本地值；文件中的默认值为空。此变量仅供两个 HTTP 节点的 `X-Pawnshop-Key` 使用，不进入模型提示词。

自定义 `--provider` 默认不附加上述插件依赖。可用 `--plugin-identifier namespace/plugin:version@sha256` 明确指定与自定义提供商对应的 Marketplace 唯一标识，或用 `--plugin-identifier none` 省略依赖；后者要求在目标 Dify 工作区自行安装所需模型提供商插件。

`code/*.py` 是实际嵌入各 Code 节点的源码；修改后重新构建 YAML。`../prompts/laoyu-system.md` 是老板规则，`../prompts/item-prototypes.md` 有十二个原创故事原型。二者在构建时嵌入 LLM 节点。

流程依次使用可信 `sys.user_id`、`sys.conversation_id`、`sys.workflow_run_id` 和 `sys.query` 构建 `/v1/prepare`；成功解析快照后才调用模型。模型仅提交提案，不能指定身份或 Scope。`/v1/act` 请求通过 JSON 序列化生成，正式典当还要求本轮原文去除首尾空白后恰为「确认典当」或「确认入柜」。HTTP 自动重试关闭。传输、模型或 Code 失败进入明确错误 Answer，解析失败通过 IF 进入错误 Answer。最终成功 Answer 仅引用真实回执中的 `display`。

测试执行生成图中实际的 Python 文本，覆盖中文、引号与换行序列化、非法提案、未确认典当、错误 HTTP 状态、畸形回执、环境变量和失败分支。已使用原版 graphon 0.7.0 的六类 Pydantic 节点模型校验全部节点。这些是单元与 schema 证据；真实 Dify 导入、真实 PowerContext 集成和模型端到端结果分别由项目验收记录说明。
