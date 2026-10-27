import json


def main(status_code: int, body: str) -> dict:
    failure = {"ok": "no", "display": "", "error": "老余：没有拿到有效交易回执，不能说已经入柜或取回。交易结果待核实，请先查看货架再决定下一步。"}
    try:
        if type(status_code) is not int or not 200 <= status_code < 300:
            return failure
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("ok") is not True:
            return failure
        required = {"action", "reply", "display", "item_id", "version", "memory_status", "memory_refs", "replayed"}
        if not required <= set(data):
            return failure
        if data["action"] not in ("appraise", "correct", "pawn", "revisit", "shelf", "retrieve", "chat"):
            return failure
        if not all(isinstance(data[key], str) for key in ("reply", "display", "item_id", "memory_status")) or not data["display"].strip():
            return failure
        if type(data["version"]) is not int or data["version"] < 0:
            return failure
        if not isinstance(data["memory_refs"], list) or type(data["replayed"]) is not bool:
            return failure
        return {"ok": "yes", "display": data["display"], "error": ""}
    except (ValueError, TypeError, KeyError):
        return failure
