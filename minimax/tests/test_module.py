"""Unit tests for the context module's pure parts (no database needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd_context.config import Settings
from sdd_context.ingest import parse_spec_file
from sdd_context.minimax import ChangeSet, MinimaxError, _extract_json, apply_changes
from sdd_context.select import _apply_cutoff
from sdd_context.terms import tokenize


def test_tokenizer_splits_identifiers_and_keeps_cjk_bigrams():
    terms = tokenize("min_total 金额下限")
    assert "min_total" in terms
    assert {"min", "total"} <= set(terms)
    assert "金额" in terms and "下限" in terms


def test_extract_json_accepts_code_fences_and_prose():
    payload = _extract_json('说明\n```json\n{"files": [{"path": "a.py", "content": "x"}]}\n```\n结束')
    assert payload is not None
    assert payload["files"][0]["path"] == "a.py"


def test_changeset_requires_files():
    with pytest.raises(MinimaxError):
        ChangeSet.from_content('{"summary": "empty"}')


def test_apply_changes_refuses_paths_outside_the_selection(tmp_path: Path):
    target = tmp_path / "demo_project" / "service.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    settings = Settings(workspace=tmp_path)
    changes = ChangeSet(summary="s", files=[{"path": "demo_project/other.py", "content": "x = 2\n"}])
    with pytest.raises(MinimaxError):
        apply_changes(settings, changes, {"demo_project/service.py"})


def test_apply_changes_rejects_invalid_python(tmp_path: Path):
    target = tmp_path / "service.py"
    target.write_text("x = 1\n", encoding="utf-8")
    settings = Settings(workspace=tmp_path)
    changes = ChangeSet(summary="s", files=[{"path": "service.py", "content": "def broken(:\n"}])
    with pytest.raises(MinimaxError):
        apply_changes(settings, changes, {"service.py"})


def test_apply_changes_writes_file_and_diff(tmp_path: Path):
    target = tmp_path / "service.py"
    target.write_text("x = 1\n", encoding="utf-8")
    settings = Settings(workspace=tmp_path)
    changes = ChangeSet(summary="s", files=[{"path": "service.py", "content": "x = 2\n"}])
    result = apply_changes(settings, changes, {"service.py"})
    assert target.read_text(encoding="utf-8") == "x = 2\n"
    assert "-x = 1" in result["files"][0]["diff"]


def test_cutoff_keeps_documents_relative_to_the_best_score():
    ranked = [{"score": 10.0}, {"score": 6.0}, {"score": 1.0}]
    assert [item["score"] for item in _apply_cutoff(ranked, 8)] == [10.0, 6.0]


def test_spec_parser_splits_requirement_sections(tmp_path: Path):
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "SPEC-DEMO.md").write_text(
        "---\nspec_id: SPEC-DEMO\ntitle: 演示\nkeywords: [demo]\nanchors: []\n---\n\n"
        "# SPEC-DEMO 演示\n\n## R1 第一条\n\n需求一。\n\n## R2 第二条\n\n需求二。\n",
        encoding="utf-8",
    )
    settings = Settings(workspace=tmp_path)
    docs = parse_spec_file(settings, specs / "SPEC-DEMO.md")
    assert [doc.symbol for doc in docs] == ["SPEC-DEMO#R1", "SPEC-DEMO#R2"]
    assert docs[0].content == "需求一。"
    assert docs[0].start_line == 10
    assert len(docs[0].checksum) == 64