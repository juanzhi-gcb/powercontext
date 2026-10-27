"""Regression for the pinned Dify console's Base64 password wire protocol."""
import base64
import importlib.util
import json
import sys
from pathlib import Path


def test_local_login_encodes_password_but_keeps_stored_password_readable(tmp_path):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location('pawnshop_configure_dify', scripts / 'configure_dify.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        password = 'Example9-secret!'
        file = tmp_path / 'local-credentials.json'
        file.write_text(json.dumps({'email': 'owner@example.com', 'password': password}), encoding='utf-8')

        class LocalConsole:
            def call(self, path, payload=None):
                if path == '/setup':
                    return {'step': 'finished'}
                assert path == '/login'
                assert payload['password'] == base64.b64encode(password.encode()).decode()
                return {'result': 'success'}

        module.login_local(LocalConsole(), tmp_path)
        assert json.loads(file.read_text(encoding='utf-8'))['password'] == password
    finally:
        sys.path.remove(str(scripts))
