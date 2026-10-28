import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FulltextIndexConfig, Schema, SeekdbAdminClient, SeekdbClient } from "seekdb";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const model = JSON.parse(fs.readFileSync(path.join(root, "model.json"), "utf8"));

const PORT = Number(process.env.PORT ?? 8787);
const DIMENSION = Number(process.env.EMBED_DIMENSION ?? 384);
const DB_PATH = process.env.SEEPDB_PATH ?? path.join(root, "seekdb-data", "kb.db");
const DB_NAME = process.env.SEEPDB_DATABASE ?? "kb";
const DEFAULT_COLLECTION = process.env.SEEPDB_COLLECTION ?? "documents";
const FULLTEXT_ANALYZER = process.env.SEEPDB_FULLTEXT_ANALYZER ?? "ngram";
const ADD_BATCH = Number(process.env.SEEPDB_ADD_BATCH ?? 64);
// RRF only sees the candidates each branch returns, so a deeper pool than the requested k
// gives the fusion something to reorder. Capped so a large k cannot ask for the whole table.
const CANDIDATE_FACTOR = Number(process.env.SEEPDB_CANDIDATE_FACTOR ?? 4);
// RRF defaults (window 60, constant 60) leave near-identical documents tied once a query
// matches several of them; the constants are env-tunable so the effect can be measured.
const RRF_WINDOW = Number(process.env.SEEPDB_RRF_WINDOW ?? 0);
const RRF_CONSTANT = Number(process.env.SEEPDB_RRF_CONSTANT ?? 1);
const CORPUS_DIR = path.join(root, "data", "corpus");
const MODELS_DIR = path.join(root, "public", "models");
const COLLECTION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_]{0,63}$/;

// The browser owns the model, so the server never embeds anything. The collection still
// requires an embedding-function handle for its schema, and this one refuses to run.
const browserEmbedding = {
  name: "browser-embedding",
  dimension: DIMENSION,
  async generate() {
    throw new Error("embedding runs in the browser; the server never vectorises");
  },
  getConfig() {
    return { provider: "browser" };
  },
};

async function bootstrap() {
  const admin = new SeekdbAdminClient({ path: DB_PATH });
  await admin.createDatabase(DB_NAME);
  await admin.close();
  return new SeekdbClient({ path: DB_PATH, database: DB_NAME });
}

// Registered before the first await: a rejected top-level await would otherwise leave the
// module half-evaluated and the process exiting with no diagnostic.
process.on("unhandledRejection", (error) => {
  console.error("unhandled rejection", error?.message ?? error);
});

let client;
try {
  client = await bootstrap();
} catch (error) {
  console.error("seekdb failed to start:", error?.message ?? error);
  console.error("if this is a fresh clone, run 'npm run setup' first to fetch the native runtime");
  process.exit(1);
}
const collections = new Map();

async function createCollection(name) {
  try {
    // The default analyzer splits "CODE-0007" into generic words and digits, which makes
    // exact-token queries indistinguishable. The ngram analyzer indexes character n-grams
    // so such identifiers stay matchable.
    const schema = new Schema({ fulltextIndex: new FulltextIndexConfig(FULLTEXT_ANALYZER) });
    return await client.createCollection({
      name,
      dimension: DIMENSION,
      distance: "cosine",
      schema,
      embeddingFunction: browserEmbedding,
    });
  } catch (error) {
    console.error(`schema with analyzer rejected for ${name}, falling back:`, error?.message ?? error);
    return client.createCollection({
      name,
      dimension: DIMENSION,
      distance: "cosine",
      embeddingFunction: browserEmbedding,
    });
  }
}

function collectionName(request) {
  const name = String(request.body?.collection ?? request.query?.collection ?? DEFAULT_COLLECTION);
  if (!COLLECTION_PATTERN.test(name)) {
    throw Object.assign(new Error(`invalid collection name: ${name}`), { status: 400 });
  }
  return name;
}

async function useCollection(request) {
  const name = collectionName(request);
  if (!collections.has(name)) {
    let collection;
    try {
      collection = await client.getCollection({ name, embeddingFunction: browserEmbedding });
    } catch {
      collection = await createCollection(name);
    }
    collections.set(name, collection);
  }
  return { name, collection: collections.get(name) };
}

/** Read a collection without creating it, so a stats probe never leaves an empty table behind. */
async function peekCollection(name) {
  if (collections.has(name)) return collections.get(name);
  try {
    const collection = await client.getCollection({ name, embeddingFunction: browserEmbedding });
    collections.set(name, collection);
    return collection;
  } catch {
    return null;
  }
}

let corpusCache = null;
function readCorpus() {
  if (corpusCache) return corpusCache;
  const names = fs
    .readdirSync(CORPUS_DIR)
    .filter((name) => /\.(md|txt)$/i.test(name))
    .sort();
  corpusCache = names.map((name) => ({ name, text: fs.readFileSync(path.join(CORPUS_DIR, name), "utf8") }));
  return corpusCache;
}

