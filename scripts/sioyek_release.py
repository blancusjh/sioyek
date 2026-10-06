#!/usr/bin/env python3
"""Package, publish, and synchronize the personal Sioyek releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.parse
import zipfile

REPO = 'blancusjh/sioyek'
MANIFEST = 'sioyek-release.json'
CONFIG = Path.home() / '.config/sioyek-release/targets.json'
STATE = Path.home() / '.local/state/sioyek-release/installed.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'sioyek-release-sync'})
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def target_platform():
    if sys.platform == 'darwin' and platform.machine() == 'arm64':
        return 'macos-arm64'
    if sys.platform == 'linux' and platform.machine() == 'x86_64':
        os_release = Path('/etc/os-release').read_text()
        if re.search(r'^ID=["\']?arch["\']?$', os_release, re.M):
            return 'linux-x86_64-arch'
    raise RuntimeError('This release supports Apple Silicon Macs and Arch Linux x86_64.')


def pack(args):
    key = target_platform()
    bundle = args.bundle.resolve()
    stamp = bundle / ('Contents/Resources/BUILD-COMMIT' if key == 'macos-arm64' else 'BUILD-COMMIT')
    commit = args.commit or (stamp.read_text().strip() if stamp.exists() else '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise RuntimeError('Missing build commit: rebuild with the updated build script or supply --commit.')
    if stamp.exists() and stamp.read_text().strip() != commit:
        raise RuntimeError('Requested commit differs from the bundle build stamp.')
    args.output.mkdir(parents=True, exist_ok=True)
    name = 'sioyek-' + key + '-' + commit[:8] + ('.zip' if key == 'macos-arm64' else '.tar.gz')
    archive = args.output / name
    executable = bundle / ('Contents/MacOS/sioyek' if key == 'macos-arm64' else 'sioyek')
    if key == 'macos-arm64':
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(bundle), str(archive)], check=True)
    else:
        with tarfile.open(archive, 'w:gz') as stream:
            stream.add(bundle, arcname='sioyek')
    write_json(args.output / (key + '.json'), {'commit': commit, 'platform': key,
        'name': name, 'sha256': digest(archive), 'binary_sha256': digest(executable)})
    print(archive, flush=True)


def publish(args):
    entries = [json.loads((args.artifacts / (key + '.json')).read_text())
               for key in ['macos-arm64', 'linux-x86_64-arch']]
    commits = {entry['commit'] for entry in entries}
    if len(commits) != 1:
        raise RuntimeError('Mac and Linux builds must come from the same commit.')
    commit = commits.pop()
    for entry in entries:
        if digest(args.artifacts / entry['name']) != entry['sha256']:
            raise RuntimeError('Archive checksum changed: ' + entry['name'])
    manifest = args.artifacts / MANIFEST
    write_json(manifest, {'schema': 1, 'tag': args.tag, 'commit': commit,
                         'assets': {entry['platform']: entry for entry in entries}})
    notes = args.artifacts / 'release-notes.md'
    notes.write_text('Matching personal Sioyek builds from commit `' + commit + '`.\n\n'
        'Includes Apple Silicon macOS and Arch Linux x86_64 (PHANEX) builds. '
        'The Linux build uses the system Qt runtime. The Mac app is ad hoc signed.\n\n'
        'Run `sioyek-sync sync` on the Mac to update both configured machines. '
        'The release manifest records each archive and executable SHA-256.\n')
    files = [str(args.artifacts / entry['name']) for entry in entries] + [str(manifest)]
    exists = subprocess.run(['gh', 'release', 'view', args.tag, '--repo', REPO],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if exists:
        # Existing assets remain immutable; only add missing platform assets and metadata.
        info = json.loads(subprocess.check_output(['gh', 'release', 'view', args.tag,
                     '--repo', REPO, '--json', 'assets'], text=True))
        remote = {asset['name']: asset for asset in info['assets']}
        for path in files:
            name = Path(path).name
            if name in remote:
                if hashlib.sha256(fetch(remote[name]['url'])).hexdigest() != digest(path):
                    raise RuntimeError('Existing release asset differs; publish a new tag: ' + name)
            else:
                subprocess.run(['gh', 'release', 'upload', args.tag, path, '--repo', REPO], check=True)
    else:
        subprocess.run(['gh', 'release', 'create', args.tag, *files, '--repo', REPO,
            '--target', commit, '--title', 'Sioyek personal build ' + commit[:8],
            '--notes-file', str(notes), '--draft'], check=True)
        subprocess.run(['gh', 'release', 'edit', args.tag, '--repo', REPO,
                        '--draft=false', '--latest'], check=True)
    print('https://github.com/' + REPO + '/releases/tag/' + args.tag, flush=True)


def install_mac(archive, work, expected_binary):
    with zipfile.ZipFile(archive) as stream:
        for entry in stream.namelist():
            if entry.startswith('/') or '..' in Path(entry).parts:
                raise RuntimeError('Invalid ZIP path.')
    subprocess.run(['ditto', '-x', '-k', str(archive), str(work / 'unpacked')], check=True)
    bundle = work / 'unpacked/sioyek.app'
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
    if digest(bundle / 'Contents/MacOS/sioyek') != expected_binary:
        raise RuntimeError('Packaged executable checksum mismatch.')
    staged = Path(tempfile.mkdtemp(prefix='.sioyek-install-', dir='/Applications'))
    try:
        shutil.copytree(bundle, staged / 'sioyek.app', symlinks=True)
        destination = Path('/Applications/sioyek.app')
        backup = Path('/Applications/.sioyek-previous-' + str(time.time_ns()) + '.app')
        if destination.exists():
            destination.rename(backup)
        try:
            (staged / 'sioyek.app').rename(destination)
        except Exception:
            if backup.exists(): backup.rename(destination)
            raise
    finally:
        shutil.rmtree(staged)


def install_linux(archive, work, commit, expected_binary):
    with tarfile.open(archive) as stream:
        stream.extractall(work / 'unpacked', filter='data')
    bundle = work / 'unpacked/sioyek'
    if digest(bundle / 'sioyek') != expected_binary:
        raise RuntimeError('Packaged executable checksum mismatch.')
    libraries = subprocess.run(['ldd', str(bundle / 'sioyek')], capture_output=True, text=True, check=True)
    if 'not found' in libraries.stdout + libraries.stderr:
        raise RuntimeError('Missing runtime libraries:\n' + libraries.stdout + libraries.stderr)
    root = Path.home() / '.local/opt/sioyek'
    root.mkdir(parents=True, exist_ok=True)
    destination = root / commit[:8]
    staged = Path(tempfile.mkdtemp(prefix='.install-', dir=root))
    backup = root / (commit[:8] + '.previous-' + str(time.time_ns()))
    try:
        shutil.copytree(bundle, staged / 'sioyek', symlinks=True)
        if destination.exists(): destination.rename(backup)
        try:
            (staged / 'sioyek').rename(destination)
        except Exception:
            if backup.exists(): backup.rename(destination)
            raise
    finally:
        shutil.rmtree(staged)
    launcher = Path.home() / '.local/bin/sioyek'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    temporary = launcher.with_name('.sioyek-link-' + str(time.time_ns()))
    temporary.symlink_to(destination / 'sioyek')
    temporary.replace(launcher)
    desktop = Path.home() / '.local/share/applications/sioyek.desktop'
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nName=Sioyek\nType=Application\nTerminal=false\n'
        'Exec="' + str(launcher) + '" %f\nIcon=' + str(destination / 'sioyek-icon-linux.png') +
        '\nCategories=Office;Viewer;\nMimeType=application/pdf;\nStartupWMClass=sioyek\n')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(desktop.parent)], check=True)


def sync(args):
    ref = 'latest' if not args.tag else 'tags/' + urllib.parse.quote(args.tag, safe='')
    release = json.loads(fetch('https://api.github.com/repos/' + REPO + '/releases/' + ref))
    assets = {entry['name']: entry['browser_download_url'] for entry in release['assets']}
    if MANIFEST not in assets:
        raise RuntimeError('This release does not contain matching platform builds and a manifest.')
    manifest = json.loads(fetch(assets[MANIFEST]))
    commit = manifest['commit']
    if manifest.get('schema') != 1 or manifest['tag'] != release['tag_name'] or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise RuntimeError('Invalid release manifest.')
    key = target_platform()
    entry = manifest['assets'][key]
    if entry['name'] not in assets or entry['commit'] != commit:
        raise RuntimeError('Release asset does not match the manifest.')
    binary = Path('/Applications/sioyek.app/Contents/MacOS/sioyek') if key == 'macos-arm64' else Path.home() / '.local/bin/sioyek'
    installed = json.loads(STATE.read_text()) if STATE.exists() else {}
    matches = (binary.exists() and digest(binary) == entry['binary_sha256'] and
               installed.get('commit') == commit and installed.get('repo') == REPO and
               installed.get('archive_sha256') == entry['sha256'])
    print(key + ': ' + ('matches ' if matches else 'update available: ') + manifest['tag'] + ' (' + commit[:8] + ')', flush=True)
    if not args.check:
        if args.force or not matches:
            with tempfile.TemporaryDirectory(prefix='sioyek-release-') as folder:
                work = Path(folder)
                archive = work / 'download'
                archive.write_bytes(fetch(assets[entry['name']]))
                if digest(archive) != entry['sha256']:
                    raise RuntimeError('Downloaded archive checksum mismatch.')
                if key == 'macos-arm64': install_mac(archive, work, entry['binary_sha256'])
                else: install_linux(archive, work, commit, entry['binary_sha256'])
                if digest(binary) != entry['binary_sha256']:
                    raise RuntimeError('Installed executable checksum mismatch.')
            print('Installed ' + manifest['tag'] + '; reopen Sioyek to use the updated build.', flush=True)
        write_json(STATE, {'repo': REPO, 'tag': manifest['tag'], 'commit': commit, 'platform': key,
                          'binary_sha256': entry['binary_sha256'], 'archive_sha256': entry['sha256']})
    if not args.local_only and CONFIG.exists():
        targets = json.loads(CONFIG.read_text())['ssh_targets']
        for target in targets:
            remote = ['python3', '-', 'sync', '--tag', manifest['tag'], '--local-only']
            if args.check: remote.append('--check')
            if args.force: remote.append('--force')
            ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes']
            ssh += target.get('options', [])
            ssh += [target['host'], shlex.join(remote)]
            print('Synchronizing ' + target['host'], flush=True)
            subprocess.run(ssh, input=Path(__file__).read_text(), text=True, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('pack', help='Package an already compiled native build')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--commit', help='Known source commit for older bundles without a stamp')
    p.set_defaults(action=pack)
    p = commands.add_parser('publish', help='Publish matching Mac and Linux packages')
    p.add_argument('--artifacts', type=Path, required=True)
    p.add_argument('--tag', required=True)
    p.set_defaults(action=publish)
    p = commands.add_parser('sync', help='Update this machine and configured SSH targets')
    p.add_argument('--tag', help='Pin a release; otherwise use latest')
    p.add_argument('--check', action='store_true', help='Check versions without installing')
    p.add_argument('--force', action='store_true', help='Reinstall even when binary hashes match')
    p.add_argument('--local-only', action='store_true')
    p.set_defaults(action=sync)
    args = parser.parse_args()
    if getattr(args, 'tag', None) and not re.fullmatch(r'[A-Za-z0-9._-]+', args.tag):
        parser.error('Release tags may contain letters, numbers, dots, underscores and hyphens.')
    try:
        args.action(args)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, 'Error: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
