"""Real Dify + model end-to-end acceptance for 烦恼典当行.

This drives the published Chatflow through Dify's service API, then reads the
same workflow runs back through the console API so the evidence shows what the
prepare node actually handed the model (memory_status and memory_context), not
just what the model said. It asserts on real receipts; a failed step is written
as a failure and never rewritten as a pass.

Requires: Dify running and the app published, PowerContext + backend running,
and a local Dify account file for console login.

    uv run --project backend python scripts/verify_e2e.py --root D:/DifyPawnshop
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from configure_dify import Console, login_local
from verify_services import call as backend_call
from verify_services import read_env

CORRECTION = "你鉴定错了，我不是嫉妒他们，我是觉得自己的努力一直没被看见。"
REVISIT_REPORT = "后来我把一直拖着的作品交出去了，虽然没什么人看。"


class CheckFailed(RuntimeError):
    pass


def check(condition, message, detail=None):
    if not condition:
        raise CheckFailed(message if detail is None else f"{message}: {detail}")


class Dify:
    def __init__(self, base: str, api_key: str, app_id: str, console: Console):
        self.base, self.api_key, self.app_id, self.console = base.rstrip('/'), api_key, app_id, console

    def chat(self, user: str, query: str, conversation: str = '') -> dict:
        body = json.dumps({'inputs': {}, 'query': query, 'response_mode': 'streaming',
                           'user': user, 'conversation_id': conversation}).encode()
        request = Request(self.base + '/v1/chat-messages', data=body,
                          headers={'Authorization': 'Bearer ' + self.api_key,
                                   'Content-Type': 'application/json'})
        answer, run_id, conversation_id = [], None, conversation
        with urlopen(request, timeout=300) as response:
            for raw in response:
                line = raw.decode('utf-8').strip()
                if not line.startswith('data:'):
                    continue
                payload = json.loads(line[5:].strip())
                event = payload.get('event')
                if event == 'error':
                    raise CheckFailed('Dify returned a workflow error', payload)
                run_id = payload.get('workflow_run_id') or run_id
                conversation_id = payload.get('conversation_id') or conversation_id
                if event == 'message' and payload.get('answer'):
                    answer.append(payload['answer'])
        check(run_id, 'Dify did not report a workflow_run_id')
        return {'query': query, 'answer': ''.join(answer), 'workflow_run_id': run_id,
                'conversation_id': conversation_id, 'nodes': self.nodes(run_id)}

    def nodes(self, run_id: str) -> dict:
        data = self.console.call(f'/apps/{self.app_id}/workflow-runs/{run_id}/node-executions')
        return {item.get('title'): item.get('outputs') or {} for item in data['data']}

    def prepare_state(self, turn: dict) -> dict:
        body = (turn['nodes'].get('读取账本与 PowerContext') or {}).get('body')
        check(body, 'prepare node produced no output')
        return json.loads(body)

    def receipt(self, turn: dict) -> dict:
        body = (turn['nodes'].get('提交受校验交易') or {}).get('body')
        check(body, 'act node produced no receipt')
        return json.loads(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('D:/DifyPawnshop'))
    parser.add_argument('--base-url', default='http://localhost:18080')
    parser.add_argument('--state-file', type=Path)
    parser.add_argument('--backend-url', default='http://localhost:18081')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    state = json.loads((args.state_file or root / 'dify-local.json').read_text(encoding='utf-8'))
    api_key = state.get('api_key')
    check(api_key, 'dify-local.json has no app api_key; set one in Dify and record it locally')
    key = read_env(args.env_file or project / 'deploy' / '.env')['PAWNSHOP_API_KEY']
    console = Console(args.base_url)
    login_local(console, root)
    dify = Dify(args.base_url, api_key, state['app_id'], console)

    user = 'e2e-' + uuid.uuid4().hex[:10]
    other = user + '-other'
    evidence = {'kind': 'real_dify_model_and_powercontext_e2e', 'created_at': datetime.now(timezone.utc).isoformat(),
                'dify_version': '1.17.1', 'model_executed': True, 'credentials_included': False,
                'user_id': user, 'steps': []}
    output = args.output or project / 'docs' / 'evidence' / 'e2e.json'

    def record(name: str, data: dict) -> None:
        evidence['steps'].append({'step': name, **data})
        print('ok', name, flush=True)

    try:
        first = dify.chat(user, '我最近总拿自己和同龄人比较，看到别人的消息就不舒服。')
        draft = dify.receipt(first)
        record('appraise', {'conversation_id': first['conversation_id'], 'workflow_run_id': first['workflow_run_id'],
                            'prepare_memory_status': dify.prepare_state(first)['memory_status'],
                            'action': draft['action'], 'item_id': draft['item_id'], 'version': draft['version'],
                            'answer': first['answer']})
        check(draft['action'] == 'appraise', 'first turn did not appraise', draft['action'])
        draft_item = backend_call(args.backend_url, f'/v1/items/{draft["item_id"]}?user_id={user}', key)
        check(draft_item['status'] == 'draft', 'draft was not stored as draft', draft_item['status'])
        draft_card = draft_item['card']

        second = dify.chat(user, CORRECTION, first['conversation_id'])
        corrected = dify.receipt(second)
        record('correct', {'conversation_id': second['conversation_id'], 'workflow_run_id': second['workflow_run_id'],
                           'prepare_memory_status': dify.prepare_state(second)['memory_status'],
                           'action': corrected['action'], 'item_id': corrected['item_id'],
                           'version': corrected['version'], 'answer': second['answer']})
        check(corrected['action'] == 'correct', 'correction was not applied', corrected['action'])
        corrected_item = backend_call(args.backend_url, f'/v1/items/{draft["item_id"]}?user_id={user}', key)
        check(corrected_item['status'] == 'draft', 'corrected item is no longer a draft', corrected_item['status'])
        check(corrected_item['card'] != draft_card, 'correction did not change the card')

        third = dify.chat(user, '确认典当', first['conversation_id'])
        pawned = dify.receipt(third)
        record('pawn', {'conversation_id': third['conversation_id'], 'workflow_run_id': third['workflow_run_id'],
                        'prepare_memory_status': dify.prepare_state(third)['memory_status'],
                        'action': pawned['action'], 'item_id': pawned['item_id'], 'version': pawned['version'],
                        'memory_status': pawned['memory_status'], 'memory_refs': pawned['memory_refs'],
                        'answer': third['answer']})
        check(pawned['action'] == 'pawn', 'explicit confirmation did not pawn', pawned['action'])
        check(pawned['memory_status'] == 'synced', 'memory was not synced at pawn', pawned['memory_status'])
        check(pawned['memory_refs'], 'pawn receipt has no PowerContext memory reference')

        recalled = dify.chat(user, '老板，上次我放在这里的东西还在吗？')
        prepared = dify.prepare_state(recalled)
        record('new_session_recall', {'conversation_id': recalled['conversation_id'],
                                      'workflow_run_id': recalled['workflow_run_id'],
                                      'prepare_memory_status': prepared['memory_status'],
                                      'memory_context': prepared['memory_context'], 'answer': recalled['answer']})
        check(recalled['conversation_id'] != first['conversation_id'], 'new session reused the old conversation')
        check(prepared['memory_status'] == 'ready', 'new session did not recall memory', prepared['memory_status'])
        check('自己的努力一直没被看见' in prepared['memory_context'],
              'recalled context lost the player correction')
        check(draft['item_id'] in prepared['memory_context'], 'recalled context lost the item id')

        revisit = dify.chat(user, REVISIT_REPORT, recalled['conversation_id'])
        changed = dify.receipt(revisit)
        record('revisit', {'conversation_id': revisit['conversation_id'], 'workflow_run_id': revisit['workflow_run_id'],
                           'prepare_memory_status': dify.prepare_state(revisit)['memory_status'],
                           'action': changed['action'], 'item_id': changed['item_id'], 'version': changed['version'],
                           'memory_status': changed['memory_status'], 'answer': revisit['answer']})
        check(changed['action'] == 'revisit', 'reported experience did not transform the item', changed['action'])
        check(changed['version'] > pawned['version'], 'revisit did not raise the item version')
        transformed = backend_call(args.backend_url, f'/v1/items/{draft["item_id"]}?user_id={user}', key)
        check(transformed['status'] == 'transformed', 'item is not transformed', transformed['status'])
        check(transformed['events'][-1]['memory_status'] == 'synced', 'revisit memory was not synced')

        mine = backend_call(args.backend_url, f'/v1/items?user_id={user}', key)
        stranger = backend_call(args.backend_url, f'/v1/items?user_id={other}', key)
        check(len(mine['items']) == 1, 'shelf does not hold exactly one item', len(mine['items']))
        check(stranger['items'] == [], 'another player saw this shelf')
        try:
            backend_call(args.backend_url, f'/v1/items/{draft["item_id"]}?user_id={other}', key)
            raise CheckFailed('cross-player item detail unexpectedly succeeded')
        except HTTPError as error:
            check(error.code == 404, 'cross-player detail returned another status', error.code)
        record('isolation', {'shelf': mine['items'], 'other_shelf': stranger['items'],
                             'cross_player_detail_status': 404})
        evidence['result'] = 'passed'
        status = 0
    except (CheckFailed, HTTPError, KeyError, ValueError) as error:
        evidence['result'] = 'failed'
        evidence['error'] = f'{type(error).__name__}: {error}'
        print('FAILED:', evidence['error'], flush=True)
        status = 1
    evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': evidence['result'], 'evidence': str(output), 'player': user}, ensure_ascii=False))
    raise SystemExit(status)


if __name__ == '__main__':
    main()