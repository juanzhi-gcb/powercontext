# 端侧 Embedding + seekdb 混合检索

一个迷你知识库 Web 应用：文档在**浏览器本地**完成向量化，向量与原文写入 **seekdb**，查询在本地生成向量后交给 seekdb 做**向量 + 全文混合检索**。

- 模型：`Xenova/all-MiniLM-L6-v2`（384 维，INT8 量化）
- 端侧运行时：Transformers.js（ONNX Runtime Web），优先 WebGPU，不支持时自动降级 WASM
- 数据库：seekdb 嵌入式模式（`seekdb` npm SDK + `@seekdb/js-bindings`）

## 环境要求

| 项 | 要求 |
|---|---|
| 浏览器 | Chrome / Edge 最新版（WebGPU 可用时自动启用，否则 WASM） |
| Node.js | 20 LTS 或更高 |
| 操作系统 | **Linux**（x64 / arm64）或 macOS（arm64）——seekdb 嵌入式原生绑定只发布这些平台 |
| 系统库 | Linux 需要 `libaio`：Ubuntu 24.04+ 为 `libaio1t64`，并补一个 `libaio.so.1` 兼容链接 |

> Windows 用户请在 WSL2（Ubuntu）中运行，浏览器仍使用 Windows 侧的 Chrome/Edge 访问 `http://127.0.0.1:8787`。

Linux 上补齐 libaio 兼容链接（只需一次）：

```bash
sudo apt-get install -y libaio1t64
sudo ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1
sudo ldconfig
```

## 安装与启动

```bash
cd stepfun
npm install

# 开发模式：Vite 前端 + 后端 API（前后端热更新）
npm run dev
# 前端 http://127.0.0.1:5173 ，API 通过 Vite 代理到 8787

# 生产模式：先构建前端，再由同一个 Node 进程同时提供页面与 API
npm run build
npm start
# 打开 http://127.0.0.1:8787
```

首次 `npm start` 时，`scripts/with-seekdb-lib.sh` 会在 `~/.seekdb` 下找到原生库并以 `LD_PRELOAD` 方式启动 Node。这是必要的一步：Node 的 `dlopen` 无法为 seekdb 预留的静态 TLS 块分配空间。

数据库文件默认落在 `stepfun/seekdb-data/kb.db`，可用环境变量覆盖：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8787` | HTTP 端口 |
| `EMBED_DIMENSION` | `384` | 向量维度，须与浏览器模型一致 |
| `SEEPDB_PATH` | `./seekdb-data/kb.db` | 嵌入式数据库目录 |
| `SEEPDB_DATABASE` | `kb` | 数据库名（启动时自动创建） |
| `SEEPDB_COLLECTION` | `documents` | 集合名（自动创建） |

## 使用

1. 打开页面，等待模型加载完成；右上角徽标显示当前推理后端（`WEBGPU` 或 `WASM`）。
2. 选择 `data/corpus/` 下的若干 `.md` 文件，点「向量化并写入 seekdb」。
3. 输入问题（例如 *How does seekdb fuse the two retrieval branches?*）点「检索」，结果按 seekdb 返回的顺序展示，含文档 ID、来源和距离。
4. 「运行指标」面板显示各阶段耗时：模型加载、文档向量化、写入、查询向量化、seekdb 检索、端到端。

## 目录

```
stepfun/
├── server/index.mjs          # Express API + seekdb 客户端
├── web/                      # 前端（Vite + TypeScript）
│   ├── src/embedder.ts       # Transformers.js 加载、WebGPU/WASM 降级、批量向量化
│   ├── src/api.ts            # 与后端交互
│   └── src/main.ts           # 页面逻辑与指标面板
├── scripts/with-seekdb-lib.sh# LD_PRELOAD 启动包装
├── data/corpus/              # 演示语料
└── TECH_NOTE.md              # 一页技术说明（含实测数据）
```

## 数据流

```
浏览器                          Node (seekdb 嵌入式)
文件 → 切分 → MiniLM(INT8) ──┐
                             │  POST /api/import  (ids, text, 384维向量, metadata)
                             └──────────────► collection.add(embeddings=...)
问题 → MiniLM(INT8) ─────────┐
                             │  POST /api/search  (query, queryVector, k)
                             └──────────────► collection.hybridSearch(knn={queryEmbeddings, queryTexts})
                                                   │
                                结果（ids / 原文 / 距离）◄──┘
```

服务端**从不计算向量**：集合绑定的 embedding 函数会直接抛错，任何绕过浏览器推理的调用都会失败。
## 离线模型与基准测试

```bash
npm run models      # 下载权重到 public/models（约 113 MB），页面不再访问外部主机
npm run benchmark   # 需要先 npm i -D puppeteer-core，并设置 CHROME_PATH（默认 Edge）
```

`benchmark` 用 Puppeteer 打开正在运行的应用，通过页面暴露的 `window.__kb.Embedder` 以 q8 与 fp32 分别编码同一查询集，输出目标文档名次与 MRR——两个精度走完全相同的代码路径。

降级验证：给浏览器加 `--disable-gpu`，并在页面加载前把 `navigator.gpu` 置空，界面徽标会显示 `WASM`，核心流程仍可用。
