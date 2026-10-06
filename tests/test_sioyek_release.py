import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release', Path(__file__).parents[1] / 'scripts/sioyek_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def fixture(self, home, **options):
        commit = 'a' * 40
        binary = home / '.local/bin/sioyek'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'existing working app')
        manifest = {'schema': 1, 'tag': 'personal-test', 'commit': commit,
                    'assets': {'linux-x86_64-arch': {'commit': commit, 'name': 'linux.tar.gz',
                        'sha256': '0' * 64, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}}}
        info = {'tag_name': 'personal-test', 'assets': [
            {'name': release.MANIFEST, 'browser_download_url': 'https://test/manifest'},
            {'name': 'linux.tar.gz', 'browser_download_url': 'https://test/archive'}]}
        def fetch(url):
            if url.endswith('/latest'): return json.dumps(info).encode()
            if url == 'https://test/manifest': return json.dumps(manifest).encode()
            if url == 'https://test/archive': return b'corrupted download'
            raise AssertionError(url)
        return binary, fetch, argparse.Namespace(tag=None, check=False, force=False, local_only=True, **options)

    def test_corrupt_download_does_not_replace_app_or_mark_installed(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            binary, fetch, args = self.fixture(home)
            args.force = True
            state = home / 'installed.json'
            with patch.object(Path, 'home', return_value=home), patch.object(release, 'fetch', side_effect=fetch), \
                 patch.object(release, 'STATE', state), patch.object(release, 'target_platform', return_value='linux-x86_64-arch'), \
                 patch.object(release, 'install_linux') as installer:
                with self.assertRaisesRegex(RuntimeError, 'archive checksum mismatch'):
                    release.sync(args)
                installer.assert_not_called()
            self.assertEqual(binary.read_bytes(), b'existing working app')
            self.assertFalse(state.exists())

    def test_both_machines_are_pinned_to_the_same_release(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            _, fetch, args = self.fixture(home)
            args.check, args.local_only = True, False
            config = home / 'targets.json'
            config.write_text(json.dumps({'ssh_targets': [{'host': 'user@machine'}]}))
            with patch.object(Path, 'home', return_value=home), patch.object(release, 'fetch', side_effect=fetch), \
                 patch.object(release, 'CONFIG', config), patch.object(release, 'STATE', home / 'installed.json'), \
                 patch.object(release, 'target_platform', return_value='linux-x86_64-arch'), \
                 patch.object(release.subprocess, 'run') as run:
                release.sync(args)
            remote = run.call_args.args[0][-1]
            self.assertIn('--tag personal-test', remote)
            self.assertIn('--check', remote)
            self.assertIn('--local-only', remote)

    def test_new_resources_are_downloaded_even_when_binary_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            _, fetch, args = self.fixture(home)
            state = home / 'installed.json'
            state.write_text(json.dumps({'repo': release.REPO, 'commit': 'a' * 40,
                                         'archive_sha256': '1' * 64}))
            with patch.object(Path, 'home', return_value=home), patch.object(release, 'fetch', side_effect=fetch), \
                 patch.object(release, 'STATE', state), patch.object(release, 'target_platform', return_value='linux-x86_64-arch'):
                with self.assertRaisesRegex(RuntimeError, 'archive checksum mismatch'):
                    release.sync(args)
            self.assertEqual(json.loads(state.read_text())['archive_sha256'], '1' * 64)

    def test_publish_rejects_builds_from_different_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for key, commit in [('macos-arm64', 'a' * 40), ('linux-x86_64-arch', 'b' * 40)]:
                (root / (key + '.json')).write_text(json.dumps({'commit': commit}))
            with patch.object(release.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'same commit'):
                    release.publish(argparse.Namespace(artifacts=root, tag='personal-test'))
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