const app = express();

// Multithreaded WASM needs SharedArrayBuffer, which only a cross-origin isolated page gets.
// The headers are only safe when every asset the page loads is same-origin or CORS-enabled,
// so they are enabled once the model weights are served locally (npm run models); a fresh
// clone that still pulls weights from Hugging Face keeps working without them.
const localModels = fs.existsSync(MODELS_DIR);
if (localModels) {
  app.use((request, response, next) => {
    response.setHeader("Cross-Origin-Opener-Policy", "same-origin");
    response.setHeader("Cross-Origin-Embedder-Policy", "credentialless");
    next();
  });
}

app.use(express.json({ limit: "64mb" }));

function route(handler) {
  return (request, response) => {
    Promise.resolve(handler(request, response)).catch((error) => {
      console.error("request failed", error?.message ?? error);
      if (!response.headersSent) {
        response.status(error?.status ?? 500).json({ error: String(error?.message ?? error) });
      }
    });
  };
}

app.get("/api/health", route(async (request, response) => {
  const name = collectionName(request);
  const collection = await peekCollection(name);
  const total = collection ? await collection.count() : 0;
  response.json({
    ok: true,
    database: DB_NAME,
    defaultCollection: DEFAULT_COLLECTION,
    analyzer: FULLTEXT_ANALYZER,
    dimension: DIMENSION,
    collections: [...new Set([DEFAULT_COLLECTION, ...collections.keys()])],
    runtime: { node: process.version, platform: process.platform, architecture: process.arch },
    retrieval: { rrfConstant: RRF_CONSTANT, rrfWindow: RRF_WINDOW, candidateFactor: CANDIDATE_FACTOR },
    active: name,
    total,
    crossOriginIsolated: localModels,
  });
}));

app.get("/api/stats", route(async (request, response) => {
  const name = collectionName(request);
  const collection = await peekCollection(name);
  const total = collection ? await collection.count() : 0;
  response.json({
    collection: name,
    total,
    dimension: DIMENSION,
    analyzer: FULLTEXT_ANALYZER,
    ready: total > 0,
  });
}));

// The bundled corpus lets a reviewer exercise the full flow without preparing files, and
// gives the benchmark harness the same input the UI uses.
app.get("/api/corpus", route(async (_request, response) => {
  response.json({ files: readCorpus() });
}));

// Byte sizes of the ONNX files this server actually serves, so the size table in the report
// is measured rather than quoted. Empty when the weights are still fetched from the hub.
app.get("/api/model-info", route(async (_request, response) => {
  const onnxDir = path.join(MODELS_DIR, "Xenova", "all-MiniLM-L6-v2", "onnx");
  const files = fs.existsSync(onnxDir)
    ? fs
        .readdirSync(onnxDir)
        .filter((name) => name.endsWith(".onnx"))
        .sort()
        .map((name) => ({ name, bytes: fs.statSync(path.join(onnxDir, name)).size }))
    : [];
  response.json({ id: model.id, revision: model.revision, local: files.length > 0, files });
}));

app.post("/api/import", route(async (request, response) => {
  const items = Array.isArray(request.body?.documents) ? request.body.documents : [];
  if (items.length === 0) {
    response.status(400).json({ error: "documents must be a non-empty array" });
    return;
  }
  for (const item of items) {
    if (
      typeof item?.id !== "string" ||
      typeof item?.text !== "string" ||
      !Array.isArray(item?.embedding) ||
      item.embedding.length !== DIMENSION
    ) {
      response.status(400).json({ error: `invalid document payload: ${item?.id ?? "?"}` });
      return;
    }
  }

  const { name, collection } = await useCollection(request);
  const refresh = request.body?.refresh !== false;
  const started = performance.now();
  let written = 0;
  try {
    for (let start = 0; start < items.length; start += ADD_BATCH) {
      const batch = items.slice(start, start + ADD_BATCH);
      // upsert keeps re-importing the same document id idempotent instead of failing on a
      // duplicated primary key.
      await collection.upsert({
        ids: batch.map((item) => item.id),
        documents: batch.map((item) => item.text),
        embeddings: batch.map((item) => item.embedding),
        metadatas: batch.map((item) => item.metadata ?? {}),
      });
      written += batch.length;
    }
  } catch (error) {
    response.status(500).json({ error: `write failed: ${error?.message ?? error}` });
    return;
  }
  const ms = performance.now() - started;

  // New rows are only guaranteed to be visible to the vector index after a refresh, so the
  // import endpoint refreshes unless the caller is streaming batches and will refresh once
  // at the end.
  let refreshMs = null;
  let refreshError = null;
  if (refresh) {
    const refreshStart = performance.now();
    try {
      await collection.refresh_index();
    } catch (error) {
      refreshError = String(error?.message ?? error);
    }
    refreshMs = performance.now() - refreshStart;
  }

  const total = await collection.count();
  response.json({ collection: name, written, ms, refreshMs, refreshError, total });
}));

