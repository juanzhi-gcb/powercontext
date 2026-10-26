import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FulltextIndexConfig, Schema, SeekdbAdminClient, SeekdbClient } from "seekdb";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

const PORT = Number(process.env.PORT ?? 8787);
const DIMENSION = Number(process.env.EMBED_DIMENSION ?? 384);
const DB_PATH = process.env.SEEPDB_PATH ?? path.join(root, "seekdb-data", "kb.db");
const DB_NAME = process.env.SEEPDB_DATABASE ?? "kb";
const COLLECTION = process.env.SEEPDB_COLLECTION ?? "documents";
const FULLTEXT_ANALYZER = process.env.SEEPDB_FULLTEXT_ANALYZER ?? "ngram";
const ADD_BATCH = Number(process.env.SEEPDB_ADD_BATCH ?? 64);

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

async function openCollection() {
  const admin = new SeekdbAdminClient({ path: DB_PATH });
  await admin.createDatabase(DB_NAME);
  await admin.close();

  const client = new SeekdbClient({ path: DB_PATH, database: DB_NAME });
  let collection;
  try {
    collection = await client.getCollection({ name: COLLECTION, embeddingFunction: browserEmbedding });
  } catch {
    try {
      // The default analyzer splits "CODE-0007" into generic words and digits, which makes
      // exact-token queries indistinguishable. The ngram analyzer indexes character n-grams
      // so such identifiers stay matchable.
      const schema = new Schema({ fulltextIndex: new FulltextIndexConfig(FULLTEXT_ANALYZER) });
      collection = await client.createCollection({
        name: COLLECTION,
        dimension: DIMENSION,
        distance: "cosine",
        schema,
        embeddingFunction: browserEmbedding,
      });
    } catch (error) {
      console.error("schema with analyzer rejected, falling back to the default:", error?.message ?? error);
      collection = await client.createCollection({
        name: COLLECTION,
        dimension: DIMENSION,
        distance: "cosine",
        embeddingFunction: browserEmbedding,
      });
    }
  }
  return { client, collection };
}

const { client, collection } = await openCollection();
const app = express();
app.use(express.json({ limit: "64mb" }));

app.get("/api/health", async (_request, response) => {
  let documents = null;
  try {
    const rows = await client.execute(`SELECT COUNT(*) AS total FROM \`${COLLECTION}\``);
    documents = Number(rows?.[0]?.total ?? 0);
  } catch {
    documents = null;
  }
  response.json({
    ok: true,
    database: DB_NAME,
    collection: COLLECTION,
    dimension: DIMENSION,
    documents,
  });
});

app.post("/api/import", async (request, response) => {
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
  response.json({ written, ms: performance.now() - started });
});

app.post("/api/search", async (request, response) => {
  const query = request.body?.query;
  const embedding = request.body?.embedding;
  const k = Math.min(Math.max(Number(request.body?.k ?? 5), 1), 50);
  if (typeof query !== "string" || query.trim() === "" || !Array.isArray(embedding)) {
    response.status(400).json({ error: "query and embedding are required" });
    return;
  }

  const started = performance.now();
  const mode = String(request.body?.mode ?? "hybrid");
  const include = ["documents", "metadatas", "distances"];
  let result;
  if (mode === "vector") {
    result = await collection.query({ queryEmbeddings: [embedding], nResults: k, include });
  } else if (mode === "fts") {
    // Only the keyword branch participates, so the collection never asks the embedding
    // function for a vector.
    result = await collection.hybridSearch({ knn: { queryTexts: query, nResults: k }, nResults: k, include });
  } else {
    // The full-text branch is expressed as a document filter ($contains -> MATCH ...
    // AGAINST); passing queryTexts under knn only vectorises text and never builds it.
    result = await collection.hybridSearch({
      query: { whereDocument: { $contains: query }, nResults: k },
      knn: { queryEmbeddings: [embedding], nResults: k },
      rank: { rrf: {} },
      nResults: k,
      include,
    });
  }
  const isNested = Array.isArray(result.ids?.[0]);
  const ids = (isNested ? result.ids[0] : result.ids) ?? [];
  const documents = (isNested ? result.documents?.[0] : result.documents) ?? [];
  const metadatas = (isNested ? result.metadatas?.[0] : result.metadatas) ?? [];
  const distances = (isNested ? result.distances?.[0] : result.distances) ?? [];

  response.json({
    ms: performance.now() - started,
    hits: ids.map((id, index) => ({
      id,
      text: documents[index] ?? "",
      metadata: metadatas[index] ?? {},
      distance: distances[index] ?? null,
    })),
  });
});

app.post("/api/reset", async (_request, response) => {
  await collection.delete();
  const recreated = await client.createCollection({
    name: COLLECTION,
    dimension: DIMENSION,
    distance: "cosine",
    embeddingFunction: browserEmbedding,
  });
  Object.assign(collection, recreated);
  response.json({ ok: true });
});

// onnxruntime-web ships its wasm loaders in node_modules; serving them here removes the
// CDN dependency of the browser runtime.
app.use("/ort", express.static(path.join(root, "node_modules", "onnxruntime-web", "dist")));
// Models downloaded by scripts/fetch-models.sh are served from here so the browser does
// not have to re-fetch weights from a remote host on every fresh profile.
app.use("/models", express.static(path.join(root, "public", "models")));
app.use(express.static(path.join(root, "dist")));
app.get("*", (_request, response) => {
  response.sendFile(path.join(root, "dist", "index.html"));
});

const server = app.listen(PORT, () => {
  console.log(`seekdb mini knowledge base listening on http://127.0.0.1:${PORT}`);
  console.log(`database=${DB_PATH} collection=${COLLECTION} dimension=${DIMENSION}`);
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

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
// Express 4 does not forward rejected async handlers, and an unhandled rejection would take
// the whole embedded database process down with it.
process.on("unhandledRejection", (error) => {
  console.error("unhandled rejection", error?.message ?? error);
});