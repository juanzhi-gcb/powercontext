/**
 * Labelled evaluation set for the bundled corpus (60 chunks).
 *
 * `relevant` lists the source files that answer the query. A file that fully answers the
 * query carries weight 1 unless a second entry is present, in which case the first entry is
 * the primary answer (2) and the rest are secondary (1). Every metric in bench/matrix.mjs is
 * computed from this list, so the numbers in TECH_NOTE.md can be re-derived.
 */
export const QUERIES = [
  // Semantic questions over the eight topic documents.
  { text: "How does seekdb fuse the two retrieval branches?", relevant: ["02-hybrid-search.md"] },
  { text: "What happens when the browser has no WebGPU?", relevant: ["04-webgpu.md"] },
  { text: "How much smaller is the int8 model?", relevant: ["03-mm39-embedding.md", "07-quantisation-tradeoff.md"] },
  { text: "Which distance metric does seekdb use by default?", relevant: ["01-vector-search.md"] },
  { text: "Why is a document not searchable right after writing?", relevant: ["06-index-refresh.md"] },
  { text: "Which index structure trades recall for latency?", relevant: ["01-vector-search.md"] },
  { text: "What does reciprocal rank fusion combine?", relevant: ["02-hybrid-search.md"] },
  { text: "Which runtime executes the model when WebGPU is missing?", relevant: ["04-webgpu.md"] },
  { text: "Does BM25 reward rare query terms?", relevant: ["05-bm25.md"] },
  { text: "How does the rank window blend the two branches?", relevant: ["02-hybrid-search.md"] },
  { text: "Why keep the embedding on the user device?", relevant: ["08-browser-inference.md"] },
  { text: "Which analyser lets BM25 match numbers inside tables?", relevant: ["05-bm25.md"] },

  // Numeric questions: only the right quarterly figure answers, so exact terms matter.
  { text: "Which quarter reported 2047 million dollars?", relevant: ["11-quarterly-revenue-q3.md"] },
  { text: "Which quarter reported 1284 million dollars?", relevant: ["09-quarterly-revenue-q1.md"] },
  { text: "Revenue in the second quarter of fiscal 2022", relevant: ["10-quarterly-revenue-q2.md"] },
  { text: "Revenue in the fourth quarter of fiscal 2022", relevant: ["12-quarterly-revenue-q4.md"] },

  // Identifier questions: all 48 archived records read the same except the code, so only an
  // exact-token match (BM25 with an n-gram analyser) can distinguish them.
  { text: "Which record references CODE-0007?", relevant: ["13-record-CODE-0007.md"] },
  { text: "Which record references CODE-0012?", relevant: ["13-record-CODE-0012.md"] },
  { text: "Which record references CODE-0021?", relevant: ["13-record-CODE-0021.md"] },
  { text: "Which record references CODE-0028?", relevant: ["13-record-CODE-0028.md"] },
  { text: "Which record references CODE-0033?", relevant: ["13-record-CODE-0033.md"] },
  { text: "Which record references CODE-0042?", relevant: ["13-record-CODE-0042.md"] },
  { text: "Which record references CODE-0047?", relevant: ["13-record-CODE-0047.md"] },
  { text: "storage partition p07 record", relevant: ["13-record-CODE-0007.md"] },
];

export const CORPUS_FILES = [
  "01-vector-search.md",
  "02-hybrid-search.md",
  "03-mm39-embedding.md",
  "04-webgpu.md",
  "05-bm25.md",
  "06-index-refresh.md",
  "07-quantisation-tradeoff.md",
  "08-browser-inference.md",
  "09-quarterly-revenue-q1.md",
  "10-quarterly-revenue-q2.md",
  "11-quarterly-revenue-q3.md",
  "12-quarterly-revenue-q4.md",
  ...Array.from({ length: 48 }, (_, index) => `13-record-CODE-${String(index + 1).padStart(4, "0")}.md`),
];

/** Relevance grade for the document at `index`, given the labelled files for a query. */
export function gradeFor(relevant, file) {
  const position = relevant.indexOf(file);
  if (position === -1) return 0;
  return position === 0 && relevant.length > 1 ? 2 : 1;
}