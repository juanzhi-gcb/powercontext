import json


def main(user_id: str, conversation_id: str, turn_id: str, query: str) -> dict:
    return {"body": json.dumps({"user_id": user_id, "conversation_id": conversation_id, "turn_id": turn_id, "query": query}, ensure_ascii=False)}
