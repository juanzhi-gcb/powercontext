# 技术说明：端侧 Embedding + seekdb 混合检索

## 1. 模型与量化

| 项 | 值 |
|---|---|
| 模型 | `Xenova/all-MiniLM-L6-v2`（MIT，Hugging Face 公开仓库） |
| 输出维度 | 384，`mean` 池化 + L2 归一化 |
| 量化方式 | ONNX 权重导出：FP32 基线、FP16、INT8（Transformers.js `dtype`） |
| 精度选择 | WebGPU → **FP16**；WASM → **INT8**（依据见 5.2 的实测） |

体积按同一口径统计本服务实际下发的 ONNX 文件（`GET /api/model-info` 直接读文件字节数）：

| 精度 | 文件 | 体积（字节） | 压缩比（相对 FP32） |
|---|---|---:|---:|
| fp32 | `onnx/model.onnx` | 90,387,606 | 1.00× |
| fp16 | `onnx/model_fp16.onnx` | 45,297,825 | 2.00× |
| **int8** | `onnx/model_quantized.onnx` | **22,972,370** | **3.93×** |

## 2. 端侧运行

- 运行时：Transformers.js 4.3.1（ONNX Runtime Web），模型与推理都在页面内。
- 后端选择：先试 `device: "webgpu"`；`navigator.gpu` 缺失或初始化失败时自动改用 `device: "wasm"`。
- 提示：顶部徽标常驻显示 `后端 · 精度 · 线程数`；降级时页面顶部出现**黄色横幅**写明原因（例如“浏览器未暴露 navigator.gpu”），而不是只在悬停提示里。
- 降级复现：访问 `?backend=wasm` 可强制走 WASM，`?dtype=q8|fp16|fp32` 可指定精度；`bench/e2e.mjs` 用同一方式自动验证徽标与横幅。
- 预热：加载后立即推理一次，首条用户查询不承担 kernel 编译开销。
- 多线程 WASM：当 `public/models` 存在（`npm run models`）时，服务端发送 `Cross-Origin-Opener-Policy: same-origin` 与 `Cross-Origin-Embedder-Policy: credentialless`，页面进入跨源隔离，`SharedArrayBuffer` 可用，ORT 以 4 线程运行——WASM 吞吐因此从约 25 ms/段升到 4.5 ms/段。权重仍从 Hugging Face 拉取时不发这些头，避免跨源资源被 COEP 拦截。
- 服务端不参与推理：集合绑定的 embedding 函数实现为直接抛错，任何绕过浏览器的向量化都会失败。

## 3. seekdb 使用

- 接入：`seekdb` npm SDK 1.4.0 嵌入式模式（`path`），原生运行时 `@seekdb/js-bindings`。
- 集合：`dimension=384`、`distance=cosine`、全文索引分词器 `ngram`（`SEEPDB_FULLTEXT_ANALYZER` 可切换）。
- 写入：`collection.upsert({ids, documents, embeddings, metadatas})`，每批 64 条。
- 索引刷新：写入后调用 `collection.refresh_index()`；**刷新完成才算可检索**，耗时单独计量并在界面显示。接口 `POST /api/refresh` 也可单独触发。
- 检索：`collection.hybridSearch({query: {whereDocument: {$contains: q}}, knn: {...}, rank: {rrf: {rankConstant}}, nResults})`，两路候选的融合（RRF）**在库内完成**，客户端不获取两路结果再拼接；向量分支与全文分支各取 `k×4`（下限 20、上限 100）个候选。
- RRF 常量：默认 `rankConstant = 1`（见 5.4 的对照），可用 `SEEPDB_RRF_CONSTANT` 覆盖。
- 计数：`GET /api/stats` 返回集合段数，界面在导入/刷新/切集合后刷新该值。

## 4. 完整流程

