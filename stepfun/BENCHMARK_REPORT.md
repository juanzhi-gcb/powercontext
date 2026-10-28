# 实验与复现记录

## 固定环境与数据

- 执行时间（UTC）：`2026-10-28T00:25:21.303Z`；北京时间2026-10-28。
- 客户端：Windows 11 build 26200，AMD Ryzen 9 8945HX，32逻辑CPU、约32GB内存；NVIDIA GeForce RTX 5060 Laptop GPU，驱动582.05。浏览器报告的适配器为NVIDIA Blackwell，设备名另由本机 `nvidia-smi` 核对。
- 浏览器：`Edg/156.0.4314.42` headless；精确UA及适配器信息保存在每个配置的 `environment`。启动参数为 `--no-sandbox --disable-dev-shm-usage --enable-unsafe-webgpu`。
- 服务端：WSL2 Ubuntu 26.04 x64，Node22.0.0；基准驱动：Windows Node22.20.0。Windows localhost:18880通过TCP转发访问WSL:18879，浏览器保持安全localhost上下文。
- 依赖：Transformers.js4.3.1、ONNX Runtime Web `1.31.0-dev.20260914-8d85527a0`、seekdb及@seekdb/js-bindings1.4.0、Vite6.4.5；精确依赖树见锁文件。
- 语料：`data/corpus/` 60段；查询：`bench/queries.mjs` 24条标注查询；k=5；向量化批16，写入批64。四配置使用相同设备、语料、查询和数据库参数。
- seekdb：嵌入式、dimension384、cosine、ngram全文索引、RRF常量1、候选数max(k×4,20)，上限100；rankWindow保持SDK默认。本轮没有改变RRF参数来生成主表。

## 模型来源、版本与量化获取

