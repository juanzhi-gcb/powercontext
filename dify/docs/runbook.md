# 运行手册

## 部署前提与路径

目标环境为 Windows + WSL2 + Docker Desktop。命令在 **Windows PowerShell** 中运行，Docker Desktop 使用 WSL2 后端运行 Linux 容器；不需要在 WSL shell 中调用 Windows 的 `D:/...` 路径。确保 PowerShell 可找到 `uv`、Python 3.12、Git 和 Docker Desktop CLI，并有足够磁盘空间下载镜像、上游源码和持久数据。

Windows PowerShell 示例，从仓库 `dify/` 目录执行：

```powershell
Set-Location D:/DifyPawnshop/submission/dify
```

Windows 命令的 `--root` 使用 Windows 绝对路径 `D:/DifyPawnshop`。如果改在 Linux/WSL shell 运行，必须同时使用 Linux 绝对路径，例如 `--root /mnt/d/DifyPawnshop`（或 Linux 主机上的 `/opt/DifyPawnshop`），不可在 Bash 中传入 `D:/...`。Linux/WSL shell 示例：

```bash
cd /mnt/d/DifyPawnshop/submission/dify
uv run --no-project --python 3.12 python scripts/bootstrap.py --root /mnt/d/DifyPawnshop
uv run --no-project --python 3.12 python scripts/manage.py up --root /mnt/d/DifyPawnshop
```

不要把上游 Dify 全量源码或本地凭据放进提交目录。

## 获取固定依赖与启动

首次在当前机器初始化：

```powershell
uv run --no-project --python 3.12 python scripts/bootstrap.py --root D:/DifyPawnshop
```

脚本获取并检出 Dify `1.17.1`，commit `8387590ace4a094de812b7847fc6a4c3a27cd52b`，以及 PowerContext commit `31ecdd61beadb7ac8de5da20998dead9a9e07845`。源码放在 root 目录下，不属于提交内容。脚本在 `dify/deploy/.env` 创建游戏 API 密钥和 PowerContext token，在 `D:/DifyPawnshop/dify-runtime/docker/.env` 建立 Dify 本地配置，并在 `D:/DifyPawnshop/model.env` 写入模型配置占位项；已存在文件不会被覆盖。请保管这些本地秘密，不要提交、贴入截图或日志。

启动仅属于此项目的 Compose 服务：

```powershell
uv run --no-project --python 3.12 python scripts/manage.py up --root D:/DifyPawnshop
uv run --no-project --python 3.12 python scripts/manage.py status --root D:/DifyPawnshop
```

服务入口：自定义柜台界面 `http://localhost:18081/`，Dify `http://localhost:18080`，游戏后端 `http://localhost:18081`，PowerContext `http://localhost:18082`。Dify 使用单独的 Compose project `pawnshop-dify`；游戏服务使用 `pawnshop-game`。`manage.py down` 会停止这两组服务，但保留持久数据和共享网络：

```powershell
uv run --no-project --python 3.12 python scripts/manage.py down --root D:/DifyPawnshop
```

不要运行 `docker compose down -v` 或删除数据目录来重置演示。使用新的玩家 ID 即可开始一份干净存档。

## 初始化 Dify 和配置模型

1. 首次初始化可选择运行下方的 `configure_dify.py` 自动创建本地管理员并导入应用；若选择手工配置，则打开 `http://localhost:18080` 完成管理员初始化，再按本节导入 DSL。不要先手工初始化后再期待脚本替你创建账号。
2. 在 Dify **模型供应商**中配置自己拥有凭据的兼容聊天模型 provider，并确认该模型可用于 Chatflow。模型供应商尚未随项目预置或配置；模型 API 密钥只在本机 Dify 设置中填写，不要写入 DSL 或提交材料。实际端点及模型名称以所选 provider 的配置要求为准。
3. 本仓库的 `dsl/pawnshop-chatflow.yml` 是由项目构建器生成的 DSL，不是从 Dify 导出的运行记录。进入 `dify/` 目录，检查 DSL 构建参数：

   ```powershell
   uv run --project backend python scripts/build_dsl.py --help
   ```

   构建器默认 provider 为 `langgenius/openai_api_compatible/openai_api_compatible`，默认模型名为 `pawnshop-model`，服务 URL 为 `http://pawnshop:8080`。仓库内已提交的 DSL 是按本机验收所用模型名构建的；**如果你配置的模型名不同，先用你的名称重新生成再导入**：

   ```powershell
   uv run --project backend python scripts/build_dsl.py --provider langgenius/openai_api_compatible/openai_api_compatible --model <你的模型名> --service-url http://pawnshop:8080 --output dsl/pawnshop-chatflow.yml
   ```

   该文件可用作导入源；其中模型引用必须与 Dify 中已配置的 provider 和模型名相符。导入或创建 Chatflow 后，在模型节点选择已配置模型，并将其发布。
