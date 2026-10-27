"""Verify real backend/PowerContext integration using only fictional test data.

This deliberately does not call a model or Dify. Its evidence is labelled accordingly.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def call(base: str, path: str, key: str, payload: dict | None = None) -> dict:
    request = Request(base.rstrip('/') + path,
                      data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                      headers={'Content-Type': 'application/json', 'X-Pawnshop-Key': key})
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:18081')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    config = read_env(args.env_file or project / 'deploy' / '.env')
    key = config['PAWNSHOP_API_KEY']
    user = 'acceptance-' + uuid.uuid4().hex[:12]
    evidence = {'kind': 'real_backend_and_powercontext_http', 'dify_model_executed': False,
                'created_at': datetime.now(timezone.utc).isoformat(), 'user_id': user, 'steps': []}

    def turn(query: str, action: str, card: dict | None = None, event: str = '', session: str = 'first'):
        turn_id = uuid.uuid4().hex
        prepared = call(args.base_url, '/v1/prepare', key,
                        {'user_id': user, 'conversation_id': session, 'turn_id': turn_id, 'query': query})
        proposal = {'action': action, 'item_id': prepared.get('active_item_id') or '',
                    'expected_version': prepared.get('active_version') or 0,
                    'reply': '这是虚构验收样例的预设台词，未调用模型。',
                    'reported_event': event}
        if card is not None:
            proposal['card'] = card
        payload = {'user_id': user, 'turn_id': turn_id, 'proposal': proposal}
        receipt = call(args.base_url, '/v1/act', key, payload)
        assert receipt['ok'], receipt
        evidence['steps'].append({'query': query, 'session': session, 'prepared': prepared, 'receipt': receipt})
        return prepared, receipt, payload

    card = {'name': '自动续费的同龄人滤镜', 'appearance': '一副有雾气的旧眼镜',
            'trait': '只显示别人的高光时刻', 'meaning': '用户正在探索与他人比较的感受',
            'inscription': '鉴定草稿，等待主人纠正', 'quest': '给最近完成的一件小事起个名字'}
    turn('我总拿自己和同龄人比较。', 'appraise', card)
    corrected = dict(card, name='没有收件人的努力邮票', meaning='用户明确表示：努力没有被看见，并非嫉妒别人',
                     appearance='一枚没有写收件地址的邮票', trait='记录努力的去向')
    turn('你理解错了，我不是嫉妒，我是觉得努力没有被看见。', 'correct', corrected)
    _, saved, pawn_payload = turn('确认典当', 'pawn')
    assert saved['memory_status'] == 'synced', saved
    assert saved['memory_refs'], saved
    replay = call(args.base_url, '/v1/act', key, pawn_payload)
    assert replay['item_id'] == saved['item_id'] and replay['replayed']
    evidence['duplicate_submission'] = replay

    prepared, _, _ = turn('老板，上次我放在这里的东西还在吗？', 'chat', session='second')
    assert prepared['memory_status'] == 'ready', prepared
    assert '努力' in prepared['memory_context'], prepared
    evolved = dict(corrected, name='已经寄出的努力邮票', inscription='收件人还没回信，寄件人已经迈出一步')
    _, transformed, _ = turn('后来我把拖着的作品交出去了，虽然没有多少人看。', 'revisit', evolved,
                             event='我把拖着的作品交出去了，虽然没有多少人看。', session='second')
    assert transformed['version'] > saved['version']
    mine = call(args.base_url, '/v1/items?user_id=' + user, key)
    other = call(args.base_url, '/v1/items?user_id=' + user + '-other', key)
    evidence['shelf'] = mine
    evidence['other_player_shelf'] = other
    assert saved['item_id'] not in json.dumps(other)
    try:
        call(args.base_url, f'/v1/items/{saved["item_id"]}?user_id={user}-other', key)
        raise AssertionError('Cross-player item access unexpectedly succeeded')
    except HTTPError as error:
        assert error.code == 404, error.code
        evidence['cross_player_detail_status'] = error.code
    turn('取回这件藏品', 'retrieve', session='second')
    evidence['result'] = 'passed'
    output = args.output or project / 'docs' / 'evidence' / 'services.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': 'passed', 'evidence': str(output), 'player': user,
                      'scope': 'real backend + real PowerContext; Dify/model not executed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
