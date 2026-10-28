# 端侧 Embedding + seekdb 混合检索

一个迷你知识库 Web 应用：文档在**浏览器本地**完成向量化，向量与原文写入 **seekdb**，查询在本地生成向量后交给 seekdb 做**向量 + 全文混合检索**。

- 模型：`Xenova/all-MiniLM-L6-v2`（Apache-2.0，384 维；WebGPU 用 FP16，WASM 用 INT8；固定版本与权重校验值见 [model.json](model.json)）
- 端侧运行时：Transformers.js（ONNX Runtime Web），优先 WebGPU，不支持时自动降级 WASM 并在页面顶部提示
- 数据库：seekdb 嵌入式模式（`seekdb` npm SDK + `@seekdb/js-bindings`）

## 环境要求

| 项 | 要求 |
|---|---|
| 浏览器 | Chrome / Edge 最新版（WebGPU 可用时自动启用，否则 WASM） |
| Node.js | 20 LTS 或更高 |
| 操作系统 | 启动包装脚本面向 **Linux**（x64 / arm64）；实测为 WSL2 Ubuntu x64。Windows 浏览器访问 WSL2 服务。其它平台需适配原生库加载，未声称通过验收。 |
| 系统库 | Linux 需要 `libaio`：Ubuntu 24.04+ 为 `libaio1t64`，并补一个 `libaio.so.1` 兼容链接 |
| 网络 | 首次运行需能访问 AWS S3（seekdb 运行时，约 54 MB）与 Hugging Face（三份模型权重，约 159 MB；只用某一种精度时可自行裁剪）；受限网络见下文的环境变量覆盖方式 |

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
npm run setup   # 首次运行必须执行：下载 seekdb 原生运行时（见下）

# 开发模式：Vite 前端 + 后端 API（前后端热更新）
npm run dev
# 前端 http://127.0.0.1:5173 ，API 通过 Vite 代理到 8787

# 生产模式：先构建前端，再由同一个 Node 进程同时提供页面与 API
npm run build
npm start
# 打开 http://127.0.0.1:8787
```

### 首次运行需要下载原生运行时

`seekdb` 的 npm 包里**不含原生代码**，`@seekdb/js-bindings` 会在首次使用时去 AWS 下载一个约 **54 MB** 的运行时归档，缓存到 `~/.seekdb/bindings/<commit>/<platform>/`。

这一步容易失败：SDK 自带的下载没有超时、没有重试、没有进度，线路慢时会在几 MB 处卡住不动，进程静默挂起而不打印任何错误。因此本仓库用 `scripts/ensure-bindings.sh`（`npm run setup`）显式完成下载：`curl -C -` 断点续传、`--retry`、`--max-time`，并在解包后校验 `seekdb.node` 存在。

```bash
npm run setup
# 已有缓存时立即返回：seekdb runtime already present: ~/.seekdb/bindings/.../linux-x64

# 线路不通或需要走镜像时：
SEEKDB_BINDINGS_BASE_URL=https://<mirror>/js-bindings/all_commits/<commit> npm run setup
```

`npm start` / `npm run dev:server` 启动时会先检查运行时是否就位，缺失就自动调用上面的脚本；脚本失败则**立即报错退出**（`exit 1`）并给出可操作提示，不会挂起。

运行时就位后，`scripts/with-seekdb-lib.sh` 会以 `LD_PRELOAD` 方式加载 `libseekdb.so` 再启动 Node。这是必要的一步：Node 的 `dlopen` 无法为 seekdb 预留的静态 TLS 块分配空间。

数据库文件默认落在 `stepfun/seekdb-data/kb.db`，可用环境变量覆盖：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8787` | HTTP 端口 |
| `EMBED_DIMENSION` | `384` | 向量维度，须与浏览器模型一致 |
| `SEEPDB_PATH` | `./seekdb-data/kb.db` | 嵌入式数据库目录 |
| `SEEPDB_DATABASE` | `kb` | 数据库名（启动时自动创建） |
| `SEEPDB_COLLECTION` | `documents` | 集合名（自动创建） |
| `SEEPDB_FULLTEXT_ANALYZER` | `ngram` | 全文分词器（`space`/`ngram`/`ngram2`/`beng`/`ik`） |
| `SEEPDB_RRF_CONSTANT` | `1` | RRF 常量；调大更保守，调小更看重各分支的第一名 |
| `SEEPDB_CANDIDATE_FACTOR` | `4` | 融合前每路候选数 = `k × factor`（下限 20、上限 100） |

## 使用

