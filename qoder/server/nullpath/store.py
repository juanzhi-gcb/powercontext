from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymysql
from pymysql.connections import Connection

from .config import Settings
from .models import (
    ArchiveCard,
    AttemptCreate,
    DecisionCreate,
    EvaluationRunCreate,
    ExperimentCreate,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def mysql_time(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    decoded = dict(row)
    for key, value in decoded.items():
        if key in {
            "assumptions",
            "competing_explanations",
            "context_refs",
            "report",
            "evidence_ids",
        } and isinstance(value, str):
            decoded[key] = json.loads(value)
        elif isinstance(value, datetime):
            decoded[key] = value.replace(tzinfo=UTC).isoformat()
    decoded.pop("embedding", None)
    return decoded


class SeekDBStore:
    def __init__(self, settings: Settings, schema_path: Path | None = None) -> None:
        self.settings = settings
        self.schema_path = schema_path or Path(__file__).resolve().parents[2] / "db" / "schema.sql"

    def connect(self, database: bool = True) -> Connection:
        return pymysql.connect(
            host=self.settings.seekdb_host,
            port=self.settings.seekdb_port,
            user=self.settings.seekdb_user,
            password=self.settings.seekdb_password,
            database=self.settings.seekdb_database if database else None,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=20,
            write_timeout=20,
        )

    def init_schema(self) -> None:
        with self.connect(database=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.settings.seekdb_database}` "
                    "DEFAULT CHARACTER SET utf8mb4"
                )
            connection.commit()
        statements = [
            part.strip() for part in self.schema_path.read_text().split(";") if part.strip()
        ]
        with self.connect() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()

    def health(self) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok, VERSION() AS version")
            row = cursor.fetchone()
        return {
            "status": "ready",
            "version": row["version"],
            "database": self.settings.seekdb_database,
        }

    def create_attempt(
        self,
        attempt: AttemptCreate,
        embedding: list[float],
        *,
        attempt_id: str | None = None,
        historical_decision: str | None = None,
    ) -> dict[str, Any]:
        attempt_id = attempt_id or str(uuid.uuid4())
        now = utcnow()
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO attempts (
                      id, title, idea, mechanism, task, domain, failure_condition,
                      assumptions, competing_explanations, differentiator, embedding,
                      historical_decision, available_at, created_at, gpu_count, data_ready,
                      checkpoint_ready, pilot_hours, storage_gb, baseline_first
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s
                    )
                    """,
                    (
                        attempt_id,
                        attempt.title,
                        attempt.idea,
                        attempt.mechanism,
                        attempt.task,
                        attempt.domain,
                        attempt.failure_condition,
                        json_value(attempt.assumptions),
                        json_value(attempt.competing_explanations),
                        attempt.differentiator,
                        json_value(embedding),
                        historical_decision,
                        mysql_time(attempt.available_at),
                        mysql_time(now),
                        attempt.gpu_count,
                        attempt.data_ready,
                        attempt.checkpoint_ready,
                        attempt.pilot_hours,
                        attempt.storage_gb,
                        attempt.baseline_first,
                    ),
                )
            connection.commit()
        return self.get_attempt(attempt_id)

    def import_card(
        self, card: ArchiveCard, embedding: list[float], *, attempt_id: str | None = None
    ) -> dict[str, Any]:
        attempt = self.create_attempt(
            card.attempt,
            embedding,
            attempt_id=attempt_id,
            historical_decision=card.historical_decision.value
            if card.historical_decision
            else None,
        )
        for item in card.evidence:
            self.add_evidence(attempt["id"], item.model_dump())
        return attempt

    def update_scope(self, attempt_id: str, task: str, domain: str) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE attempts SET task = %s, domain = %s WHERE id = %s",
                (task, domain, attempt_id),
            )
            connection.commit()

    def add_evidence(self, attempt_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO evidence (
                      id, attempt_id, source_type, title, locator, excerpt, stance,
                      published_at, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        evidence["id"],
                        attempt_id,
                        evidence["source_type"],
                        evidence["title"],
                        evidence["locator"],
                        evidence["excerpt"],
                        evidence["stance"],
                        mysql_time(evidence["published_at"]),
                        mysql_time(utcnow()),
                    ),
                )
            connection.commit()
        return self.get_evidence_by_id(evidence["id"])

    def get_attempt(self, attempt_id: str) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM attempts WHERE id = %s", (attempt_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Attempt not found: {attempt_id}")
        return decode_row(row)

    def has_attempt(self, attempt_id: str) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM attempts WHERE id = %s", (attempt_id,))
            return cursor.fetchone() is not None

    def list_attempts(self) -> list[dict[str, Any]]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, title, task, domain, historical_decision, available_at, created_at "
                "FROM attempts ORDER BY created_at DESC LIMIT 200"
            )
            rows = cursor.fetchall()
        return [decode_row(row) for row in rows]

    # source- is the stable namespace created by import_sources; seeded demo cards share the
    # source_type values but are not part of the user's library.
    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.id AS attempt_id, a.title, a.task, a.domain, a.available_at, "
                "COUNT(e.id) AS evidence_count, MIN(e.source_type) AS source_type, "
                "MIN(e.locator) AS locator, MIN(e.published_at) AS published_at, "
                "MAX(e.created_at) AS imported_at "
                "FROM attempts a JOIN evidence e ON e.attempt_id = a.id "
                "WHERE a.id LIKE 'source-%' AND e.source_type IN ('paper', 'log', 'code_audit') "
                "GROUP BY a.id, a.title, a.task, a.domain, a.available_at "
                "ORDER BY imported_at DESC LIMIT 200"
            )
            rows = cursor.fetchall()
        return [decode_row(row) for row in rows]

    def list_source_documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.id AS attempt_id, a.title, a.task, a.domain, a.available_at, "
                "a.mechanism, a.embedding, e.id AS evidence_id, e.source_type, "
                "e.locator, e.excerpt, e.published_at "
                "FROM attempts a JOIN evidence e ON e.attempt_id = a.id "
                "WHERE a.id LIKE 'source-%' AND e.source_type IN ('paper', 'log', 'code_audit') "
                "ORDER BY a.available_at, a.id, e.published_at"
            )
            rows = cursor.fetchall()
        documents: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = decode_row({key: value for key, value in row.items() if key != "embedding"})
            document = documents.setdefault(
                item["attempt_id"],
                {
                    "attempt_id": item["attempt_id"],
                    "title": item["title"],
                    "task": item["task"],
                    "domain": item["domain"],
                    "available_at": item["available_at"],
                    "mechanism": item["mechanism"],
                    "embedding": json.loads(row["embedding"])
                    if isinstance(row["embedding"], str)
                    else list(row["embedding"]),
                    "evidence_ids": [],
                    "locators": [],
                    "source_types": [],
                    "excerpts": [],
                },
            )
            document["evidence_ids"].append(item["evidence_id"])
            document["locators"].append(item["locator"])
            document["source_types"].append(item["source_type"])
            document["excerpts"].append(item["excerpt"])
        return list(documents.values())

    def get_evidence_by_id(self, evidence_id: str) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM evidence WHERE id = %s", (evidence_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Evidence not found: {evidence_id}")
        return decode_row(row)

    def evidence_for_attempts(
        self, attempt_ids: Iterable[str], cutoff: datetime
    ) -> dict[str, list[dict[str, Any]]]:
        ids = list(dict.fromkeys(attempt_ids))
        if not ids:
            return {}
        placeholders = ",".join(["%s"] * len(ids))
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM evidence WHERE attempt_id IN ({placeholders}) "
                "AND published_at <= %s ORDER BY published_at",
                (*ids, mysql_time(cutoff)),
            )
            rows = cursor.fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {attempt_id: [] for attempt_id in ids}
        for row in rows:
            item = decode_row(row)
            grouped[item["attempt_id"]].append(item)
        return grouped

    def hybrid_retrieve(
        self,
        attempt: dict[str, Any],
        embedding: list[float],
        cutoff: datetime,
        limit: int = 6,
        *,
        channels: tuple[str, ...] = ("vector", "fts"),
        match_all: bool = False,
    ) -> list[dict[str, Any]]:
        conditions = ["status = 'active'", "id <> %s", "available_at <= %s"]
        shared = (attempt["id"], mysql_time(cutoff))
        if not match_all:
            conditions.append("(task = %s OR domain = %s)")
            shared = (*shared, attempt["task"], attempt["domain"])
        eligibility = " AND ".join(conditions)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, title, mechanism, differentiator, task, domain, "
                "historical_decision, available_at, l2_distance(embedding, %s) AS vector_distance "
                f"FROM attempts WHERE {eligibility} ORDER BY vector_distance LIMIT 8",
                (json_value(embedding), *shared),
            )
            vector_rows = cursor.fetchall()
            cursor.execute(
                "SELECT id, title, mechanism, differentiator, task, domain, "
                "historical_decision, available_at, "
                "MATCH(idea, mechanism, failure_condition) AGAINST(%s) AS fts_score "
                f"FROM attempts WHERE MATCH(idea, mechanism, failure_condition) AGAINST(%s) "
                f"AND {eligibility} ORDER BY fts_score DESC LIMIT 8",
                (attempt["mechanism"], attempt["mechanism"], *shared),
            )
            fts_rows = cursor.fetchall()

        merged: dict[str, dict[str, Any]] = {}
        for channel, rows in (("vector", vector_rows), ("fts", fts_rows)):
            if channel not in channels:
                continue
            weight = 0.6 if channel == "vector" else 0.4
            for rank, row in enumerate(rows, start=1):
                item = merged.setdefault(
                    row["id"],
                    {
                        **decode_row(row),
                        "vector_distance": None,
                        "fts_score": None,
                        "vector_rank": None,
                        "fts_rank": None,
                        "fused_score": 0.0,
                    },
                )
                item[f"{channel}_rank"] = rank
                item["fused_score"] += weight / (60 + rank)
                if channel == "vector":
                    item["vector_distance"] = float(row["vector_distance"])
                else:
                    item["fts_score"] = float(row["fts_score"])
        return sorted(merged.values(), key=lambda item: item["fused_score"], reverse=True)[:limit]

    def snapshot_hash(self, cutoff: datetime) -> tuple[str, dict[str, int]]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, available_at FROM attempts WHERE available_at <= %s ORDER BY id",
                (mysql_time(cutoff),),
            )
            attempts = cursor.fetchall()
            cursor.execute(
                "SELECT id, published_at FROM evidence WHERE published_at <= %s ORDER BY id",
                (mysql_time(cutoff),),
            )
            evidence = cursor.fetchall()
        canonical = json_value(
            {
                "attempts": [[row["id"], str(row["available_at"])] for row in attempts],
                "evidence": [[row["id"], str(row["published_at"])] for row in evidence],
            }
        )
        return hashlib.sha256(canonical.encode()).hexdigest(), {
            "attempts": len(attempts),
            "evidence": len(evidence),
        }

    def save_evaluation(
        self,
        attempt_id: str,
        request: EvaluationRunCreate,
        report: dict[str, Any],
        *,
        snapshot_hash: str,
        context_refs: list[dict[str, Any]],
        replay_of: str | None = None,
    ) -> dict[str, Any]:
        run_id = report["id"]
        now = utcnow()
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO evaluation_runs (
                      id, attempt_id, cutoff, snapshot_hash, model_version, embedding_version,
                      rules_version, context_refs, machine_decision, reason_code, report,
                      replay_of, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        attempt_id,
                        mysql_time(request.cutoff),
                        snapshot_hash,
                        report["versions"]["model"],
                        report["versions"]["embedding"],
                        report["versions"]["rules"],
                        json_value(context_refs),
                        report["machine_decision"],
                        report["reason_code"],
                        json_value(report),
                        replay_of,
                        mysql_time(now),
                    ),
                )
                for comparison in report["comparisons"]:
                    cursor.execute(
                        """
                        INSERT INTO comparisons (
                          id, run_id, historical_attempt_id, vector_distance, fts_score,
                          fused_score, mechanism_difference, evidence_ids, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            run_id,
                            comparison["attempt_id"],
                            comparison["vector_distance"],
                            comparison["fts_score"],
                            comparison["fused_score"],
                            comparison["mechanism_difference"],
                            json_value(comparison["evidence_ids"]),
                            mysql_time(now),
                        ),
                    )
                for check in report["checks"]:
                    cursor.execute(
                        """
                        INSERT INTO check_results (
                          id, run_id, check_name, status, reason_code, detail,
                          evidence_ids, checker_version, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            run_id,
                            check["name"],
                            check["status"],
                            check["reason_code"],
                            check["detail"],
                            json_value(check["evidence_ids"]),
                            report["versions"]["rules"],
                            mysql_time(now),
                        ),
                    )
            connection.commit()
        return report

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM evaluation_runs WHERE id = %s", (run_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Evaluation run not found: {run_id}")
        decoded = decode_row(row)
        report = decoded["report"]
        report["snapshot_hash"] = decoded["snapshot_hash"]
        report["context_refs"] = decoded["context_refs"] or []
        report["replay_of"] = decoded["replay_of"]
        report["created_at"] = decoded["created_at"]
        return report

    def list_runs(self) -> list[dict[str, Any]]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, attempt_id, cutoff, machine_decision, reason_code, replay_of, created_at "
                "FROM evaluation_runs ORDER BY created_at DESC LIMIT 100"
            )
            rows = cursor.fetchall()
        return [decode_row(row) for row in rows]

    def add_decision(self, decision: DecisionCreate) -> dict[str, Any]:
        run = self.get_run(decision.run_id)
        decision_id = str(uuid.uuid4())
        now = utcnow()
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO decisions (
                      id, run_id, attempt_id, decision, reason, restart_conditions,
                      reviewer_alias, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        decision_id,
                        decision.run_id,
                        run["attempt_id"],
                        decision.decision.value,
                        decision.reason,
                        decision.restart_conditions,
                        decision.reviewer_alias,
                        mysql_time(now),
                    ),
                )
            connection.commit()
        return {
            "id": decision_id,
            **decision.model_dump(mode="json"),
            "created_at": now.isoformat(),
        }

    def add_experiment(self, experiment: ExperimentCreate) -> dict[str, Any]:
        self.get_attempt(experiment.attempt_id)
        experiment_id = str(uuid.uuid4())
        now = utcnow()
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO experiments (
                      id, attempt_id, hypothesis, intervention, control, metric, threshold,
                      observed_result, outcome, stop_triggered, ran_at, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        experiment_id,
                        experiment.attempt_id,
                        experiment.hypothesis,
                        experiment.intervention,
                        experiment.control,
                        experiment.metric,
                        experiment.threshold,
                        experiment.observed_result,
                        experiment.outcome,
                        experiment.stop_triggered,
                        mysql_time(experiment.ran_at),
                        mysql_time(now),
                    ),
                )
                evidence_id = f"exp-{experiment_id}"
                cursor.execute(
                    """
                    INSERT INTO evidence (
                      id, attempt_id, source_type, title, locator, excerpt, stance,
                      published_at, created_at
                    ) VALUES (%s, %s, 'experiment', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        evidence_id,
                        experiment.attempt_id,
                        f"Experiment: {experiment.hypothesis[:200]}",
                        f"nullpath://experiments/{experiment_id}",
                        experiment.observed_result,
                        "limits" if experiment.outcome == "inconclusive" else experiment.outcome,
                        mysql_time(experiment.ran_at),
                        mysql_time(now),
                    ),
                )
            connection.commit()
        return {
            "id": experiment_id,
            "evidence_id": evidence_id,
            **experiment.model_dump(mode="json"),
            "created_at": now.isoformat(),
        }

    def lineage(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.get_attempt(attempt_id)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM evidence WHERE attempt_id = %s ORDER BY published_at", (attempt_id,)
            )
            evidence = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM evaluation_runs WHERE attempt_id = %s ORDER BY created_at",
                (attempt_id,),
            )
            runs = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM decisions WHERE attempt_id = %s ORDER BY created_at", (attempt_id,)
            )
            decisions = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM experiments WHERE attempt_id = %s ORDER BY ran_at", (attempt_id,)
            )
            experiments = cursor.fetchall()
        return {
            "attempt": attempt,
            "evidence": [decode_row(row) for row in evidence],
            "runs": [decode_row(row) for row in runs],
            "decisions": [decode_row(row) for row in decisions],
            "experiments": [decode_row(row) for row in experiments],
        }
