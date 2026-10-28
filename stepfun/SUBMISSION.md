# 阶跃星辰测评提交

题目：seekdb × 阶跃星辰，端侧 AI 推理性能优化与 seekdb 混合检索。

## 仓库和平台字段

本提交使用公开仓库 `juanzhi-gcb/powercontext`，代码可匿名克隆；平台填写仓库根地址及下面的分支和提交号。

| 字段 | 值或格式 |
|---|---|
| 提交仓库 | `https://github.com/juanzhi-gcb/powercontext` |
| 平台克隆地址 | `https://github.com/juanzhi-gcb/powercontext.git` |
| Branch | `2026-competition-ecosystem` |
| Commit | 本次推送后的完整 40 位提交号，须存在于上述仓库分支历史中 |
| 项目目录 | `stepfun` |
| 安装与启动 | 仓库根目录执行 `npm ci`、`npm start`；或在 `stepfun/` 执行相同命令 |
| 应用地址 | 默认 `http://127.0.0.1:8787`，可用 `PORT` 覆盖 |

公开仓库的克隆地址无需附带PAT。不要填写官方PR地址、GitHub的 `/tree/...` 页面地址或 `stepfun/` 子目录链接。Branch不加 `fork/`，也不填本地开发分支别名。[官方指南](https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts)对私有仓库及认证另有要求；公开访问成功不代表平台已确认提交合规或完成验收。

## 材料入口

- 一页技术说明：[TECH_NOTE.pdf](TECH_NOTE.pdf)，对应可编辑文本 [TECH_NOTE.md](TECH_NOTE.md)。
- 完整复现步骤、依赖、平台限制：[README.md](README.md)。
- 模型来源、固定 revision、ONNX 体积与 SHA-256：[model.json](model.json)。直接使用发布者的 FP32、FP16、INT8 ONNX 文件，`npm run models` 下载并校验，浏览器按精度选择文件。
- 四配置实验的环境、计时范围和全部原始样本：[BENCHMARK_REPORT.md](BENCHMARK_REPORT.md)、[bench/results/matrix.json](bench/results/matrix.json)。
- 浏览器验收结果：[bench/results/e2e.json](bench/results/e2e.json)。

## 最快复现

需要 Linux x64/arm64 的 seekdb 原生运行时环境，Windows 使用 WSL2；Linux 系统库配置见 README。

```bash
npm ci
npm run setup
npm run models
npm start
```

另开终端，在同一目录执行：

```bash
npm test
npm run typecheck
npm run bench:e2e
npm run bench:matrix
```

两个浏览器脚本需要本机 Chrome/Edge；`CHROME_PATH` 指定可执行文件，`KB_URL` 指定应用地址。`BENCH_REPEATS` 默认 5。应用的所有 embedding 都由浏览器执行；原生运行时仅负责 seekdb 存储与检索。

## 失败阶段

`git clone` 失败意味着尚未安装或启动应用。仓库权限/地址应先符合官方流程；SSL/TLS 握手错误则需查看执行克隆的机器的网络与 TLS 日志。一次本地克隆成功不能证明平台凭据、平台网络或后续应用验收都已通过。
