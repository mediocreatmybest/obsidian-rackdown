import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const script = new URL('./prepare-rackdown.mjs', import.meta.url);
const provenance = JSON.parse(readFileSync(new URL('../rackdown-provenance.json', import.meta.url), 'utf8'));

function fixture(t, changes = {}) {
  const root = mkdtempSync(join(tmpdir(), 'rackdown-preparation-test-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, 'scripts'));
  copyFileSync(script, join(root, 'scripts/prepare-rackdown.mjs'));
  writeFileSync(join(root, 'rackdown-provenance.json'), JSON.stringify({ ...provenance, ...changes }));
  return root;
}

function run(root) {
  return spawnSync(process.execPath, [join(root, 'scripts/prepare-rackdown.mjs')], { encoding: 'utf8' });
}

test('rejects a moving ref before fetching or creating staging', (t) => {
  const root = fixture(t, { commit: 'main' });
  const result = run(root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /full 40-character commit SHA/);
  assert.equal(existsSync(join(root, '.rackdown')), false);
});

test('refuses symlinked staging and leaves its target untouched', (t) => {
  const root = fixture(t);
  const outside = mkdtempSync(join(tmpdir(), 'rackdown-unrelated-'));
  t.after(() => rmSync(outside, { recursive: true, force: true }));
  writeFileSync(join(outside, 'keep.txt'), 'unrelated work');
  symlinkSync(outside, join(root, '.rackdown'), 'dir');
  const result = run(root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /must be a real directory/);
  assert.equal(readFileSync(join(outside, 'keep.txt'), 'utf8'), 'unrelated work');
});
