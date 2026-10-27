"""Start, stop or inspect only this submission's two Docker Compose projects."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def capture(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding='utf-8').strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('up', 'down', 'status', 'lock-images'))
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    # Keep this project's Desktop plugins isolated from installed Rancher/Podman
    # CLI plugins, without changing the user's global Docker configuration.
    desktop_plugins = Path('C:/Program Files/Docker/Docker/resources/cli-plugins')
    if os.name == 'nt' and desktop_plugins.is_dir():
        client = root / 'docker-client'
        client.mkdir(parents=True, exist_ok=True)
        config = client / 'config.json'
        if not config.exists():
            config.write_text(json.dumps({'cliPluginsExtraDirs': [str(desktop_plugins)]}), encoding='utf-8')
        os.environ['DOCKER_CONFIG'] = str(client)
        os.environ['DOCKER_HOST'] = 'npipe:////./pipe/dockerDesktopLinuxEngine'
    runtime = root / 'dify-runtime' / 'docker'
    if not (runtime / '.env').exists() or not (project / 'deploy' / '.env').exists():
        raise SystemExit('Run bootstrap.py --root <directory> first.')
    dify = ['docker', 'compose', '-p', 'pawnshop-dify', '--project-directory', str(runtime),
            '--env-file', str(runtime / '.env'), '-f', str(runtime / 'docker-compose.yaml'),
            '-f', str(project / 'deploy' / 'dify.override.yaml')]
    lockfile = project / 'deploy' / 'dify-images.lock.json'
    if lockfile.exists():
        dify += ['-f', str(lockfile)]
    game = ['docker', 'compose', '-p', 'pawnshop-game', '--env-file', str(project / 'deploy' / '.env'),
            '-f', str(project / 'deploy' / 'compose.yaml')]
    if args.command == 'up':
        existing = subprocess.run(['docker', 'network', 'inspect', 'pawnshop-shared'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if existing.returncode:
            subprocess.run(['docker', 'network', 'create', '--driver', 'bridge', '--subnet',
                            '172.30.92.0/24', 'pawnshop-shared'], check=True)
        else:
            network = json.loads(capture('docker', 'network', 'inspect', 'pawnshop-shared'))[0]
            if network['IPAM']['Config'][0]['Subnet'] != '172.30.92.0/24':
                raise SystemExit('Existing pawnshop-shared uses another subnet; refusing to modify it.')
        subprocess.run(dify + ['up', '-d', '--quiet-pull'], check=True)
        subprocess.run(game + ['up', '-d', '--build'], check=True)
        print('Dify: http://localhost:18080 | Game health: http://localhost:18081/health')
    elif args.command == 'down':
        subprocess.run(game + ['down'], check=True)
        subprocess.run(dify + ['down'], check=True)
        print('Stopped this project. Persisted data and shared network were retained.')
    elif args.command == 'status':
        subprocess.run(dify + ['ps'], check=True)
        subprocess.run(game + ['ps'], check=True)
    else:
        config = json.loads(capture(*dify, 'config', '--format', 'json'))
        services = {}
        for name, service in config['services'].items():
            image = service.get('image')
            if image:
                info = json.loads(capture('docker', 'image', 'inspect', image))[0]
                digests = info.get('RepoDigests') or []
                if not digests:
                    raise SystemExit(f'No registry digest for {name}; pull the upstream image first.')
                services[name] = {'image': digests[0]}
        lockfile.write_text(json.dumps({'services': services}, indent=2) + '\n', encoding='utf-8')
        print(f'Pinned {len(services)} Dify service images by registry digest: {lockfile}')


if __name__ == '__main__':
    main()
