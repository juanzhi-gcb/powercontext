"""Install the pinned model provider, save local credentials, or publish locally."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from configure_dify import Console, login_local
from verify_services import read_env

PLUGIN = 'langgenius/openai_api_compatible:0.0.72@87f3c4c7acee9ff03ac2c04ba8191edc5ea87cd53e36af1bbf1ccd13f00352a4'
PROVIDER = 'langgenius/openai_api_compatible/openai_api_compatible'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install-plugin', 'configure', 'publish'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--base-url', default='http://localhost:18080')
    args = parser.parse_args()
    root = args.root.resolve()
    console = Console(args.base_url)
    login_local(console, root)
    model = read_env(root / 'model.env')
    state_file = root / 'dify-local.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
    if args.action == 'install-plugin':
        result = console.call('/workspaces/current/plugin/install/marketplace',
                              {'plugin_unique_identifiers': [PLUGIN]})
        # Task identifiers are safe; plugin initialization may continue after this exits.
        print(json.dumps({'requested_plugin': PLUGIN, 'task': result}, ensure_ascii=False))
        return
    for name in ('MODEL_BASE_URL', 'MODEL_API_KEY', 'MODEL_NAME'):
        if not model.get(name):
            raise SystemExit(f'Fill {name} in {root / "model.env"} first.')
    if not model['MODEL_BASE_URL'].startswith('https://'):
        raise SystemExit('Use an HTTPS model endpoint; credentials are never sent to an HTTP endpoint.')
    if args.action == 'configure':
        # Credential validation performs a small real model call inside the official plugin.
        console.call(f'/workspaces/current/model-providers/{PROVIDER}/models/credentials', {
            'model': model['MODEL_NAME'], 'model_type': 'llm', 'name': 'Pawnshop local model',
            'credentials': {'api_key': model['MODEL_API_KEY'], 'endpoint_url': model['MODEL_BASE_URL'],
                            'mode': 'chat', 'context_size': '32768', 'max_tokens_to_sample': '4096',
                            'agent_thought_support': 'not_supported', 'function_calling_type': 'no_call',
                            'vision_support': 'no_support', 'structured_output_support': 'not_supported',
                            'stream_include_usage': 'enabled', 'api_type': 'chat_completions'},
        })
        state['model_configured'] = model['MODEL_NAME']
        print(json.dumps({'result': 'model_configured', 'model': model['MODEL_NAME'], 'key_printed': False}))
    else:
        app_id = state.get('app_id')
        if not app_id:
            raise SystemExit('Run configure_dify.py first to import the application.')
        console.call(f'/apps/{app_id}/workflows/publish', {'marked_name': '比赛体验', 'marked_comment': '烦恼典当行可复现样例'})
        if not state.get('api_key'):
            token = console.call(f'/apps/{app_id}/api-keys', {})
            state['api_key'] = token['token']
        app = console.call(f'/apps/{app_id}')
        site = app.get('site') or {}
        code = site.get('access_token') or site.get('code')
        state['play_url'] = args.base_url + '/chat/' + code if code else ''
        state['api_base_url'] = args.base_url + '/v1'
        evidence = {'kind': 'real_dify_local_publish', 'created_at': datetime.now(timezone.utc).isoformat(),
                    'app_id': app_id, 'provider': PROVIDER, 'plugin': PLUGIN, 'model': model['MODEL_NAME'],
                    'published': True, 'model_conversation_executed': False, 'credentials_included': False}
        project = Path(__file__).resolve().parents[1]
        evidence_file = project / 'docs' / 'evidence' / 'dify-publish.json'
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'result': 'published_locally', 'play_url': state['play_url'], 'key_printed': False}, ensure_ascii=False))
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    state_file.chmod(0o600)


if __name__ == '__main__':
    main()
