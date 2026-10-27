import json


def main(user_id: str, turn_id: str, proposal_text: str, query: str) -> dict:
    failure = {"ok": "no", "body": "", "error": "老余：这份鉴定单格式不对，这轮没有提交交易。请重新说一遍；正式入柜请单独发送「确认典当」。"}
    try:
        text = proposal_text.strip()
        if text.startswith("```json\n") and text.endswith("\n```"):
            text = text[8:-4].strip()
        elif text.startswith("```\n") and text.endswith("\n```"):
            text = text[4:-4].strip()
        if len(text) > 24000:
            return failure
        proposal = json.loads(text)
        allowed = {"action", "item_id", "expected_version", "reply", "reported_event", "card"}
        if not isinstance(proposal, dict) or set(proposal) - allowed:
            return failure
        if proposal.get("action") not in ("appraise", "correct", "pawn", "revisit", "shelf", "retrieve", "chat"):
            return failure
        for key in ("item_id", "reply", "reported_event"):
            if key in proposal and not isinstance(proposal[key], str):
                return failure
        for key, limit in (("item_id", 256), ("reply", 2000), ("reported_event", 600)):
            if len(proposal.get(key, "")) > limit:
                return failure
        event = proposal.get("reported_event", "")
        if proposal["action"] != "revisit" and event:
            return failure
        if proposal["action"] == "revisit" and (not event.strip() or event.strip() not in query):
            return failure
        if "expected_version" in proposal and (type(proposal["expected_version"]) is not int or proposal["expected_version"] < 0):
            return failure
        if "card" in proposal:
            card = proposal["card"]
            if not isinstance(card, dict) or set(card) != {"name", "appearance", "trait", "meaning", "inscription", "quest"}:
                return failure
            if not all(isinstance(value, str) and 1 <= len(value) <= 250 for value in card.values()):
                return failure
        if proposal["action"] in ("appraise", "correct", "revisit") and "card" not in proposal:
            return failure
        card_bytes = len(json.dumps(proposal["card"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) if "card" in proposal else 0
        event_bytes = len(json.dumps(event, ensure_ascii=False).encode("utf-8")) - 2
        if card_bytes + event_bytes > 6500:
            return failure
        if proposal["action"] == "pawn" and query.strip() not in ("确认典当", "确认入柜"):
            return failure
        return {"ok": "yes", "body": json.dumps({"user_id": user_id, "turn_id": turn_id, "proposal": proposal}, ensure_ascii=False), "error": ""}
    except (ValueError, TypeError, AttributeError):
        return failure
