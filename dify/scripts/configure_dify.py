"""Initialize this local Dify instance and import the DSL without exposing secrets."""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import yaml

from verify_services import read_env


class Console:
    def __init__(self, base: str):
        self.base = base.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def call(self, path: str, payload: dict | None = None, method: str | None = None):
        headers = {'Content-Type': 'application/json', 'Origin': self.base}
        for cookie in self.jar:
            if cookie.name.removeprefix('__Host-') == 'csrf_token':
                headers['X-CSRF-Token'] = cookie.value
        request = Request(self.base + '/console/api' + path,
                          data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                          headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=120) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as error:
            # Do not print request bodies, cookies, tokens or imported environment variables.
            raise RuntimeError(f'Dify {method or ("POST" if payload is not None else "GET")} {path}: HTTP {error.code}') from None


def login_local(console: Console, root: Path) -> dict:
    credentials = root / 'local-credentials.json'
    setup = console.call('/setup')
    if setup['step'] == 'not_started':
        if credentials.exists():
            account = json.loads(credentials.read_text(encoding='utf-8'))
        else:
            account = {'email': 'owner@example.com', 'password': 'Pw9!' + secrets.token_urlsafe(24)}
            credentials.write_text(json.dumps(account, indent=2) + '\n', encoding='utf-8')
            credentials.chmod(0o600)
        console.call('/setup', {**account, 'name': '烦恼典当行掌柜', 'language': 'zh-Hans'})
    if not credentials.exists():
        raise SystemExit('Dify is already initialized. Provide your local account in local-credentials.json; existing accounts are not modified.')
    account = json.loads(credentials.read_text(encoding='utf-8'))
    result = console.call('/login', {**account, 'password': base64.b64encode(account['password'].encode()).decode(), 'remember_me': True})
    if result.get('result') != 'success':
        raise RuntimeError('Dify console login did not succeed')
    return account


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--base-url', default='http://localhost:18080')
    parser.add_argument('--dsl', type=Path)
    parser.add_argument('--new-app', action='store_true', help='Import another copy to verify clean reimport')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    console = Console(args.base_url)
    login_local(console, root)
    dsl = yaml.safe_load((args.dsl or project / 'dsl' / 'pawnshop-chatflow.yml').read_text(encoding='utf-8'))
    key = read_env(project / 'deploy' / '.env')['PAWNSHOP_API_KEY']
    found = False
    for variable in dsl['workflow'].get('environment_variables', []):
        if variable['name'] == 'PAWNSHOP_API_KEY':
            variable['value'] = key
            found = True
    if not found:
        raise SystemExit('DSL is missing its PAWNSHOP_API_KEY secret environment variable')
    state_file = root / 'dify-local.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
    request = {'mode': 'yaml-content', 'yaml_content': yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False)}
    if state.get('app_id') and not args.new_app:
        request['app_id'] = state['app_id']
    imported = console.call('/apps/imports', request)
    if imported.get('status') not in ('completed', 'completed-with-warnings', 'completed_with_warnings'):
        raise RuntimeError('DSL import did not complete: ' + str(imported.get('status')))
    app_id = imported['app_id']
    draft = console.call(f'/apps/{app_id}/workflows/draft')
    node_count = len(draft['graph']['nodes'])
    if node_count != len(dsl['workflow']['graph']['nodes']):
        raise RuntimeError('Imported draft node count differs from DSL')
    state.update({'app_id': app_id, 'base_url': args.base_url})
    state_file.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    evidence = {'kind': 'real_dify_import', 'created_at': datetime.now(timezone.utc).isoformat(),
                'dify_version': '1.17.1', 'dsl_version': dsl['version'], 'app_id': app_id,
                'import_status': imported['status'], 'node_count': node_count,
                'clean_new_app': args.new_app, 'model_executed': False,
                'credentials_included': False}
    path = project / 'docs' / 'evidence' / ('dify-reimport.json' if args.new_app else 'dify-import.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': 'imported', 'app_url': args.base_url + '/app/' + app_id + '/workflow',
                      'node_count': node_count, 'credentials_file': str(root / 'local-credentials.json'),
                      'model_executed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
