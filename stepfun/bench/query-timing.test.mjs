import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const source = fs.readFileSync(new URL("../web/src/query-timing.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { measureQuery } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

test("end-to-end time encloses asynchronous inference, retrieval and rendering", async (context) => {
  let now = 0;
  context.mock.method(performance, "now", () => now);
  const result = await measureQuery(
    async () => { await Promise.resolve(); now += 35; return [1, 0]; },
    async (vector) => { assert.deepEqual(vector, [1, 0]); now += 7; return { hits: ["document"] }; },
    async (response) => { assert.deepEqual(response.hits, ["document"]); await Promise.resolve(); now += 5; },
  );
  assert.equal(result.queryEmbedMs, 35);
  assert.equal(result.endToEndMs, 47);
  assert.deepEqual(result.response.hits, ["document"]);
});

test("fulltext passes no vector and includes rendering in its end-to-end time", async (context) => {
  let now = 0;
  context.mock.method(performance, "now", () => now);
  const result = await measureQuery(
    null,
    async (vector) => { assert.equal(vector, null); now += 7; return "fulltext hit"; },
    () => { now += 5; },
  );
  assert.equal(result.queryEmbedMs, 0);
  assert.equal(result.endToEndMs, 12);
});

test("a rendering failure cannot be reported as a completed query", async () => {
  await assert.rejects(
    measureQuery(null, async () => "hit", async () => { throw new Error("render failed"); }),
    /render failed/,
  );
});
