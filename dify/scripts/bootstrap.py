"""Fetch pinned upstream sources and generate local-only deployment secrets."""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
from pathlib import Path

DIFY_COMMIT = '8387590ace4a094de812b7847fc6a4c3a27cd52b'
PC_COMMIT = '31ecdd61beadb7ac8de5da20998dead9a9e07845'


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, encoding='utf-8').strip()


def checkout(path: Path, repository: str, commit: str, sparse: list[str] | None = None) -> None:
    if not (path / '.git').exists():
        run('git', 'clone', '--filter=blob:none', repository, str(path))
    if sparse:
        run('git', 'sparse-checkout', 'set', *sparse, cwd=path)
    if run('git', 'status', '--porcelain', cwd=path):
        raise SystemExit(f'Upstream checkout has local changes; refusing to overwrite: {path}')
    try:
        run('git', 'cat-file', '-e', commit, cwd=path)
    except subprocess.CalledProcessError:
        run('git', 'fetch', '--depth', '1', 'origin', commit, cwd=path)
    run('git', 'checkout', '--detach', commit, cwd=path)


def write_new(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        try:
            path.chmod(0o600)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    checkout(root / 'dify-runtime', 'https://github.com/langgenius/dify.git', DIFY_COMMIT, ['docker'])
    checkout(root / 'powercontext-source', 'https://github.com/oceanbase/powercontext.git', PC_COMMIT)
    data = root / 'data'
    for name in ('pawnshop', 'powercontext'):
        (data / name).mkdir(parents=True, exist_ok=True)
    write_new(project / 'deploy' / '.env', '\n'.join([
        'PAWNSHOP_API_KEY=' + secrets.token_urlsafe(32),
        'POWERCONTEXT_TOKEN=' + secrets.token_urlsafe(32),
        f'POWERCONTEXT_SOURCE={(root / "powercontext-source").as_posix()}',
        'POWERCONTEXT_VERSION=1.4.0',
        f'PAWNSHOP_DATA={data.as_posix()}',
        'PAWNSHOP_PORT=18081', 'POWERCONTEXT_PORT=18082', '',
    ]))
    upstream = root / 'dify-runtime' / 'docker'
    base_env = (upstream / '.env.example').read_text(encoding='utf-8')
    overrides = {
        'EXPOSE_NGINX_PORT': '18080',
        'EXPOSE_NGINX_SSL_PORT': '18443',
        'EXPOSE_PLUGIN_DEBUGGING_PORT': '15003',
        'NEXT_PUBLIC_SOCKET_URL': 'ws://localhost:18080',
        'SECRET_KEY': secrets.token_urlsafe(48),
        'DB_PASSWORD': secrets.token_urlsafe(32),
        'REDIS_PASSWORD': secrets.token_urlsafe(32),
        'PLUGIN_DAEMON_KEY': secrets.token_urlsafe(32),
        'PLUGIN_DIFY_INNER_API_KEY': secrets.token_urlsafe(32),
        'DIFY_AGENT_API_TOKEN': secrets.token_urlsafe(32),
        'DIFY_AGENT_SERVER_SECRET_KEY': secrets.token_urlsafe(32),
        'DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN': secrets.token_urlsafe(32),
        'CODE_EXECUTION_API_KEY': secrets.token_urlsafe(32),
        'SANDBOX_API_KEY': '',
        'SSRF_PROXY_ALLOW_PRIVATE_IPS': '172.30.92.0/24',
        'COMPOSE_PROFILES': 'postgresql,collaboration',
        'NEXT_TELEMETRY_DISABLED': '1',
    }
    overrides['SANDBOX_API_KEY'] = overrides['CODE_EXECUTION_API_KEY']
    overrides['CELERY_BROKER_URL'] = f'redis://:{overrides["REDIS_PASSWORD"]}@redis:6379/1'
    lines = []
    for line in base_env.splitlines():
        key = line.split('=', 1)[0]
        lines.append(f'{key}={overrides.pop(key)}' if key in overrides else line)
    lines.extend(f'{key}={value}' for key, value in overrides.items())
    write_new(upstream / '.env', '\n'.join(lines) + '\n')
    write_new(root / 'model.env', '# Fill locally; never commit this file.\nMODEL_BASE_URL=\nMODEL_NAME=\nMODEL_API_KEY=\n')
    # A separate, immutable identity per repeated acceptance run is the reset mechanism.
    print(json.dumps({'root': str(root), 'dify': 'http://localhost:18080',
                      'secrets_file': str(project / 'deploy' / '.env'),
                      'model_file': str(root / 'model.env')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
