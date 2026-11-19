"""Execute workflow shell blocks against local fixtures and a stateful GitHub stub."""
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

import test_package_release

ROOT = Path(__file__).resolve().parents[1]
SHA = '1234567890abcdef1234567890abcdef12345678'


def blocks(text):
    # Extract literal run blocks without introducing a YAML runtime dependency.
    return [re.sub(r'^          ', '', match, flags=re.M)
            for match in re.findall(r'        run: \|\n((?:          .*\n|\n)+)', text)]


GH_STUB = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ['GH_STATE'])
s = json.loads(path.read_text())
a = sys.argv[1:]
s['calls'].append(a)
def finish(code=0):
    path.write_text(json.dumps(s))
    sys.exit(code)
if a[:2] == ['api', '--paginate']:
    if s.get('list_failure'): finish(1)
    print('\\n'.join(s['releases']))
elif a[:3] == ['api', '--method', 'POST']:
    assert a[3].endswith('/git/refs'), a
    fields = dict(arg.split('=', 1) for arg in a if arg.startswith(('ref=', 'sha=')))
    tag = fields['ref'].removeprefix('refs/tags/')
    if tag in s['tags']: finish(1)
    s['tags'][tag] = fields['sha']
elif a[0] == 'api' and '/git/ref/tags/' in a[1]:
    tag = a[1].split('/git/ref/tags/')[1]
    print(s.get('wrong_sha', s['tags'][tag]))
elif a[:2] == ['release', 'create']:
    tag = a[2]
    if tag in s['releases']: finish(1)
    if s.get('create_failure') == 'before': finish(1)
    s['releases'].append(tag)
    s['created'] = a
    if s.get('create_failure'): finish(1)
else:
    raise AssertionError(a)
