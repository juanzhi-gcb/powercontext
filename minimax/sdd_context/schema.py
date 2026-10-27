"""DDL for the engineering-material store.

The schema only uses MySQL 5.7 compatible syntax so it works both on an
embedded seekdb instance (``pylibseekdb``) and on an OceanBase / MySQL server.
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sdd_documents (
        doc_id      VARCHAR(255) NOT NULL,
        project_id  VARCHAR(64)  NOT NULL,
        doc_type    VARCHAR(16)  NOT NULL,
        path        VARCHAR(512) NOT NULL,
        symbol      VARCHAR(255) NULL,
        start_line  INT          NOT NULL,
        end_line    INT          NOT NULL,
        title       VARCHAR(512) NOT NULL,
        content     MEDIUMTEXT   NOT NULL,
        keywords    VARCHAR(1024) NOT NULL DEFAULT '',
        checksum    VARCHAR(64)  NOT NULL,
        revision    INT          NOT NULL DEFAULT 1,
        updated_at  DATETIME     NOT NULL,
        PRIMARY KEY (doc_id),
        KEY idx_sdd_documents_project (project_id, doc_type)
    ) DEFAULT CHARSET = utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_postings (
        term    VARCHAR(64)  NOT NULL,
        doc_id  VARCHAR(255) NOT NULL,
        tf      DECIMAL(10, 4) NOT NULL,
        PRIMARY KEY (term, doc_id),
        KEY idx_sdd_postings_doc (doc_id)
    ) DEFAULT CHARSET = utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_links (
        src_id  VARCHAR(255) NOT NULL,
        dst_id  VARCHAR(255) NOT NULL,
        kind    VARCHAR(32)  NOT NULL,
        PRIMARY KEY (src_id, dst_id, kind),
        KEY idx_sdd_links_dst (dst_id)
    ) DEFAULT CHARSET = utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_ingest_runs (
        run_id        VARCHAR(64) NOT NULL,
        project_id    VARCHAR(64) NOT NULL,
        started_at    DATETIME    NOT NULL,
        finished_at   DATETIME    NULL,
        spec_docs     INT         NOT NULL DEFAULT 0,
        code_docs     INT         NOT NULL DEFAULT 0,
        test_docs     INT         NOT NULL DEFAULT 0,
        source_digest VARCHAR(64) NOT NULL,
        PRIMARY KEY (run_id)
    ) DEFAULT CHARSET = utf8mb4
    """,
)

DROP_ORDER: tuple[str, ...] = (
    "DROP TABLE IF EXISTS sdd_links",
    "DROP TABLE IF EXISTS sdd_postings",
    "DROP TABLE IF EXISTS sdd_documents",
    "DROP TABLE IF EXISTS sdd_ingest_runs",
)
