import { env, pipeline, type FeatureExtractionPipeline } from "@huggingface/transformers";

export type Backend = "webgpu" | "wasm";
export type Dtype = "q8" | "fp32" | "fp16";

export const MODEL_ID = "Xenova/all-MiniLM-L6-v2";

// Everything runs from the browser cache when the page is a secure context (https or
// localhost). Plain-HTTP origins do not expose the Cache API, so the model is simply
// re-fetched in those environments instead of failing to load.
env.allowLocalModels = false;
env.useBrowserCache = typeof caches !== "undefined";

export class Embedder {
  backend: Backend = "wasm";
  dtype: Dtype = "q8";
  loadMs = 0;
  fallbackReason: string | null = null;

  private pipe: FeatureExtractionPipeline | null = null;

  async load(dtype: Dtype = "q8"): Promise<Backend> {
    const started = performance.now();
    this.dtype = dtype;
    this.pipe = null;
    this.backend = "wasm";
    this.fallbackReason = null;

    if (typeof navigator !== "undefined" && "gpu" in navigator && navigator.gpu) {
      try {
        this.pipe = await pipeline("feature-extraction", MODEL_ID, { device: "webgpu", dtype });
        this.backend = "webgpu";
      } catch (error) {
        this.fallbackReason = error instanceof Error ? error.message : String(error);
        console.warn("WebGPU unavailable, degrading to WASM:", this.fallbackReason);
      }
    } else {
      this.fallbackReason = "navigator.gpu is not exposed by this browser";
    }

    if (!this.pipe) {
      this.pipe = await pipeline("feature-extraction", MODEL_ID, { device: "wasm", dtype });
      this.backend = "wasm";
    }

    // Warm up once so the first real batch is not paying kernel compilation.
    await this.pipe(["warm up"], { pooling: "mean", normalize: true });
    this.loadMs = performance.now() - started;
    return this.backend;
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