app.post("/api/refresh", route(async (request, response) => {
  const { name, collection } = await useCollection(request);
  const started = performance.now();
  await collection.refresh_index();
  const ms = performance.now() - started;
  response.json({ collection: name, ms, total: await collection.count() });
}));

app.post("/api/search", route(async (request, response) => {
  const query = request.body?.query;
  const embedding = request.body?.embedding ?? null;
  const mode = String(request.body?.mode ?? "hybrid");
  const k = Math.min(Math.max(Number(request.body?.k ?? 5), 1), 50);
  if (typeof query !== "string" || query.trim() === "") {
    response.status(400).json({ error: "query is required" });
    return;
  }
  if (mode !== "fulltext" && !Array.isArray(embedding)) {
    response.status(400).json({ error: "embedding is required unless mode=fulltext" });
    return;
  }
  if (!["hybrid", "vector", "fulltext"].includes(mode)) {
    response.status(400).json({ error: `unknown mode: ${mode}` });
    return;
  }

  const { name, collection } = await useCollection(request);
  const include = ["documents", "metadatas", "distances"];
  const candidates = Math.min(Math.max(k * CANDIDATE_FACTOR, 20), 100);
  const started = performance.now();
  let result;
  if (mode === "vector") {
    result = await collection.query({ queryEmbeddings: [embedding], nResults: k, include });
  } else if (mode === "fulltext") {
    // Full-text only: no vector branch, so the result is pure BM25 ordering.
    result = await collection.hybridSearch({
      query: { whereDocument: { $contains: query }, nResults: k },
      nResults: k,
      include,
    });
  } else {
    // The full-text branch is expressed as a document filter ($contains -> MATCH ...
    // AGAINST); queryTexts under knn only vectorises text and never builds it.
    const rankWindowSize = Number(request.body?.rankWindowSize ?? RRF_WINDOW);
    const rankConstant = Number(request.body?.rankConstant ?? RRF_CONSTANT);
    const rrf = {};
    if (rankWindowSize > 0) rrf.rankWindowSize = rankWindowSize;
    if (rankConstant > 0) rrf.rankConstant = rankConstant;
    result = await collection.hybridSearch({
      query: { whereDocument: { $contains: query }, nResults: candidates },
      knn: { queryEmbeddings: [embedding], nResults: candidates },
      rank: { rrf },
      nResults: k,
      include,
    });
  }
  const ms = performance.now() - started;

  const isNested = Array.isArray(result.ids?.[0]);
  const ids = (isNested ? result.ids[0] : result.ids) ?? [];
  const documents = (isNested ? result.documents?.[0] : result.documents) ?? [];
  const metadatas = (isNested ? result.metadatas?.[0] : result.metadatas) ?? [];
  const distances = (isNested ? result.distances?.[0] : result.distances) ?? [];

  response.json({
    collection: name,
    mode,
    candidates,
    ms,
    hits: ids.map((id, index) => ({
      id,
      text: documents[index] ?? "",
      metadata: metadatas[index] ?? {},
      distance: distances[index] ?? null,
    })),
  });
}));

app.post("/api/reset", route(async (request, response) => {
  const name = collectionName(request);
  collections.delete(name);
  // Collection.delete() takes document ids, not "drop the table"; the drop lives on the client.
  if (await client.hasCollection(name)) await client.deleteCollection(name);
  response.json({ ok: true, collection: name });
}));

// onnxruntime-web ships its wasm loaders in node_modules; serving them here removes the
// CDN dependency of the browser runtime.
app.use("/ort", express.static(path.join(root, "node_modules", "onnxruntime-web", "dist")));
// Models downloaded by scripts/fetch-models.sh are served from here so the browser does
// not have to re-fetch weights from a remote host on every fresh profile.
app.use("/models", express.static(MODELS_DIR));
app.use(express.static(path.join(root, "dist")));
app.get("*", (_request, response) => {
  response.sendFile(path.join(root, "dist", "index.html"));
});

const server = app.listen(PORT, () => {
  console.log(`seekdb mini knowledge base listening on http://127.0.0.1:${PORT}`);
  console.log(`database=${DB_PATH} analyzer=${FULLTEXT_ANALYZER} dimension=${DIMENSION}`);
  console.log(`cross-origin isolated headers: ${localModels ? "on (local models, WASM threads enabled)" : "off (weights from Hugging Face)"}`);
});

async function shutdown() {
  server.close();
  try {
    await client.close();
  } catch (error) {
    console.error("close failed", error?.message ?? error);
  }
  process.exit(0);
}

// Express 4 does not forward rejected async handlers, so unhandled rejections are what a
// failing request turns into once it escapes route(); they are logged from the handler
// registered at the top of this module.
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
