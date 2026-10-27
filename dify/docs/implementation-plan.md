# 烦恼典当行 Implementation Plan

> **For agentic workers:** Use subagent-driven-development for isolated backend and DSL tasks, then independently review spec compliance and code quality. All agents share files; ownership is explicit.

**Goal:** 在 D 盘交付可复现的 Dify + PowerContext 叙事游戏与验收材料。

**Architecture:** Dify owns model execution and orchestration. FastAPI validates game transitions and owns a SQLite ledger; PowerContext supplies persistent memory and readback. Commit identities are pinned in deployment configuration.

**Tech Stack:** Dify 1.17.1, Python 3.12, FastAPI, httpx, SQLite, Docker Compose, PowerContext HTTP.

## Task 1 — Infrastructure（主代理）
- [x] 检查 D 盘、WSL、Docker 磁盘，不迁移既有数据。
- [x] 在 D:\DifyPawnshop\submission 从官方比赛分支建立 feat/dify-pawnshop。
- [x] 提供 deploy/ 中的固定版本依赖获取、环境生成、启动停止配置；Dify 使用独立项目名 pawnshop-dify、端口 18080，避免影响现有服务。
- [x] 将官方 Dify 1.17.1 docker 目录拉到 D:\DifyPawnshop\dify-runtime，数据绑定目录留在 D 盘；启动并检查 /install 与 /console/api/setup。
- [x] 将 PowerContext 固定到已核对的源码 commit，配置持久化目录与鉴权，实际验证 remember/prepare。

## Task 2 — Backend（backend 代理；只拥有 backend/、tests/backend/、data/）
- [x] 根据 design.md 接口先写行为测试：草稿/纠正/确认/回访/取回、隔离、幂等、冲突、记忆不可用。
- [x] 执行测试观察缺失功能失败；实现最小接口、状态、PowerContext HTTP 适配器与 Markdown 渲染。
- [x] 补充 Dockerfile、pyproject、锁定依赖，虚构原型数据；后端不可调用模型。
- [x] 运行完整后端测试，报告准确结果与未验证的外部依赖。

## Task 3 — DSL（workflow 代理；只拥有 dsl/、prompts/、scripts/build_dsl.py、tests/test_dsl.py）
- [x] 针对 Dify 1.17.1 官方源代码核对 HTTP、Code、LLM、IF/Answer 的导入字段。
- [x] 生成主 Chatflow，依照 design.md 契约，显式失败分支，HTTP 密钥仅占位。
- [x] 提供中文老板 prompt、10+ 原创物件原型和边界规则；所有真实模型调用保留于 Dify。
- [x] 测试 DSL 变量引用、请求 JSON 序列化和输出处理；不得将 YAML 静态检查宣称成真实导入。

## Task 4 — Reproducibility and Review（主代理 + 审核代理）
- [x] 提供 README、runbook、acceptance、来源许可说明、版本清单、样例与重置/验证脚本。
- [x] 启动后端、PowerContext，运行真实记忆集成脚本；将虚构数据回执保存 docs/evidence/。
- [x] 在真实 Dify 执行 DSL 导入和干净重新导入；配置用户提供的模型服务并完成跨会话体验。
- [x] 独立执行规格审核和代码审核，修复问题；检查 diff、无真实凭据、资产仅位于 dify/。
- [x] 运行全部必要测试，记录已完成与待用户配置项；本地 commit，不未经明确确认发布公共仓库。

## 执行记录（2026-10-27）

| 检查 | 结果 |
|---|---|
| `pytest tests -q`（后端 + DSL + 控制台登录） | 97 passed |
| `scripts/verify_services.py`（真实后端 + 真实 PowerContext） | passed，见 `docs/evidence/services.json` |
| `scripts/verify_e2e.py`（真实 Dify + 真实模型，跨会话） | passed，见 `docs/evidence/e2e.json` |
| `npm run verify:ui`（无头 Edge，BFF + 真实模型 + 跨浏览器当票） | passed，截图在 `docs/evidence/ui-*.png` |
| `docker compose ... config --quiet` | 通过 |

端到端验收中发现并修复的问题：用户原话直接用作 PowerContext 检索词时，自然口语问句因词法覆盖率不足返回 empty，导致新会话召不回旧藏品。后端改为用账本中的藏品 ID 与名称构造检索锚点，并补了回归测试；修复后真实 Dify 跨会话 prepare 返回 `ready`，召回内容包含玩家纠正原文。

## Checks

后端：`uv run --project dify/backend --group dev pytest dify/tests/backend -q`。

DSL：`uv run --project dify/backend --group dev pytest dify/tests/test_dsl.py -q`。

Compose：`docker compose -p pawnshop-game --env-file dify/deploy/.env -f dify/deploy/compose.yaml config --quiet`。

真实依赖：`uv run --project dify/backend python dify/scripts/verify_services.py`；真实 Dify 模型会话使用独立验收脚本与用户本地配置。所有凭据从环境读取，不在证据中保存。
