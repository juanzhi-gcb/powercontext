# seekdb × 阶跃星辰：端侧 Embedding + 混合检索

本题应用在 [`stepfun/`](stepfun/) 目录。仓库根目录提供同名入口，可直接在根上执行：

```bash
npm install     # 同时安装 stepfun/ 的依赖
npm start       # 构建前端并启动服务，打开 http://127.0.0.1:8787
```

| 路径 | 内容 |
|---|---|
| `stepfun/web/` | 前端（Vite + TypeScript，Transformers.js 端侧推理，WebGPU → WASM 自动降级） |
| `stepfun/server/` | Express API + seekdb 嵌入式客户端 |
| `stepfun/data/corpus/` | 演示语料 |
| `stepfun/TECH_NOTE.md` | 一页技术说明（量化前后体积与检索质量、分阶段计时、降级验证） |
| `stepfun/README.md` | 环境要求、完整启动步骤、环境变量 |

首次运行需联网下载两样资源：seekdb 原生运行时（约 54 MB，由 `npm run setup` 完成）与模型权重（约 113 MB，可跳过，浏览器会直接从 Hugging Face 加载）。细节与镜像变量见 [`stepfun/README.md`](stepfun/README.md)。

其余目录（`dify/`、`gaode/`、`minimax/`、`qoder/`）属于同一赛道的其它题目，与本题无关。