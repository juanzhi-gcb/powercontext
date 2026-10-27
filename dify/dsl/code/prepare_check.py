import json


def main(status_code: int, body: str, turn_id: str) -> dict:
    failure = {"ok": "no", "state_json": "", "memory_context": "", "memory_status": "unavailable", "error": "老余：账本读取失败，这轮还没有办理交易。请稍后重新发送。"}
    try:
        if type(status_code) is not int or not 200 <= status_code < 300:
            return failure
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("turn_id") != turn_id:
            return failure
        if not isinstance(data.get("state_json"), str):
            return failure
        state = json.loads(data["state_json"])
        if not isinstance(state, dict) or not {"current_item", "shelf", "allowed_actions"} <= set(state):
            return failure
        if not isinstance(state["shelf"], list) or not isinstance(state["allowed_actions"], list):
            return failure
        if data.get("memory_status") not in ("ready", "empty", "unavailable"):
            return failure
        if not isinstance(data.get("memory_context"), str) or not isinstance(data.get("active_item_id"), str):
            return failure
        if type(data.get("active_version")) is not int or data["active_version"] < 0:
            return failure
        return {"ok": "yes", "state_json": data["state_json"], "memory_context": data["memory_context"], "memory_status": data["memory_status"], "error": ""}
    except (ValueError, TypeError, KeyError):
        return failure