4. 在该 Chatflow 的环境变量中设置 `PAWNSHOP_API_KEY`，值必须与本地 `dify/deploy/.env` 中自动生成的同名变量一致。不要在 DSL 中写入真实密钥。HTTP 节点访问后端的地址应为 `http://pawnshop:8080`，这是 Compose 私有网络中的服务名，不能替换成容器内的 `localhost`。
5. 游戏 API 和 PowerContext 通过 `pawnshop-shared` Docker 网络连接。Dify SSRF 私网访问仅允许 `172.30.92.0/24`，用于上述容器间通信；不要扩大为整个私网范围。若同名网络已经存在但子网不同，启动脚本会停止并要求先检查现状，不会擅自改网。

此流程不配置知识库，不需要 Embedding 或 Rerank。Dify 本身的模型推理和工作流编排不可由 `verify_services.py` 代替。

## 自动初始化本地 Dify 并导入 DSL

服务启动后，可用辅助脚本初始化本地 Dify 管理员账号并导入 DSL。该脚本只用于本机实例：

```powershell
uv run --project backend --group dev python scripts/configure_dify.py --root D:/DifyPawnshop
```

首次初始化会在 `D:/DifyPawnshop/local-credentials.json` 生成本地管理员凭据，然后登录 Dify 并导入 `dsl/pawnshop-chatflow.yml`。导入请求中的 `PAWNSHOP_API_KEY` 从 `dify/deploy/.env` 读取，仅在内存中注入，不会写回 DSL。导入状态写入 `D:/DifyPawnshop/dify-local.json`，不含模型凭据；导入证据写到 `dify/docs/evidence/dify-import.json`，并标明 `model_executed: false`。请勿提交本地管理员凭据文件。

若要另建一份应用以验证干净导入，可加 `--new-app`：

```powershell
uv run --project backend --group dev python scripts/configure_dify.py --root D:/DifyPawnshop --new-app
```

这会创建另一份应用并记录 `dify-reimport.json`。该脚本验证真实 Dify 导入，不会配置模型 provider、发布应用或执行对话；这些步骤仍须人工完成并分别记录。若 Dify 已初始化但本地 `local-credentials.json` 不存在，脚本不会重置账号；请在 Dify 中手动创建/使用管理员凭据，再按项目流程导入。

## 自定义前端与当票

前端由游戏后端在同一端口提供（`http://localhost:18081/`），不需要单独的 Web 服务。它通过 `/api/*` 访问后端 BFF，BFF 再用服务端保存的密钥调用 Dify 的应用 API，因此浏览器里没有模型密钥，也没有游戏服务密钥。

启用步骤：

1. 在 Dify 打开已发布的 Chatflow，进入「访问 API」，生成应用 API 密钥。
2. 把它写入本机 `dify/deploy/.env` 的 `DIFY_APP_API_KEY=`；`DIFY_API_URL` 默认 `http://api:5001/v1`，这是共享 Docker 网络里的 Dify API 服务名。
3. `PAWNSHOP_SESSION_SECRET` 由 `bootstrap.py` 生成，用于给当票 Cookie 签名；换成新值会让所有浏览器里的当票失效，但存档本身不丢，重新认领即可。
4. 重新启动游戏服务：`uv run --no-project --python 3.12 python scripts/manage.py up --root D:/DifyPawnshop`。

`deploy/compose.yaml` 把 `dify/frontend` 只读挂载到容器 `/app/frontend`，改界面不需要重建镜像；镜像里也包含一份前端副本，用于不带挂载的运行。前端首次进店会生成一张当票，换浏览器后可在「当票」弹窗里用旧当票认领同一份存档。当票是 bearer 凭证，不要公开。

界面验收（可选，需要 Node.js 与本机 Edge）：

```powershell
Set-Location D:/DifyPawnshop/submission/dify
npm install
npm run verify:ui
```

脚本会真实走一遍鉴定、纠正、确认典当、货架、记忆来历，并在第二个干净浏览器里认领同一张当票；截图默认写入 `docs/evidence/`。它调用真实模型，耗时约一分钟。

## 记忆与身份行为