[Xenova/all-MiniLM-L6-v2固定版本](https://huggingface.co/Xenova/all-MiniLM-L6-v2/tree/751bff37182d3f1213fa05d7196b954e230abad9)，Apache-2.0。直接采用发布者提供的FP32、FP16和INT8量化ONNX文件，不训练模型，也不在服务器推理。

`npm run models` 从manifest所记revision获取config、tokenizer及三份ONNX。ONNX字节数和SHA-256必须与 `model.json` 匹配；已有文件也校验，损坏文件重新下载。`HF_BASE`可指向提供相同内容的镜像，哈希规则不变。浏览器pipeline使用同一个revision，WebGPU默认FP16、WASM默认INT8，FP16初始化失败可尝试FP32，再自动降级WASM。比较时强制后端并核对实际后端，不能把自动回退结果记为WebGPU结果。

| 文件 | 实测字节数 | 相对FP32压缩比 |
|---|---:|---:|
| `model.onnx` | 90,387,606 | 1.00× |
| `model_fp16.onnx` | 45,297,825 | 2.00× |
| `model_quantized.onnx` | 22,972,370 | 3.93× |

体积来自 `/api/model-info` 对实际下发文件的字节统计，只比较ONNX；三种精度共享的tokenizer/config未计入任一行，口径一致。

## 性能与检索质量主表

| 配置 | ONNX体积 | 段/秒 | seekdb | 端到端 | MRR / R@1 / R@5 / nDCG@5 |
|---|---:|---:|---:|---:|---|
| FP32 + WebGPU | 90.39 MB | 616.5 | 7 ms | 27 ms | 0.903 / 83.3% / 100% / 0.919 |
| FP16 + WebGPU | 45.30 MB | 530.8 | 7 ms | 28 ms | 0.903 / 83.3% / 100% / 0.919 |
| INT8 + WebGPU | 22.97 MB | 51.6 | 8 ms | 113 ms | 0.951 / 91.7% / 100% / 0.955 |
| INT8 + WASM/4线程 | 22.97 MB | 77.9 | 7 ms | 21 ms | 0.951 / 91.7% / 100% / 0.955 |

每配置文档向量化5次取中位；写入5次、索引刷新5次分别取中位。每配置查询24条×5轮，共120条原始计时样本，所有样本的中位数用于主表。每轮均计算MRR@5、R@1、R@5及nDCG@5，质量列取五轮指标的中位数。nDCG相关性等级由 `gradeFor` 定义；当前每条查询的标注相关文件为单条，不宣称代表开放领域质量。

原始结果为 `bench/results/matrix.json`（schemaVersion2），包含 `raw.embedRuns`、`raw.writeRuns`、`raw.refreshRuns`、`raw.queryRuns`、`raw.ranksByRun`、`qualityRuns` 及浏览器环境；不只保留最快一次或最后一轮质量结果。

## 分阶段计时与首次请求

| 配置 | ONNX本地HTTP传输 | 加载含预热 | 预热 | 60段向量化 | 写入 | 刷新 | 查询向量化 | 首次查询端到端 | 后续端到端 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FP32 + WebGPU | 564 ms | 3486 ms | 927 ms | 97 ms | 969 ms | 302 ms | 11 ms | 206 ms | 27 ms |
| FP16 + WebGPU | 264 ms | 2231 ms | 465 ms | 113 ms | 965 ms | 302 ms | 12 ms | 141 ms | 28 ms |
| INT8 + WebGPU | 182 ms | 2408 ms | 741 ms | 1163 ms | 1080 ms | 402 ms | 97 ms | 144 ms | 113 ms |
| INT8 + WASM/4线程 | 125 ms | 1355 ms | 79 ms | 770 ms | 893 ms | 302 ms | 7 ms | 50 ms | 21 ms |

加载含预热为每配置一个全新浏览器profile的单次采样，不称作五次中位数。ONNX传输列是同源本地HTTP文件请求的Resource Timing duration，不是首次公网Hugging Face下载耗时；权重已在服务端本地。tokenizer/config及其观测字节数与耗时保存在 `raw.modelRequests`。并发请求的duration不能直接相加当总下载墙钟时间。

加载计时覆盖pipeline初始化、资源获取与预热，预热单列但属于加载总时间；首次查询和随后120条查询的中位数分开。首次查询是在文档向量化及索引写入后发出的首条查询，因此不等于模型完全未经预热的冷启动。首次公网权重下载、native运行时从零联网下载均未作为本轮性能数据。

端到端由页面 `runQuery` 调用 `measureQuery`：从查询embedding之前开始，经过seekdb HTTP请求、真实结果DOM渲染与两次requestAnimationFrame后停止。UI与benchmark调用同一个函数。服务端检索耗时是实际数据库调用的墙钟时间；写入耗时由应用API计时；索引刷新单独计时。端到端不是各阶段中位数之和。

## 优化与取舍

- 固定WebGPU时，FP32→FP16将体积减半，质量指标一致；本轮吞吐616.5→530.8段/秒，下降约14%，端到端27→28ms。没有把吞吐描述为完全持平。
- 固定WebGPU时，INT8吞吐51.6段/秒、端到端113ms，FP16吞吐530.8段/秒、端到端28ms，因此应用默认FP16。固定INT8切换到WASM，吞吐77.9段/秒、端到端21ms。本轮WASM跨源隔离并启用4线程，未重新测单线程对照，不报告新的多线程加速倍数。
- FP32/FP16质量相同；INT8的MRR和R@1略高。48条归档记录高度相似，精度可改变向量候选与RRF并列顺序，变化也涉及第一名；R@5均为100%，不能把小样本差异解读为量化普遍提升质量。
- 流式导入按16段推理、64段写入，完成后统一刷新；稳定ID配合upsert。连续导入和切换集合由真实浏览器验收覆盖。

## 功能与状态验收

`npm run bench:e2e` 本轮13/13，结果见 `bench/results/e2e.json`：WebGPU/FP16、60段导入与刷新、段数、CODE-0021首位、各阶段指标、全文无向量、端到端计时、重导成功且总数不变、新文件向量检索、新文件混合检索、集合隔离与恢复、屏蔽navigator.gpu时的降级横幅、WASM检索。每次验收独立集合，避免之前的测试数据影响结果。

`npm test` 的3个计时回归测试验证异步推理/检索/渲染都计时、全文没有向量化、渲染失败不报告成功；类型检查与构建也实际运行。服务端embedding函数抛错，存储与融合使用真实seekdb，不以测试向量或内存检索替代浏览器端到端验收。

## 复现

先按README配置Linux系统库。在仓库根目录执行：

```bash
npm ci
npm run setup
npm run models
npm start
```

另开终端执行 `npm test`、`npm run typecheck`、`npm run bench:e2e`、`npm run bench:matrix`。`CHROME_PATH`指定Chrome/Edge，`KB_URL`指定应用，`BENCH_REPEATS`默认5；四配置顺序固定。任一后端不匹配或配置失败时矩阵返回非零退出码。

`TECH_NOTE.md`为一页摘要源文件，`npm --prefix stepfun run note:pdf`生成HTML与A4 PDF。提交仓库与分支填写见SUBMISSION。此处本地检查不代表赛事平台已成功完成测评。
