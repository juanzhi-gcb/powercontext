import { env, pipeline, type FeatureExtractionPipeline } from "@huggingface/transformers";

export type Backend = "webgpu" | "wasm";
export type Dtype = "q8" | "fp32" | "fp16";
/** "auto" picks fp16 on WebGPU and int8 on WASM; both were measured on this corpus. */
export type RequestedDtype = Dtype | "auto";

export const MODEL_ID = "Xenova/all-MiniLM-L6-v2";

// Everything runs from the browser cache when the page is a secure context (https or
// localhost). Plain-HTTP origins do not expose the Cache API, so the model is simply
// re-fetched in those environments instead of failing to load.
env.allowLocalModels = true;
env.localModelPath = "/models/";
env.allowRemoteModels = true;
// Serve the ONNX Runtime wasm assets from this application instead of a CDN, so inference
// works on a machine without access to public CDNs.
const wasmOptions = env.backends.onnx.wasm;
if (wasmOptions) wasmOptions.wasmPaths = "/ort/";
env.useBrowserCache = typeof caches !== "undefined";

export interface LoadOptions {
  /** Pin the backend instead of probing WebGPU first. Used by the fallback test. */
  forceBackend?: Backend | null;
  /** Thread count for the WASM path; ORT only honours >1 when the page is cross-origin isolated. */
  threads?: number;
}

export class Embedder {
  backend: Backend = "wasm";
  dtype: Dtype = "q8";
  loadMs = 0;
  warmupMs = 0;
  threads = 1;
  crossOriginIsolated = false;
  fallbackReason: string | null = null;

  private pipe: FeatureExtractionPipeline | null = null;

  async load(requested: RequestedDtype = "auto", options: LoadOptions = {}): Promise<Backend> {
    const started = performance.now();
    this.pipe = null;
    this.backend = "wasm";
    this.dtype = "q8";
    this.fallbackReason = null;
    this.crossOriginIsolated = typeof crossOriginIsolated !== "undefined" && crossOriginIsolated;
    this.threads = Math.max(1, options.threads ?? Math.min(4, navigator.hardwareConcurrency || 1));
    // Multithreaded WASM needs SharedArrayBuffer; asking for more threads without isolation
    // makes ORT print a warning and fall back to one thread, so only raise it when usable.
    if (wasmOptions) wasmOptions.numThreads = this.crossOriginIsolated ? this.threads : 1;

    const attach = async (backend: Backend, dtype: Dtype): Promise<FeatureExtractionPipeline> => {
      const created = await pipeline("feature-extraction", MODEL_ID, { device: backend, dtype });
      this.pipe = created;
      this.backend = backend;
      this.dtype = dtype;
      return created;
    };

    let pipe: FeatureExtractionPipeline | null = null;
    const force = options.forceBackend ?? null;
    const hasGpu = typeof navigator !== "undefined" && "gpu" in navigator && Boolean(navigator.gpu);
    if (force === "wasm") {
      this.fallbackReason = "backend=wasm 由查询参数强制指定（用于复现降级路径）";
    } else if (hasGpu) {
      // On WebGPU, int8 pays a dequantisation cost per operator (measured 11x slower than
      // fp16 here), so the GPU path defaults to fp16 and only falls back to int8 on WASM.
      const order: Dtype[] = requested === "auto" ? ["fp16", "fp32"] : [requested];
      for (const dtype of order) {
        try {
          pipe = await attach("webgpu", dtype);
          break;
        } catch (error) {
          this.fallbackReason = error instanceof Error ? error.message : String(error);
          console.warn(`WebGPU ${dtype} unavailable, trying the next option:`, this.fallbackReason);
        }
      }
    } else {
      this.fallbackReason = "浏览器未暴露 navigator.gpu";
    }

    if (!pipe) {
      const wasmDtype: Dtype = requested === "auto" || requested === "fp16" ? "q8" : requested;
      pipe = await attach("wasm", wasmDtype);
    }

    // Warm up once so the first real batch is not paying kernel compilation.
    const warmStart = performance.now();
    await pipe(["warm up"], { pooling: "mean", normalize: true });
    this.warmupMs = performance.now() - warmStart;
    this.loadMs = performance.now() - started;
    return this.backend;
  }

  /** One-line description of the runtime actually in use, for the UI and the report. */
  describe(): string {
    const parts = [this.backend.toUpperCase(), this.dtype.toUpperCase()];
    if (this.backend === "wasm") {
      parts.push(`${this.crossOriginIsolated ? this.threads : 1} thread(s)`);
    }
    return parts.join(" · ");
  }

  async embed(
    texts: string[],
    batchSize = 16,
    onProgress?: (done: number, total: number, elapsedMs: number) => void,
  ): Promise<number[][]> {
    if (!this.pipe) throw new Error("model is not loaded");
    const started = performance.now();
    const vectors: number[][] = [];
    for (let start = 0; start < texts.length; start += batchSize) {
      const batch = texts.slice(start, start + batchSize);
      const tensor = await this.pipe(batch, { pooling: "mean", normalize: true });
      vectors.push(...(tensor.tolist() as number[][]));
      onProgress?.(Math.min(start + batch.length, texts.length), texts.length, performance.now() - started);
    }
    return vectors;
  }
}