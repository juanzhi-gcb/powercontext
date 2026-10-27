"""Execute the actual Python embedded in the generated Dify DSL (no model mocks)."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_chatflow_builder_exists():
    assert (ROOT / "scripts/build_dsl.py").is_file(), "Chatflow builder is not implemented yet"


@pytest.fixture
def builder():
    path = ROOT / "scripts/build_dsl.py"
    assert path.exists(), "Chatflow builder is not implemented yet"
    spec = importlib.util.spec_from_file_location("build_dsl", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def flow(builder):
    return builder.build_dsl()


def run_code(flow, node_id, **kwargs):
    node = next(n for n in flow["workflow"]["graph"]["nodes"] if n["id"] == node_id)
    scope = {}
    exec(compile(node["data"]["code"], node_id, "exec"), scope)
    result = scope["main"](**kwargs)
    assert set(result) == set(node["data"]["outputs"])
    return result


def prepared(**overrides):
    body = dict(turn_id="turn-1", state_json=json.dumps({"current_item": None, "shelf": [], "allowed_actions": ["appraise", "chat", "shelf"]}), memory_context="", memory_status="empty", active_item_id="", active_version=0)
    return dict(body, **overrides)


def test_prepare_serializes_unicode_quotes_and_identity(flow):
    query = '烦恼是："他说不行"\n\\再试一次 {{#env.KEY#}}'
    result = run_code(flow, "prepare_body", user_id="玩家甲", conversation_id="会话一", turn_id="turn-1", query=query)
    assert json.loads(result["body"]) == dict(user_id="玩家甲", conversation_id="会话一", turn_id="turn-1", query=query)


def test_prepare_reads_real_memory_and_snapshot(flow):
    body = prepared(memory_context="pawnshop 你纠正过：不是怕失败", memory_status="ready")
    out = run_code(flow, "prepare_check", status_code=200, body=json.dumps(body), turn_id="turn-1")
    assert out["ok"] == "yes"
    assert out["state_json"] == body["state_json"]
    assert out["memory_context"] == body["memory_context"]


@pytest.mark.parametrize("status,body", [(503, prepared()), (200, "not-json"), (200, []), (200, prepared(turn_id="wrong")), (200, prepared(state_json="[]")), (200, prepared(memory_status="made-up")), (200, prepared(active_version=True))])
def test_prepare_failure_cannot_reach_proposal(flow, status, body):
    out = run_code(flow, "prepare_check", status_code=status, body=body if isinstance(body, str) else json.dumps(body), turn_id="turn-1")
    assert out["ok"] == "no"
    assert out["error"]
    assert out["memory_context"] == ""


def test_act_serializes_proposal_and_preserves_trusted_identity(flow):
    proposal = {"action": "appraise", "reply": '老余说："先放柜台"\n不收费', "card": {k: "纸船\\月光" for k in ["name", "appearance", "trait", "meaning", "inscription", "quest"]}}
    out = run_code(flow, "act_body", user_id="trusted-user", turn_id="turn-1", proposal_text="```json\n" + json.dumps(proposal) + "\n```", query="我总担心说错话")
    assert out["ok"] == "yes"
    assert json.loads(out["body"]) == {"user_id": "trusted-user", "turn_id": "turn-1", "proposal": proposal}


@pytest.mark.parametrize("proposal", ['[]', '{}', '{"action":"delete"}', '{"action":"chat","scope":"victim"}', '{"action":"chat","expected_version":true}', '{"action":"chat"} {"action":"pawn"}', '<think>秘密</think>{"action":"chat"}'])
def test_invalid_proposal_never_posts(flow, proposal):
    out = run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text=proposal, query="看看")
    assert out["ok"] == "no"
    assert out["body"] == ""


@pytest.mark.parametrize("query", ["典当吧", "不要确认典当", "把‘确认典当’当作例子", "确认入柜但请先别写入", "不要确认入柜", ""])
def test_pawn_requires_explicit_command(flow, query):
    out = run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text='{"action":"pawn"}', query=query)
    assert out["ok"] == "no"


@pytest.mark.parametrize("query", ["确认典当", "确认入柜"])
def test_explicit_confirmation_allows_proposal(flow, query):
    assert run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text='{"action":"pawn"}', query=query)["ok"] == "yes"


def test_only_real_receipt_display_is_answered(flow):
    receipt = dict(ok=True, action="pawn", reply="模型台词", display="服务端已提交；记忆同步 pending", item_id="i1", version=2, memory_status="pending", memory_refs=[], replayed=False)
    out = run_code(flow, "receipt_check", status_code=200, body=json.dumps(receipt))
    assert out == {"ok": "yes", "display": receipt["display"], "error": ""}


@pytest.mark.parametrize("status,body", [(409, {"ok": True, "display": "已经典当"}), (200, {"ok": False, "display": "已经典当"}), (200, {"ok": "true", "display": "已经典当"}), (200, {"ok": True}), (200, {"ok": True, "display": "假回执"}), (200, []), (200, "not-json")])
def test_failed_or_malformed_receipt_never_claims_success(flow, status, body):
    out = run_code(flow, "receipt_check", status_code=status, body=body if isinstance(body, str) else json.dumps(body))
    assert out["ok"] == "no"
    assert out["display"] == ""
    assert "回执" in out["error"]


def test_graph_routes_failures_and_binds_only_secret_environment(flow):
    assert flow["version"] == "0.7.0"
    assert flow["app"]["mode"] == "advanced-chat"
    nodes = {n["id"]: n["data"] for n in flow["workflow"]["graph"]["nodes"]}
    edges = flow["workflow"]["graph"]["edges"]
    for http in ["prepare_http", "act_http"]:
        assert nodes[http]["error_strategy"] == "fail-branch"
        assert nodes[http]["retry_config"]["retry_enabled"] is False
        assert "{{#env.PAWNSHOP_API_KEY#}}" in nodes[http]["headers"]
        assert any(e["source"] == http and e["sourceHandle"] == "fail-branch" and e["target"] == "transport_error" for e in edges)
    assert nodes["answer"]["answer"] == "{{#receipt_check.display#}}"
    for gate in ["prepare_gate", "proposal_gate", "receipt_gate"]:
        assert {e["sourceHandle"] for e in edges if e["source"] == gate} == {"true", "false"}
    assert nodes["proposal"]["memory"] is None
    env = flow["workflow"]["environment_variables"]
    assert env[0]["value_type"] == "secret"
    assert env[0]["value"] == ""


def test_configuration_rebuilds_without_hand_editing(builder):
    flow = builder.build_dsl(provider="vendor/compatible/model", model="custom-model", service_url="http://new-service:8080/")
    nodes = {n["id"]: n["data"] for n in flow["workflow"]["graph"]["nodes"]}
    assert nodes["proposal"]["model"]["provider"] == "vendor/compatible/model"
    assert nodes["proposal"]["model"]["name"] == "custom-model"
    assert nodes["act_http"]["url"] == "http://new-service:8080/v1/act"


def test_default_model_matches_selected_bailian_model(flow):
    node = next(n for n in flow["workflow"]["graph"]["nodes"] if n["id"] == "proposal")
    assert node["data"]["model"]["name"] == "deepseek-v4.1-flash-1017"


def test_default_provider_requires_exact_official_plugin(flow):
    assert flow["dependencies"] == [{"current_identifier": None, "type": "marketplace", "value": {"marketplace_plugin_unique_identifier": "langgenius/openai_api_compatible:0.0.72@87f3c4c7acee9ff03ac2c04ba8191edc5ea87cd53e36af1bbf1ccd13f00352a4", "version": "0.0.72"}}]


def test_custom_provider_does_not_attach_unrelated_plugin(builder):
    assert builder.build_dsl(provider="vendor/other/other")["dependencies"] == []


def test_plugin_dependency_can_be_overridden_or_disabled(builder):
    identifier = "vendor/other:1.2.3@" + "a" * 64
    flow = builder.build_dsl(provider="vendor/other/other", plugin_identifier=identifier)
    assert flow["dependencies"] == [{"current_identifier": None, "type": "marketplace", "value": {"marketplace_plugin_unique_identifier": identifier, "version": "1.2.3"}}]
    assert builder.build_dsl(plugin_identifier="none")["dependencies"] == []


def test_committed_yaml_matches_default_builder(builder):
    assert yaml.safe_load((ROOT / "dsl/pawnshop-chatflow.yml").read_text(encoding="utf-8")) == builder.build_dsl()


@pytest.fixture
def wire_models():
    spec = importlib.util.spec_from_file_location("pawnshop_wire_models", ROOT / "backend/pawnshop/models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proposal_card(value="纸船"):
    return {key: value for key in ("name", "appearance", "trait", "meaning", "inscription", "quest")}


@pytest.mark.parametrize("proposal,query", [
    ({"action": "correct", "card": proposal_card(), "reported_event": "其实我怕让人失望"}, "其实我怕让人失望"),
    ({"action": "correct", "card": proposal_card("")}, "纠正一下"),
    ({"action": "correct", "card": proposal_card("物" * 251)}, "纠正一下"),
    ({"action": "chat", "reply": "余" * 2001}, "你好"),
    ({"action": "chat", "item_id": "i" * 257}, "你好"),
    ({"action": "revisit", "card": proposal_card(), "reported_event": "事" * 601}, "事" * 601),
    ({"action": "revisit", "card": proposal_card(), "reported_event": "我已经完成了所有练习"}, "我还没试过练习"),
    ({"action": "revisit", "card": proposal_card(), "reported_event": ""}, "回访"),
    ({"action": "revisit", "card": proposal_card("🌙" * 250), "reported_event": "🌙" * 600}, "🌙" * 600),
    ({"action": "chat", "card": None}, "你好"),
])
def test_backend_invalid_proposals_are_stopped_before_http(flow, proposal, query):
    out = run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text=json.dumps(proposal, ensure_ascii=False), query=query)
    assert out["ok"] == "no"
    assert out["body"] == ""


@pytest.mark.parametrize("proposal,query", [
    ({"action": "correct", "card": proposal_card("物" * 250)}, "其实我怕让人失望"),
    ({"action": "correct", "card": proposal_card(), "reported_event": ""}, "其实我怕让人失望"),
    ({"action": "chat", "reply": "余" * 2000, "item_id": "i" * 256}, "你好"),
    ({"action": "revisit", "card": proposal_card("物" * 250), "reported_event": "事" * 600}, "后来，" + "事" * 600 + "。"),
])
def test_boundary_proposals_satisfy_actual_backend_schema(flow, wire_models, proposal, query):
    out = run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text=json.dumps(proposal, ensure_ascii=False), query=query)
    assert out["ok"] == "yes"
    assert wire_models.ActRequest.model_validate_json(out["body"]).proposal.model_dump(exclude_unset=True) == proposal


@pytest.mark.parametrize("action,query", [("appraise", "我总担心说错话"), ("correct", "其实不是怕说错，是怕让人失望"), ("revisit", "回访：昨天我说出了自己的意见。")])
def test_generated_prompt_examples_match_code_and_backend(flow, wire_models, action, query):
    prompt = next(n for n in flow["workflow"]["graph"]["nodes"] if n["id"] == "proposal")["data"]["prompt_template"][0]["text"]
    examples = [json.loads(line[line.index("{"):]) for line in prompt.splitlines() if "示例（" in line and "：{" in line]
    proposal = next((value for value in examples if value["action"] == action), None)
    assert proposal is not None, f"Missing usable {action} prompt example"
    out = run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text=json.dumps(proposal, ensure_ascii=False), query=query)
    assert out["ok"] == "yes"
    wire_models.ActRequest.model_validate_json(out["body"])
    if action != "revisit":
        assert not proposal.get("reported_event")
    else:
        assert proposal["reported_event"] in query


@pytest.mark.parametrize("event,expected_ok", [('"' * 600, False), ("\\" * 600, False), ('"' * 500, True)], ids=["quotes-over-budget", "backslashes-over-budget", "quotes-within-budget"])
def test_escaped_event_memory_budget_matches_backend(flow, wire_models, event, expected_ok):
    proposal = {"action": "revisit", "card": proposal_card("🌙" * 225), "reported_event": event}
    card_bytes = len(wire_models.Card.model_validate(proposal["card"]).model_dump_json().encode("utf-8"))
    assert card_bytes + len(event.encode("utf-8")) <= 6500, "Regression must fit the obsolete raw-byte calculation"
    if expected_ok:
        wire_models.Proposal.model_validate(proposal)
    else:
        with pytest.raises(ValueError, match="memory byte budget"):
            wire_models.Proposal.model_validate(proposal)
    out = run_code(flow, "act_body", user_id="u", turn_id="t", proposal_text=json.dumps(proposal, ensure_ascii=False), query=event)
    assert out["ok"] == ("yes" if expected_ok else "no")
    if not expected_ok:
        assert out["body"] == ""
