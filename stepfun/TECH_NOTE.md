# 技术说明：端侧 Embedding + seekdb 混合检索

## 1. 模型与量化

| 项 | 值 |
|---|---|
| 模型 | `Xenova/all-MiniLM-L6-v2`（MIT，Hugging Face 公开仓库） |
| 输出维度 | 384，`mean` 池化 + L2 归一化 |
| 量化方案 | ONNX INT8（Transformers.js `dtype: "q8"`） |

模型体积按同一口径统计 ONNX 权重文件（`Content-Length` 实测）：

| 精度 | 文件 | 体积（字节） | 压缩比（相对 fp32） |
|---|---|---:|---:|
| fp32 | `onnx/model.onnx` | 90,387,606 | 1.00× |
| fp16 | `onnx/model_fp16.onnx` | 45,297,825 | 2.00× |
| **int8（实际使用）** | `onnx/model_quantized.onnx` | **22,972,370** | **3.93×** |

模型加载即按 int8 权重下载，浏览器端不做二次量化。

## 2. 端侧运行

- 运行时：Transformers.js 4.3.1（ONNX Runtime Web），模型与推理都在页面内。
- 后端选择：先尝试 `device: "webgpu"`；构造失败或 `navigator.gpu` 缺失时自动改用 `device: "wasm"`，界面徽标显示当前后端，鼠标悬停显示降级原因。
- 预热：加载完成后先跑一次单句推理，避免第一批真实请求承担 kernel 编译开销。
- 服务端**不参与推理**：集合绑定的 embedding 函数被实现为直接抛错，任何绕过浏览器的向量化都会失败。

## 3. seekdb 使用

- 接入方式：`seekdb` npm SDK 1.4.0，嵌入式模式（`path` 参数），原生运行时 `@seekdb/js-bindings`。
- 集合：名称 `documents`，`dimension=384`，`distance=cosine`，同时启用稠密向量索引与全文索引。
- 写入：浏览器算好向量后调用 `collection.add({ids, documents, embeddings, metadatas})`，按 64 条一批提交，原文与 `source`/`chunk` 元数据同批写入。
- 检索：`collection.hybridSearch({knn: {queryEmbeddings, queryTexts}, nResults, include})`。**两路候选的融合由 seekdb 内部完成**（RRF），客户端不获取两路结果再拼接。
- 增量与刷新：每次导入只需提交新增段落；SDK 在写入后刷新索引，写入完成的段落立即参与检索（实测导入后立刻检索可命中）。

## 4. 实测结果

环境：Windows 11 + Edge（headless，WebGPU 可用）、WSL2 Ubuntu（seekdb 嵌入式，Node 20.19）、语料 8 段、查询 3 条。

| 阶段 | 实测 |
|---|---:|
| 模型加载 + 预热（首次，含 23 MB 下载） | 132,232 ms |
| 文档向量化（8 段，批大小 16） | 545 ms |
| 写入 seekdb（8 段） | 247 ms |
| 查询向量化（单条） | 104 ms |
| **seekdb 混合检索（服务端计时）** | **3 ms** |
| 端到端（点击检索 → 结果渲染） | 153 ms |

检索质量（同一语料，混合检索）：3 条标注查询的首条结果**全部命中目标文档**（`02-hybrid-search`、`04-webgpu`、`07-quantisation-tradeoff`）。

## 5. 未完成与复现说明

以下两项**尚未取得实测数字**，不写入结论：

1. **int8 vs fp32 的检索质量对比**：fp32 基线模型（90 MB）在本次网络环境下多次下载中断，浏览器侧对比未能跑完。
2. **WASM 后端的性能数字**：同样受模型下载影响，未取得可信数据。

复现命令（网络稳定时执行）：

```bash
npm run build && npm start           # 后端 + 静态页面
# 另起终端：node <repo>/bench.mjs     # 在同一浏览器内依次加载 q8 与 fp32，
                                      # 对同一查询集计算目标文档排名与 MRR
```

其中 `bench.mjs` 通过页面暴露的 `window.__kb.Embedder` 驱动，两个精度走完全相同的代码路径；质量指标为「目标文档在余弦排序中的名次」与 MRR。

## 6. 优化点

- **批处理**：向量化按 16 条一批、写入按 64 条一批，减少每次调用的固定开销。
- **预热**：模型加载后立即推理一次，把编译开销移出首个用户请求。
- **单进程托管**：生产模式由同一个 Node 进程同时提供静态页面与 API，省掉前端独立部署。
- **原生库加载**：Linux 上以 `LD_PRELOAD` 预加载 `libseekdb.so`，规避 Node `dlopen` 无法满足静态 TLS 预留的问题；数据库在启动时显式创建，连接不自动建库。