1. 页面加载 → 模型在浏览器内初始化（WebGPU/FP16，降级则 WASM/INT8）。
2. 选择文件或点「载入示例语料」（服务端 `GET /api/corpus` 返回 `data/corpus/` 全部 60 个文件）。
3. 前端切分 → 每 16 段向量化一次 → 每 64 段写一批（`refresh:false`），全部写完后调用一次索引刷新。进度条与状态行逐步更新，导入大语料不会一次性驻留内存。
4. 文档 ID 由「文件名 + 段落序号」生成稳定值：重复导入同一文件是覆盖，导入新文件是增量追加（实测：同 ID 重导 `total` 不变，新增文件 `total` +1）。
5. 输入查询 → 本地生成查询向量 → `POST /api/search`（`mode=hybrid|vector|fulltext`）→ 按 seekdb 返回顺序渲染结果。
6. 指标面板记录：模型加载（含预热）、文档向量化（含段/秒）、写入、索引刷新、查询向量化、seekdb 检索、端到端。

## 5. 实测结果

环境：Windows 11 + Edge（headless，WebGPU 可用）；服务运行于 WSL2 Ubuntu（Node 22）；语料 60 段；查询 24 条（12 条语义、4 条数值、8 条标识符，见 `bench/queries.mjs`）；k=5；每个配置重复 5 次取中位数。原始数据：`bench/results/matrix.json`。

### 5.1 主表（同一设备、同一语料、同一查询集）

| 配置 | 模型体积 | 向量化吞吐 | seekdb 检索延迟 | 端到端查询延迟 | MRR@5 | R@1 | R@5 | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 量化前基线（FP32 + WebGPU） | 90.39 MB | 1,064 段/秒（0.9 ms/段） | 4 ms | 7 ms | 0.903 | 83.3% | 100% | 0.919 |
| **FP16 + WebGPU（应用默认）** | 45.30 MB | 982 段/秒（1.0 ms/段） | 4 ms | 7 ms | 0.903 | 83.3% | 100% | 0.919 |
| INT8 + WebGPU（对照，非默认） | 22.97 MB | 92 段/秒（10.9 ms/段） | 5 ms | 8 ms | 0.951 | 91.7% | 100% | 0.955 |
| **INT8 + WASM（降级默认，4 线程）** | 22.97 MB | 220 段/秒（4.5 ms/段） | 4 ms | 7 ms | 0.951 | 91.7% | 100% | 0.955 |

两个对照都只改一个变量：FP32→FP16 固定 WebGPU；WebGPU→WASM 固定 INT8。

### 5.2 结论一：INT8 在 WebGPU 上是负优化

同一语料、同一会话内，每 60 段耗时（5 次）：

| 精度 + 后端 | 各次耗时（ms） | 中位 |
|---|---|---:|
| FP32 + WebGPU | 238, 56, 56, 59, 55 | 58 ms |
| FP16 + WebGPU | 198, 68, 61, 58, 58 | 61 ms |
| INT8 + WebGPU | 858, 664, 634, 640, 653 | 640 ms |
| INT8 + WASM（4 线程） | 306, 283, 259, 271, 273 | 271 ms |

INT8 权重在 WebGPU 上要先反量化再送 GPU，ORT 实测慢约 **11×**，查询向量化也从 7 ms 涨到 90 ms。因此 WebGPU 路径默认 **FP16**：体积减半、速度与 FP32 持平；INT8 只在 WASM 路径使用（体积最小，且 4 线程下比单线程快约 5 倍）。这是本项目的取舍依据，不是通用结论。

### 5.3 结论二：量化对检索质量的影响

FP32 与 FP16 名次完全一致；INT8 的 MRR/nDCG 反而略高（0.951 vs 0.903）。但这不是“量化提升质量”，而是**并列打破的随机性**：48 条归档记录除代码外完全相同，向量分支无法区分，量化噪声改变了 RRF 并列项的顺序。四种配置 **R@5 均为 100%**，差异只出现在第 2/3 名的先后。结论：在本评测集上量化没有可测的质量损失，但也不应把 INT8 的小幅领先解读为质量提升。

### 5.4 结论三：RRF 常量对并列项敏感

同一 60 段语料、24 条查询、INT8 向量，只改 `rankConstant`：

| rankConstant | MRR@5 | R@1 | R@5 |
|---|---:|---:|---:|
| 60（RRF 默认） | 0.876 | 20/24 | 23/24 |
| **1（应用默认）** | **0.951** | **22/24** | **24/24** |