Dify 的 Start 节点身份字段用于 API 调用：后端以 Dify `sys.user_id` 作为玩家标识、`sys.conversation_id` 作为会话标识、`sys.workflow_run_id` 作为本轮幂等 turn 标识。HTTP `prepare` 提供 SQLite 账本快照和 PowerContext 记忆；模型只提出结构化动作建议，后端验证后执行状态变更并返回回执。最终回答展示经校验的后端回执，而不是直接把模型提案当作交易成功。

玩家需显式发送**“确认典当”**，工作流才允许提交 pawn 动作。跨会话回忆依赖同一个 `user_id`，而不是相同会话 ID。Dify WebApp 的浏览器身份是否在不同浏览器或设备间保持一致，不能作为本项目身份连续性的保证；手动体验应在同一应用身份下新建会话，或用后述 API 验证脚本固定玩家 ID 并更换 `conversation_id`。

如用 Dify API 验证身份连续性，应对 `/chat-messages` 请求在不同对话间保持相同 `user` 值，并使用新的 `conversation_id` 开始第二段对话；按 Dify API 要求提供本机 Dify 应用凭据。不要把 Dify API 凭据写入仓库或证据文件。该 API 身份与游戏后端的 `user_id` 映射须以实际发布的 Chatflow 输入为准；验收时检查新会话的 `prepare` 确实携带同一玩家身份。

PowerContext 返回 `unavailable` 或等待同步时，应用必须如实显示该状态，不可把 SQLite 中的交易记录说成记忆已同步。SQLite 是确切物品状态账本，PowerContext 是跨会话叙事记忆，两者用途不同。

## 健康检查和脚本验证

健康检查只确认后端进程可用：

```powershell
Invoke-RestMethod http://localhost:18081/health
```

服务集成脚本使用随机虚构玩家，直接调用游戏 API；在 PowerContext 正常运行且 API 密钥有效时，它会检查记忆写入和读取、跨会话回访、货架隔离、重复提交及取回，并把记录写入 `dify/docs/evidence/services.json`（若该目录存在且运行成功）。从 `dify/` 运行：

```powershell
uv run --project backend python scripts/verify_services.py
```

此脚本**不运行 Dify，也不调用真实模型**。它不能作为 DSL 成功导入、模型连通或完整 Dify 端到端体验的证据。其输出中 `dify_model_executed: false` 是预期标记。任何验收材料都应注明其证据范围。

真实 Dify + 模型端到端验收：

```powershell
uv run --project backend python scripts/verify_e2e.py --root D:/DifyPawnshop
```

前置条件：应用已发布，`D:/DifyPawnshop/dify-local.json` 记录了该应用的 `app_id` 与 `api_key`（可在 Dify 应用的「访问 API」页生成 API 密钥后填入，不要提交此文件），控制台账号文件存在。脚本会跑完鉴定、纠正、确认典当、新会话召回、回访与玩家隔离，并从每轮 `workflow_run_id` 的节点执行记录中取回 prepare、act 的真实输出，写入 `docs/evidence/e2e.json`。若新会话的 prepare 未返回 `ready`，先确认后端与 PowerContext 正常，再检查 Chatflow 的 `PAWNSHOP_API_KEY` 是否与 `deploy/.env` 一致。

## 停止、重置与排错

- **开始全新体验：**生成一个全新的稳定玩家 ID。不要在每轮随意更换同一玩家 ID，也不要清空数据库。
- **服务不可达：**运行 `manage.py status`，查看容器状态；检查 Docker Desktop / WSL 是否运行，以及本机端口 18080、18081、18082 是否已被占用。
- **Dify 无法访问后端：**确认 DSL 的服务 URL 是 `http://pawnshop:8080`、Dify 环境变量 `PAWNSHOP_API_KEY` 与 `deploy/.env` 值完全一致，并且两个 Compose 项目都接入 `pawnshop-shared` 网络。
- **记忆状态 unavailable/pending：**查看 PowerContext 服务与其日志，确认 token 与数据目录已挂载；不要通过伪造记忆内容或宣称 SQLite 记忆回读来掩盖错误。
- **模型节点报错：**检查 Dify 中 provider 凭据、兼容 API 地址和模型名称；不要把密钥写入 DSL、命令行历史或提交目录。
- **源码或数据目录：**初始化脚本只在 root 目录建立上游 checkout 和数据目录。若需要换目录，先停止本项目服务，再以新的 `--root` 初始化；勿清理其它 Docker 项目或共用存储。
