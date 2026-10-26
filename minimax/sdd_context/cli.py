"""Command line entry point for the SDD context module.

    python -m sdd_context.cli <command> [...]

Every command is stateless: engineering material lives in seekdb/OceanBase and
task progress lives in PowerContext, so a new process sees the same data.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from .config import Settings
from .db import Database, QueryLog, init_schema, open_database
from .ingest import ingest
from .minimax import (
    ChangeSet,
    MinimaxClient,
    MinimaxError,
    apply_changes,
    build_messages,
    load_replay,
    save_transcript,
    write_patch,
)
from .runner import TestRun, node_ids_from_context, run_pytest
from .select import (
    attach_excerpts,
    build_context,
    context_for_prompt,
    latest_run_id,
    make_task_id,
)
from .state import PowerContextState, RequestRecorder

STATE_FILE_DIR = ".sdd_state"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _database(settings: Settings) -> Iterator[Database]:
    sink: list[QueryLog] = []
    with open_database(settings, log_sink=sink) as database:
        try:
            yield database
        finally:
            _write_query_log(settings, sink)


def _write_query_log(settings: Settings, sink: list[QueryLog]) -> None:
    if not sink:
        return
    path = settings.evidence_dir / "logs" / "db_queries.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with path.open("a", encoding="utf-8") as handle:
        for entry in sink:
            handle.write(
                json.dumps(
                    {
                        "at": stamp,
                        "statement": entry.statement[:400],
                        "params": _stringify(entry.params),
                        "rows": entry.rows,
                        "elapsed_ms": entry.elapsed_ms,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _stringify(params: Any) -> Any:
    if params is None:
        return None
    if isinstance(params, tuple):
        return [_stringify(item) for item in params]
    if isinstance(params, (str, int, float, bool)) or params is None:
        value = str(params)
        return value[:200] + ("..." if len(value) > 200 else "")
    return str(type(params))


def _state_client(settings: Settings) -> PowerContextState:
    recorder = RequestRecorder(settings.evidence_dir / "powercontext" / "requests.jsonl")
    return PowerContextState(
        settings.powercontext_url,
        token=settings.powercontext_token,
        recorder=recorder,
    )


def _scope_for(settings: Settings, client: PowerContextState, task_id: str, task: str) -> str:
    return client.ensure_scope(
        title=f"sdd:{settings.project_id}:{task_id}",
        summary=f"SDD task {task_id}: {task[:400]}",
    )


def _context_path(settings: Settings, task_id: str) -> Path:
    return settings.workspace / STATE_FILE_DIR / f"context-{task_id}.json"


def _save_context(settings: Settings, context: dict[str, Any]) -> Path:
    path = _context_path(settings, context["task_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: value for key, value in context.items() if not key.startswith("_")}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_context(settings: Settings, task_id: str | None, task: str | None, database: Database) -> dict[str, Any]:
    if task_id:
        path = _context_path(settings, task_id)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    if not task:
        raise SystemExit("need --task or a saved context for --task-id")
    context = build_context(settings, database, task, task_id=task_id or make_task_id(task))
    return json.loads(json.dumps(context))


def _strip_private(context: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in context.items() if not key.startswith("_")}


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _state_payload(context: dict[str, Any], *, phase: str, settings: Settings) -> dict[str, Any]:
    return {
        "task_id": context["task_id"],
        "task": context["task"],
        "project_id": context["project_id"],
        "phase": phase,
        "spec_items": [item["id"] for item in context["spec_items"]],
        "code": [f"{item['source']['path']}::{item['symbol']}" for item in context["code"]],
        "tests": {
            "target": [item["node_id"] for item in context["tests"]["target"]],
            "regression": [item["node_id"] for item in context["tests"]["regression"]],
        },
        "context_file": str(_context_path(settings, context["task_id"]).relative_to(settings.workspace)),
        "completed": [],
        "pending": [
            "确认目标测试在修改前失败",
            "使用 MiniMax 生成并应用代码修改",
            "运行目标测试与回归测试",
        ],
        "verification": [],
    }


def _merge_state(previous: dict[str, Any] | None, update: dict[str, Any]) -> dict[str, Any]:
    state = dict(previous or {})
    for key, value in update.items():
        if key in ("completed", "pending", "verification") and isinstance(value, list):
            merged = list(state.get(key) or [])
            for item in value:
                if item not in merged:
                    merged.append(item)
            state[key] = merged
        else:
            state[key] = value
    return state


def _complete(state: dict[str, Any], step: str, next_step: str | None = None) -> dict[str, Any]:
    completed = list(state.get("completed") or [])
    if step not in completed:
        completed.append(step)
    pending = [item for item in (state.get("pending") or []) if item != step]
    if next_step and next_step not in pending:
        pending.append(next_step)
    state["completed"] = completed
    state["pending"] = pending
    return state


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    report: dict[str, Any] = {"version": __version__, "settings": settings.as_public_dict(), "checks": {}}
    try:
        import pylibseekdb  # noqa: F401

        report["checks"]["pylibseekdb"] = "ok"
    except ModuleNotFoundError:
        report["checks"]["pylibseekdb"] = "missing (needed for SDDCTX_DB_MODE=embedded)"
    try:
        with _database(settings) as database:
            tables = database.query("SHOW TABLES LIKE 'sdd_%'")
            docs = database.scalar("SELECT COUNT(*) AS n FROM sdd_documents") if tables else 0
        report["checks"]["database"] = {"status": "ok", "tables": len(tables), "documents": docs}
    except Exception as exc:  # noqa: BLE001
        report["checks"]["database"] = f"error: {exc}"
    client = _state_client(settings)
    report["checks"]["powercontext"] = "ok" if client.healthy() else "unreachable"
    report["checks"]["minimax_key"] = "set" if settings.minimax_api_key else "missing"
    _print_json(report)
    return 0


def cmd_init(args: argparse.Namespace, settings: Settings) -> int:
    with _database(settings) as database:
        init_schema(database, drop=args.drop)
        tables = database.query("SHOW TABLES LIKE 'sdd_%'")
    print(f"initialised {len(tables)} tables in {settings.db_mode} database")
    return 0


def cmd_ingest(args: argparse.Namespace, settings: Settings) -> int:
    with _database(settings) as database:
        report = ingest(settings, database)
        tables = database.query("SHOW TABLES LIKE 'sdd_%'")
    evidence = settings.evidence_dir / "logs" / f"ingest-{report.run_id}.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    payload = report.as_dict()
    payload["tables"] = len(tables)
    payload["evidence"] = str(evidence.relative_to(settings.workspace))
    if args.json:
        _print_json(payload)
    else:
        print(
            f"ingested specs={report.spec_docs} code={report.code_docs} tests={report.test_docs} "
            f"links={report.links} run={report.run_id}"
        )
        if report.revisions_bumped:
            print("revisions bumped: " + ", ".join(report.revisions_bumped))
        if report.removed:
            print("removed stale documents: " + ", ".join(report.removed))
    return 0


def cmd_context(args: argparse.Namespace, settings: Settings) -> int:
    task = _task_text(args)
    with _database(settings) as database:
        run_id = latest_run_id(database, settings.project_id)
        context = build_context(settings, database, task, task_id=args.task_id or make_task_id(task), run_id=run_id)
        attach_excerpts(settings, context)
    path = _save_context(settings, context)

    client = _state_client(settings)
    scope_id = _scope_for(settings, client, context["task_id"], task)
    state = client.read_state(scope_id)
    payload = _merge_state(state, _state_payload(context, phase="context_ready", settings=settings))
    payload["phase"] = "context_ready"
    payload["scope_id"] = scope_id
    payload["pending"] = [
        "确认目标测试在修改前失败",
        "使用 MiniMax 生成并应用代码修改",
        "运行目标测试与回归测试",
    ]
    client.write_state(scope_id, payload)

    result = {
        "task_id": context["task_id"],
        "scope_id": scope_id,
        "context_file": str(path.relative_to(settings.workspace)),
        "spec_items": [item["id"] for item in context["spec_items"]],
        "code": [item["symbol"] for item in context["code"]],
        "target_tests": [item["node_id"] for item in context["tests"]["target"]],
        "regression_tests": [item["node_id"] for item in context["tests"]["regression"]],
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        result["out"] = str(out)
    if args.json:
        _print_json(_strip_private(context))
    else:
        print(context_for_prompt(context))
        print("\n--- summary ---")
        _print_json(result)
    return 0


def cmd_baseline(args: argparse.Namespace, settings: Settings) -> int:
    task = _task_text(args) if (args.task or args.task_file) else None
    with _database(settings) as database:
        context = _load_context(settings, args.task_id, task, database)
    targets = node_ids_from_context(context, "target")
    run = run_pytest(settings, "target-baseline", targets)

    client = _state_client(settings)
    scope_id = _scope_for(settings, client, context["task_id"], context["task"])
    state = client.read_state(scope_id) or _state_payload(context, phase="context_ready", settings=settings)
    state = dict(state)
    state["phase"] = "baseline_failed" if not run.ok else "baseline_unexpectedly_passed"
    state["verification"] = list(state.get("verification") or []) + [run.as_dict()]
    state = _complete(state, "确认目标测试在修改前失败", "使用 MiniMax 生成并应用代码修改")
    client.write_state(scope_id, state)
    client.milestone(scope_id, f"baseline exit={run.exit_code} failed={run.failed} log={run.log_path}")

    _print_json({"task_id": context["task_id"], "run": run.as_dict(), "log_tail": run.output[-1500:]})
    expected_fail = args.expect == "fail"
    return 0 if (not run.ok) == expected_fail else 1


def cmd_patch(args: argparse.Namespace, settings: Settings) -> int:
    task = _task_text(args) if (args.task or args.task_file) else None
    with _database(settings) as database:
        context = _load_context(settings, args.task_id, task, database)
    attach_excerpts(settings, context)

    allowed = {item["source"]["path"] for item in context["code"]}
    if args.replay:
        changes = load_replay(Path(args.replay))
        response = None
        print(f"replaying {args.replay}")
    else:
        client = MinimaxClient(settings)
        messages = build_messages(settings, context, instruction=args.instruction)
        response = client.chat(messages, temperature=args.temperature, max_tokens=args.max_tokens)
        changes = ChangeSet.from_content(response.content)

    applied = apply_changes(settings, changes, allowed)
    patch_path = write_patch(settings, context["task_id"], applied)
    transcript = None
    if response is not None:
        transcript = save_transcript(settings, context["task_id"], response, changes, applied)

    pc = _state_client(settings)
    scope_id = _scope_for(settings, pc, context["task_id"], context["task"])
    state = pc.read_state(scope_id) or _state_payload(context, phase="context_ready", settings=settings)
    state = dict(state)
    state["phase"] = "patched"
    state["changes"] = {
        "patch": str(patch_path.relative_to(settings.workspace)),
        "summary": changes.summary,
        "files": [item["path"] for item in applied["files"]],
        "spec_coverage": changes.spec_coverage,
        "transcript": None if transcript is None else str(transcript.relative_to(settings.workspace)),
    }
    state = _complete(state, "使用 MiniMax 生成并应用代码修改", "运行目标测试与回归测试")
    pc.write_state(scope_id, state)
    pc.milestone(scope_id, f"applied change: {changes.summary[:300]}")

    result = {
        "task_id": context["task_id"],
        "summary": changes.summary,
        "files": [item["path"] for item in applied["files"]],
        "spec_coverage": changes.spec_coverage,
        "patch": str(patch_path.relative_to(settings.workspace)),
        "transcript": None if transcript is None else str(transcript.relative_to(settings.workspace)),
        "diff": "".join(item["diff"] for item in applied["files"]),
    }
    _print_json(result)
    return 0


def cmd_verify(args: argparse.Namespace, settings: Settings) -> int:
    client = _state_client(settings)
    scope_id = args.scope_id or client.find_scope(f"sdd:{settings.project_id}:{args.task_id}")
    if not scope_id:
        raise SystemExit(f"no PowerContext scope for task {args.task_id}")
    state = client.read_state(scope_id)
    if state is None:
        raise SystemExit(f"no PowerContext state for scope {scope_id}")

    if state.get("tests"):
        targets = state["tests"]["target"]
        regressions = state["tests"]["regression"]
    else:
        with _database(settings) as database:
            context = _load_context(settings, state.get("task_id"), state.get("task"), database)
        targets = node_ids_from_context(context, "target")
        regressions = node_ids_from_context(context, "regression")

    target_run = run_pytest(settings, "target", targets)
    regression_run = run_pytest(settings, "regression", regressions)
    ok = target_run.ok and regression_run.ok

    state = dict(state)
    state["phase"] = "verified" if ok else "verification_failed"
    state["verification"] = list(state.get("verification") or []) + [
        target_run.as_dict(),
        regression_run.as_dict(),
    ]
    state = _complete(state, "运行目标测试与回归测试")
    client.write_state(scope_id, state)
    client.milestone(
        scope_id,
        f"verification target_exit={target_run.exit_code} regression_exit={regression_run.exit_code}",
    )

    _print_json(
        {
            "task_id": state.get("task_id"),
            "scope_id": scope_id,
            "verification": state["verification"],
            "passed": ok,
            "target_log": target_run.log_path,
            "regression_log": regression_run.log_path,
        }
    )
    return 0 if ok else 1


def cmd_status(args: argparse.Namespace, settings: Settings) -> int:
    client = _state_client(settings)
    scope_id = args.scope_id or client.find_scope(f"sdd:{settings.project_id}:{args.task_id}")
    if not scope_id:
        print(f"no PowerContext scope for task {args.task_id}")
        return 1
    state = client.read_state(scope_id)
    if state is None:
        print(f"no state recorded in PowerContext for {scope_id}")
        return 1
    if args.json:
        _print_json(state)
        return 0
    print(f"task:        {state.get('task_id')}")
    print(f"scope:       {scope_id}")
    print(f"phase:       {state.get('phase')}")
    print(f"updated:     {state.get('updated_at')} (seq {state.get('seq')})")
    print("specs:       " + ", ".join(state.get("spec_items") or []))
    print("completed:   " + ("; ".join(state.get("completed") or []) or "-"))
    print("pending:     " + ("; ".join(state.get("pending") or []) or "-"))
    print("verification:")
    for item in state.get("verification") or []:
        print(
            f"  - {item.get('scope')}: exit={item.get('exit_code')} "
            f"passed={item.get('passed')} failed={item.get('failed')} log={item.get('log_path')}"
        )
    if state.get("changes"):
        print(f"patch:       {state['changes'].get('patch')}")
    return 0


def cmd_test(args: argparse.Namespace, settings: Settings) -> int:
    run = run_pytest(settings, args.scope, args.node or [])
    _print_json({"run": run.as_dict(), "output_tail": run.output[-2000:]})
    return run.exit_code


def cmd_reset_demo(args: argparse.Namespace, settings: Settings) -> int:
    before = settings.evidence_dir / "code" / "before"
    if not before.is_dir():
        raise SystemExit(f"missing pristine snapshot at {before}")
    restored: list[str] = []
    for source in before.rglob("*.py"):
        relative = source.relative_to(before)
        target = settings.demo_project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        restored.append(str(relative))
    _print_json({"restored": restored})
    return 0


def cmd_snapshot(args: argparse.Namespace, settings: Settings) -> int:
    label = args.label
    destination = settings.evidence_dir / "code" / label
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in sorted(settings.demo_project.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(settings.demo_project)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        copied.append(str(relative))
    _print_json({"label": label, "files": copied, "destination": str(destination.relative_to(settings.workspace))})
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def _task_text(args: argparse.Namespace) -> str:
    if getattr(args, "task_file", None):
        return Path(args.task_file).read_text(encoding="utf-8").strip()
    if getattr(args, "task", None):
        return args.task.strip()
    raise SystemExit("--task or --task-file is required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sddctx", description="规格驱动开发上下文模块")
    parser.add_argument("--workspace", help="minimax/ workspace directory", default=None)
    parser.add_argument("--version", action="version", version=f"sddctx {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="检查依赖、数据库和 PowerContext 连通性")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("init", help="创建数据库表")
    p.add_argument("--drop", action="store_true", help="先删除已有表")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("ingest", help="导入规格/代码/测试到 seekdb/OceanBase")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("context", help="为任务生成上下文包")
    p.add_argument("--task")
    p.add_argument("--task-file")
    p.add_argument("--task-id")
    p.add_argument("--out")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("baseline", help="运行目标测试（修改前应失败）")
    p.add_argument("--task")
    p.add_argument("--task-file")
    p.add_argument("--task-id")
    p.add_argument("--expect", choices=["fail", "pass"], default="fail")
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("patch", help="调用 MiniMax 生成并应用代码修改")
    p.add_argument("--task")
    p.add_argument("--task-file")
    p.add_argument("--task-id")
    p.add_argument("--instruction", default="")
    p.add_argument("--replay", help="使用已记录的 MiniMax 响应，无需 API key")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--max-tokens", type=int, default=6000)
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser("verify", help="运行目标与回归测试")
    p.add_argument("--task-id", required=True)
    p.add_argument("--scope-id")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="从 PowerContext 读取任务状态")
    p.add_argument("--task-id", required=True)
    p.add_argument("--scope-id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("test", help="直接运行指定测试节点")
    p.add_argument("--scope", default="manual")
    p.add_argument("--node", action="append", required=True)
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("snapshot", help="保存业务工程当前代码快照")
    p.add_argument("--label", required=True)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("reset-demo", help="恢复业务工程到修改前快照")
    p.set_defaults(func=cmd_reset_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load(args.workspace)
    started = time.time()
    exit_code = 1
    try:
        exit_code = args.func(args, settings)
        return exit_code
    except (MinimaxError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        _record_command(settings, args, exit_code, time.time() - started)


def _record_command(settings: Settings, args: argparse.Namespace, exit_code: int, duration: float) -> None:
    path = settings.evidence_dir / "logs" / "commands.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "argv": ["sddctx", *sys.argv[1:]] if args else [],
                        "command": getattr(args, "command", None),
                        "exit_code": exit_code,
                        "duration_s": round(duration, 2),
                        "python": sys.version.split()[0],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:  # noqa: BLE001 - evidence logging must never mask the command
        traceback.print_exc()


if __name__ == "__main__":
    raise SystemExit(main())