finish()
'''


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_package_release.ReleasePackagingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name, script in {
            'gh': GH_STUB,
            'git': '#!/bin/sh\ncase "$*" in\n"rev-parse HEAD") echo ' + SHA + ';;\n"check-ref-format "*) exit 0;;\n*) exit 1;;\nesac\n',
            'date': '#!/bin/sh\ntest "$*" = "-u +%Y%m%d" || exit 1\necho 20261119\n',
        }.items():
            path = self.bin / name
            path.write_text(script)
            path.chmod(0o755)
        self.state = self.root / 'github.json'
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'GH_STATE': str(self.state), 'GH_REPO': 'example/plugin',
                    'GH_TOKEN': 'stub-only', 'GITHUB_SHA': SHA,
                    'GITHUB_REF': 'refs/heads/main'}

    def reset(self, **changes):
        self.state.write_text(json.dumps({'tags': {}, 'releases': [], 'calls': [], **changes}))

    def state_data(self):
        return json.loads(self.state.read_text())

    def workflow(self, name):
        return (ROOT / '.github/workflows' / name).read_text()

    def run_creation(self, name, **env):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', blocks(self.workflow(name))[-1]],
                              cwd=self.root, env={**self.env, **env}, capture_output=True, text=True)

    def prepare(self, version='0.1.0'):
        self.fixture.set_release_version(version)
        result = self.fixture.run_packager()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_workflow_structure_and_shell_syntax(self):
        pipeline = ['prepare:rackdown', 'ci', 'typecheck', 'test', 'build',
                    'test:dist', 'test:release', 'package:release']
        for name in ('release.yml', 'prerelease.yml'):
            text = self.workflow(name)
            self.assertIn('on:\n  workflow_dispatch:\n', text)
            self.assertIn('group: draft-plugin-release\n  cancel-in-progress: false', text)
            self.assertIn('ref: ${{ github.sha }}', text)
            self.assertIn('persist-credentials: false', text)
            self.assertIn('run: test "$GITHUB_REF" = refs/heads/main', text)
            self.assertEqual(text.count('GH_TOKEN:'), 1)
            self.assertGreater(text.index('GH_TOKEN:'), text.index('Verify release assets'))
            commands = [f'npm {step}' if step in ('ci', 'test') else f'npm run {step}' for step in pipeline]
            positions = [text.index(command + '\n') for command in commands]
            self.assertEqual(positions, sorted(positions))
            for block in blocks(text):
                result = subprocess.run(['bash', '-n'], input=block, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            rejected = subprocess.run(['bash', '-e', '-c', 'test "$GITHUB_REF" = refs/heads/main'],
                                      env={**self.env, 'GITHUB_REF': 'refs/heads/feature'})
            self.assertNotEqual(rejected.returncode, 0)

    def test_future_versions_flags_assets_and_duplicate_invocation(self):
        self.prepare('1.2.3')
        for name, tag in [('release.yml', '1.2.3'), ('prerelease.yml', '1.2.3-pre.20261119.1234567')]:
            with self.subTest(name=name):
                self.reset()
                result = self.run_creation(name)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = self.state_data()
                self.assertEqual(state['tags'], {tag: SHA})
                args = state['created']
                self.assertEqual(args[2], tag)
                for flag in ('--draft', '--verify-tag'):
                    self.assertIn(flag, args)
                self.assertIn('--prerelease' if name == 'prerelease.yml' else '--prerelease=false', args)
                self.assertEqual(args[args.index('--target') + 1], SHA)
                expected = ['main.js', 'manifest.json', 'styles.css', 'rackdown-1.2.3.zip', 'SHA256SUMS']
                self.assertEqual(args[-5:], [f'.rackdown/release/1.2.3/{asset}' for asset in expected])
                self.assertTrue(all((self.root / asset).is_file() for asset in args[-5:]))
                self.assertNotEqual(self.run_creation(name).returncode, 0)
                self.assertEqual(self.state_data()['releases'], [tag])
                self.assertEqual(self.state_data()['tags'], {tag: SHA})

    def test_failures_never_overwrite_or_clean_up(self):
        self.prepare()
        for name, tag in [('release.yml', '0.1.0'), ('prerelease.yml', '0.1.0-pre.20261119.1234567')]:
            for changes, env in [
                ({}, {'GITHUB_REF': 'refs/heads/feature'}),
                ({}, {'GITHUB_SHA': 'f' * 40}),
                ({'tags': {tag: 'old-sha'}}, {}),
                ({'releases': [tag]}, {}),
                ({'list_failure': True}, {}),
                ({'wrong_sha': 'f' * 40}, {}),
                ({'create_failure': True}, {}),
                ({'create_failure': 'before'}, {}),
            ]:
                with self.subTest(name=name, changes=changes, env=env):
                    self.reset(**changes)
                    result = self.run_creation(name, **env)
                    self.assertNotEqual(result.returncode, 0)
                    state = self.state_data()
                    if changes.get('create_failure'):
                        self.assertEqual(state['tags'], {tag: SHA})
                        self.assertEqual(state['releases'], [] if changes['create_failure'] == 'before' else [tag])
                        self.assertNotEqual(self.run_creation(name).returncode, 0)
                    elif changes.get('wrong_sha'):
                        self.assertEqual(state['tags'], {tag: SHA})
                        self.assertNotIn('created', state)
                    else:
                        self.assertEqual(state['tags'], changes.get('tags', {}))
                        self.assertEqual(state['releases'], changes.get('releases', []))
                        self.assertNotIn('created', state)
                    if env:
                        self.assertEqual(state['calls'], [])

    def test_version_mismatch_blocks_packaging(self):
        for filename, content in [('package.json', {'version': '9.9.9'}),
                                  ('package-lock.json', {'version': '9.9.9', 'packages': {'': {'version': '0.1.0'}}}),
                                  ('package-lock.json', {'version': '0.1.0', 'packages': {'': {'version': '9.9.9'}}})]:
            self.fixture.set_release_version('0.1.0')
            self.fixture.write_json(filename, content)
            result = self.fixture.run_packager()
            self.assertNotEqual(result.returncode, 0, filename)
            self.assertIn('version differs', result.stderr)


if __name__ == '__main__':
    unittest.main()