`rankWindowSize`（20/100）在本题无影响。常量取 1 时，各分支的第一名权重更大，BM25 精确命中 `CODE-0012` 这类查询不再被向量分支的并列项稀释。该值可用 `SEEPDB_RRF_CONSTANT` 调整，也可在单次请求里用 `POST /api/search` 的 `rankConstant` 字段临时覆盖——对照只需改这一个变量。

### 5.5 分阶段计时（60 段，默认配置）

| 阶段 | FP16 + WebGPU | INT8 + WASM |
|---|---:|---:|
| 模型加载（含预热） | 1,170 ms（预热 191 ms） | 747 ms（预热 40 ms） |
| 文档向量化（60 段，首批含编译） | 61 ms（首批 198 ms） | 273 ms（首批 306 ms） |
| 写入 seekdb（60 段） | 563 ms | 555 ms |
| 索引刷新 | 301 ms | 301 ms |
| 查询向量化 | 7 ms | 3 ms |
| seekdb 检索（服务端计时） | 4 ms | 4 ms |
| 端到端（提交 → 渲染） | 7 ms | 7 ms |

首次与预热后：首次查询 15 ms（FP16/WEBGPU）、13 ms（INT8/WASM），预热后均为 7 ms；模型加载时间是首次会话的最大项，权重本地化后稳定在 0.7–1.2 s。

### 5.6 降级路径验证

`bench/e2e.mjs` 在屏蔽 `navigator.gpu` 的页面里逐项检查：徽标变为 `WASM`、顶部横幅给出原因、示例语料导入 + 索引刷新成功、查询返回结果。当前结果 **8/8 通过**。

## 6. 优化点

- **按后端的精度策略**：WebGPU/FP16、WASM/INT8（依据 5.2 的实测），以及 FP16 失败时回退 FP32、再回退 WASM 的顺序。
- **流式导入**：16 段一批推理、64 段一批写入，最后统一刷新索引；大语料不占满内存，写入与向量化重叠。
- **稳定文档 ID**：重复导入幂等，新增文件增量追加。
- **显式索引刷新**：`refresh_index()` 后计数可查，界面显示刷新耗时与集合段数。
- **多线程 WASM**：本地权重 + COOP/COEP → `SharedArrayBuffer` → 4 线程，吞吐约 5×。
- **RRF 调参**：`rankConstant=1` 使 R@5 从 23/24 提升到 24/24。
- **候选池**：两路各取 `k×4`（≥20）候选再融合，避免融合窗口过窄。
- **本地资源**：`npm run models` 把三份权重放到本服务，`/ort` 提供 ORT wasm，页面不访问公共 CDN。

## 7. 复现

```bash
npm install
npm run setup       # seekdb 原生运行时（约 54 MB）
npm run models      # FP32/FP16/INT8 三份权重到 public/models（约 159 MB）
npm run build
npm start           # http://127.0.0.1:8787

# 另开终端（需要浏览器；CHROME_PATH 可指定 Chrome/Edge）
npm run bench:matrix   # 5.1 的四配置对照 → bench/results/matrix.json
npm run bench:e2e      # 浏览器端验收（导入、检索、全文、降级）8/8
```

两处下载都有明确失败行为：`npm run setup` 用 `curl -C -` 断点续传并校验产物，失败即 `exit 1`；`npm run models` 同样在缺文件时才会联网。

## 8. 已知局限

- 语料只有 60 段、24 条标注查询，指标接近上限；标注意义上的“相关文档”多为单条，nDCG 采用二值/三级混合口径。
- 48 条归档记录高度重复，RRF 并列项的顺序受浮点噪声影响，第 2/3 名的差异不应过度解读。
- 主表在单机（Windows 11 + Edge、WSL2）测得，绝对值随设备变化；跨设备比较应重新运行 `bench:matrix`。
- `bench/matrix.mjs` 依赖 `puppeteer-core`（devDependency）与本机浏览器，判题环境若没有浏览器可跳过该脚本，应用本身不依赖它。