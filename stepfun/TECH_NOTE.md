# seekdb × 阶跃星辰：端侧知识库技术说明

## 模型与量化

模型为 Apache-2.0 的 `Xenova/all-MiniLM-L6-v2`，revision `751bff37182d3f1213fa05d7196b954e230abad9`，384维、mean池化、L2归一化。直接采用发布者的 FP32、FP16、INT8 ONNX，`npm run models` 下载固定版本并校验 SHA-256（见 `model.json`），浏览器 `dtype` 选择文件。FP16/INT8 压缩比分别为 2.00×/3.93×。

## 端侧运行与 seekdb

Transformers.js 4.3.1 / ONNX Runtime Web 1.31.0-dev：显式 WebGPU + FP16，初始化失败自动 WASM + INT8，页面徽标与横幅说明后端；本地模型配合 COOP/COEP 提供4线程。文档和查询均在浏览器推理；服务端 embedding 函数直接抛错。seekdb SDK/原生绑定1.4.0，嵌入式集合保存 ID、原文、向量和元数据，cosine、ngram；`hybridSearch` 在库内进行 RRF（常量1），不在客户端融合。

## 五次实测与质量

2026-10-28：Win11、Ryzen 9 8945HX、32GB、RTX 5060 Laptop（驱动582.05）、Edge 156.0.4314.42 headless；服务为 WSL2 Ubuntu 26.04、Node22。固定60段、24个标注查询、k=5；向量化批16，写入批64。

| 配置 | ONNX体积 | 段/秒 | seekdb | 端到端 | MRR / R@1 / R@5 / nDCG@5 |
|---|---:|---:|---:|---:|---|
| FP32 + WebGPU | 90.39 MB | 616.5 | 7 ms | 27 ms | 0.903 / 83.3% / 100% / 0.919 |
| FP16 + WebGPU | 45.30 MB | 530.8 | 7 ms | 28 ms | 0.903 / 83.3% / 100% / 0.919 |
| INT8 + WebGPU | 22.97 MB | 51.6 | 8 ms | 113 ms | 0.951 / 91.7% / 100% / 0.955 |
| INT8 + WASM/4线程 | 22.97 MB | 77.9 | 7 ms | 21 ms | 0.951 / 91.7% / 100% / 0.955 |

中位数：每配置5次语料向量化/写入/刷新；查询为24条×5轮。端到端从向量化前到页面结果渲染及绘制机会，均走应用同一查询函数。FP16质量与基线一致、体积减半，吞吐下降约14%；INT8的名次小幅变化不解读为质量提升。WebGPU下FP16端到端28ms，INT8为113ms。

## 状态、阶段计时与复现

稳定“文件名+chunk序号”ID配合upsert保证重导幂等，导入结束一次刷新后可检索；集合名随请求传递，切换清理结果并重读计数。FP16实测：首次本地HTTP ONNX传输264ms；加载2231ms（含预热465ms）；60段向量化113ms、写入965ms、刷新302ms；首次查询141ms，后续28ms。加载只采样一次，首次公网下载未测；所有原始样本、传输观测和限制见 `BENCHMARK_REPORT.md` / `bench/results/matrix.json`。

Linux安装系统库后，在仓库根目录 `npm ci` → `npm run setup` → `npm run models` → `npm start`，访问localhost:8787。`npm run bench:e2e` 本轮13/13（含幂等、增量向量/混合检索、集合隔离、无WebGPU降级）；`npm run bench:matrix` 复现主表。平台仓库与分支填写见 `SUBMISSION.md`。
