# Template provenance

Adapted from the user-provided Codex Sites 0.1.66 `sites-building/templates/vinext-starter`.

The UI catalog, hooks, utilities, Tailwind stylesheet and vendored Shadcn CSS originate from that template. The vendored CSS license is preserved beside the file. Dependencies retain their own licenses.

Qoder adaptations replace Vinext/Next server rendering and Cloudflare configuration with a Vite static build; remove D1/Drizzle, R2 and ChatGPT authentication scaffolding; set Shadcn to client rendering; and make the toast component use its system theme without a Next theme provider. The Function example reuses Qoder Sites' credential-free handler. No upstream hosting, auth or resource configuration is copied into generated projects.

`src/assets/archivist.png` is an original character illustration drawn by a teammate for this competition entry and used with permission. The archive scene, lamp, counter and receipt are CSS/SVG authored in this repository; no remote image assets are loaded.

## External archive records

`src/public-archive.json` also contains 215 records imported on 2026-10-28 from three public sources. They keep their own `source`, `source_url`, `original_doi`, `replication_doi`, `license` and `retrieved_at` fields; each record links back to a DOI or source page as locatable evidence. Their `historical_decision` is always `null`: these are external replication and retraction outcomes, not verdicts issued by this archive, and they are excluded from the nine curated research-line prechecks.

- **ReScience C** (40 records, `https://github.com/ReScience/articles`). Replication and reproduction articles with abstracts; editorials and letters excluded. Article-level license: CC BY 4.0.
- **FORRT Replication Database / FReD** (125 records, `https://github.com/forrtproject/FReD`). One row per `fred_id`, limited to reported failed or mixed replications whose source text includes an outcome quote. The R package is MIT-licensed; the data license is not declared upstream.
- **Retraction Watch** (50 records, `https://gitlab.com/crossref/retraction-watch-data`). Computer-science/data-science retractions with a DOI and a stated scientific reason. No license file is published upstream; records are used as public bibliographic notices with a link to the notice and the retracted paper.

Source counts, licenses and retrieval dates are stored in the `sources` block of the generated corpus. The records were selected and normalized by `scripts/import-external-records.py` into `../examples/external-records.json`, then merged by `scripts/build-public-archive.py`.

