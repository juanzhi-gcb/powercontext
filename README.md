# NullPath / Research CI — Qoder 赛道

Qoder × OceanBase 2026 大赛 Qoder 赛道作品。默认入口是游戏化的「研究档案馆」：把研究想法写在纸条上，先拿到只标出处的检索回执，再进入确定性预检、证据链与历史裁决回放。公开站点在浏览器内执行与本地服务一致的哈希嵌入、词面 + 向量 RRF 检索和 `research-ci-rules-v1` 裁决，不连接在线后端。

- 作品网站：<https://nullpath-research-ci-5dqanvro27t.qoder.zone>
- 本项目目录：[`qoder/`](qoder/)
- 运行说明：[`qoder/README.md`](qoder/README.md)
- 开发记录与验证：[`qoder/evidence/qoder-development.md`](qoder/evidence/qoder-development.md)
- 公开版实现：[`qoder/web/src/publicEngine.ts`](qoder/web/src/publicEngine.ts)

本地完整应用：

```bash
cd qoder
cp .env.example .env
docker compose -f deploy/compose.yaml up --build
```

工作台 `http://127.0.0.1:5173`，API 文档 `http://127.0.0.1:8080/docs`。本地验证：

```bash
cd qoder/server
uv sync --extra dev
uv run pytest
uv run python ../evaluation/run_golden.py
uv run python ../evaluation/run_ablation.py
uv run python ../evaluation/run_secretary.py
```

技术栈：React 19 + Vite、FastAPI、seekdb（VECTOR + FULLTEXT/IK + RRF）、PowerContext 1.4.1。公开版是静态构建；资料导入、研究秘书、PowerContext 与人工终审需要本地 Compose。