1. 打开页面，等待模型加载完成；右上角徽标显示 `后端 · 精度 · 线程数`（如 `WEBGPU · FP16`）。若降级到 WASM，页面顶部会出现黄色横幅说明原因。
2. 选择 `data/corpus/` 下的若干 `.md` 文件，点「向量化并写入 seekdb」；没有文件时直接点**「载入示例语料」**，会导入全部 60 段内置语料。
3. 输入问题（例如 *How does seekdb fuse the two retrieval branches?*）点「检索」，结果按 seekdb 返回的顺序展示，含文档 ID、来源和距离。检索模式可选**混合 / 仅向量 / 仅全文**。
4. 「运行指标」面板显示各阶段耗时：模型加载、文档向量化、写入、**索引刷新**、查询向量化、seekdb 检索、端到端；下方显示集合当前段数。
5. 增量导入：同名文件的同段落按稳定 ID 覆盖，新文件追加；「刷新索引」按钮可单独触发 `refresh_index()`。

降级与精度复现：`http://127.0.0.1:8787/?backend=wasm` 强制 WASM，`?dtype=q8|fp16|fp32` 指定精度。

## 目录

```
stepfun/
├── server/index.mjs          # Express API + seekdb 客户端
├── web/                      # 前端（Vite + TypeScript）
│   ├── src/embedder.ts       # Transformers.js 加载、WebGPU/WASM 降级、批量向量化
│   ├── src/api.ts            # 与后端交互
│   └── src/main.ts           # 页面逻辑与指标面板
├── scripts/with-seekdb-lib.sh# LD_PRELOAD 启动包装
├── bench/
│   ├── matrix.mjs            # 四配置对照（体积/吞吐/延迟/质量）
│   ├── queries.mjs           # 24 条标注查询（评测集）
│   ├── e2e.mjs               # 浏览器端验收（13 项）
│   └── results/matrix.json   # 环境、计时范围与每轮原始样本
├── data/corpus/              # 演示语料（60 段）
├── model.json                # 模型固定 revision、体积、SHA-256
├── TECH_NOTE.md / .pdf       # 一页技术说明
├── BENCHMARK_REPORT.md       # 完整实验说明
└── SUBMISSION.md             # 平台提交字段与私有仓库流程
```

## 数据流

```
浏览器                          Node (seekdb 嵌入式)
文件 → 切分 → MiniLM(FP16/INT8) ─┐
                             │  POST /api/import  (ids, text, 384维向量, metadata)
                             └──────────────► collection.upsert(embeddings=...)
问题 → MiniLM(FP16/INT8) ────┐
                             │  POST /api/search  (query, queryVector, k, mode)
                             └──────────────► collection.hybridSearch(
                                                  query={whereDocument:{$contains}},
                                                  knn={queryEmbeddings}, rank={rrf})
                                                   │
                                结果（ids / 原文 / 距离）◄──┘
```

写入路径末尾调用 `collection.refresh_index()`，刷新耗时与集合段数通过 `GET /api/stats` 回读。

服务端**从不计算向量**：集合绑定的 embedding 函数会直接抛错，任何绕过浏览器推理的调用都会失败。

## 离线模型与基准测试

```bash
npm run models         # FP32/FP16/INT8 三份权重到 public/models（约 159 MB）
npm run bench:matrix   # 四种配置的对照（体积/吞吐/延迟/检索质量）→ bench/results/matrix.json
npm run bench:e2e      # 13 项浏览器验收：导入、刷新、幂等、增量、隔离、检索、降级
```

两个脚本都通过 Puppeteer 驱动本机 Chrome/Edge（`puppeteer-core` 已在 devDependencies 中，`CHROME_PATH` 可覆盖默认的 Edge 路径），并且走应用自身的代码路径：推理用页面里的 `Embedder`，存储与检索用 HTTP API。

`bench:matrix` 默认重复 5 次，输出四配置主表及完整原始计时。端到端走页面同一个 `runQuery`，覆盖查询向量化、seekdb HTTP 请求、DOM 渲染和绘制机会；所有配置都要求实际后端匹配请求，失败时命令返回非零。加载/预热和资源传输观测单列，不把本地 HTTP 权重传输称为首次公网下载。范围详见 [实验说明](BENCHMARK_REPORT.md)。

`bench:e2e` 输出 13 项通过/失败并写入 `bench/results/e2e.json`，每次使用独立测试集合。`npm run benchmark` 也执行 seekdb 矩阵；`bench:embedding` / `bench:sweep` 仅作早期向量一致性与批量探索，不替代正式 seekdb 验收。

`npm run models` 读取 [model.json](model.json)，从固定 revision 下载发布者的 FP32、FP16、INT8 ONNX，并逐一验证字节数与 SHA-256。不在服务端执行模型。`HF_BASE` 仅用于提供相同文件的镜像；哈希不符会退出。`npm run note:pdf` 可用本机 Chrome/Edge 将一页 Markdown 重新渲染成 HTML/PDF。

提交平台的仓库、分支与字段格式见 [SUBMISSION.md](SUBMISSION.md)。仓库根目录也提供 `models`、`test`、`typecheck`、`bench:matrix`、`bench:e2e` 转发命令。
