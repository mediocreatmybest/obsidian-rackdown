import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { lstat, mkdir, mkdtemp, readFile, rename, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const project = fileURLToPath(new URL('../', import.meta.url));
const pin = JSON.parse(await readFile(join(project, 'rackdown-provenance.json'), 'utf8'));
assert.match(pin.commit, /^[0-9a-f]{40}$/, 'RackDown must use a full 40-character commit SHA.');
assert.equal(pin.repository, 'https://github.com/mediocreatmybest/RackDown.git');
assert.match(pin.packageManager, /^pnpm@\d+\.\d+\.\d+$/);

const generated = join(project, '.rackdown');
await mkdir(generated, { recursive: true });
assert.ok((await lstat(generated)).isDirectory(), '.rackdown must be a real directory, not a symlink.');
const staging = await mkdtemp(join(generated, 'upstream-'));
const env = {
  ...process.env,
  COREPACK_HOME: join(generated, 'corepack'),
  PNPM_HOME: join(generated, 'pnpm'),
};

function run(command, args, cwd = staging) {
  execFileSync(command, args, { cwd, env, stdio: 'inherit' });
}

function output(command, args, cwd = staging) {
  return execFileSync(command, args, { cwd, env, encoding: 'utf8' }).trim();
}

async function json(path) {
  return JSON.parse(await readFile(join(staging, path), 'utf8'));
}

try {
  run('git', ['init', '--quiet']);
  run('git', ['fetch', '--depth=1', pin.repository, pin.commit]);
  run('git', ['checkout', '--quiet', '--detach', 'FETCH_HEAD']);
  assert.equal(output('git', ['rev-parse', 'HEAD']), pin.commit, 'Fetched HEAD must match the pin.');
  assert.equal((await json('package.json')).packageManager, pin.packageManager);
  assert.equal(output('corepack', ['pnpm', '--version']), pin.packageManager.slice('pnpm@'.length));
  const catalogue = await json('upstream/netbox.lock.json');
  assert.equal(catalogue.source, pin.catalogue.repository);
  assert.equal(catalogue.ref, pin.catalogue.commit);
  assert.equal(catalogue.license, pin.catalogue.license);

  // The upstream package manager and frozen lockfile own the build tool versions.
  run('corepack', ['pnpm', 'install', '--frozen-lockfile', '--filter', '@rackdown/core...']);
  run('corepack', ['pnpm', '--filter', '@rackdown/core', 'build']);
  const archives = join(staging, 'archives');
  await mkdir(archives);
  for (const name of ['core', 'devices']) {
    const directory = join(staging, `packages/rackdown-${name}`);
    const manifest = await json(`packages/rackdown-${name}/package.json`);
    assert.equal(manifest.name, `@rackdown/${name}`);
    assert.equal(manifest.version, pin.packages[manifest.name]);
    assert.equal(manifest.private, true, 'Prepared packages must remain private.');
    run('corepack', ['pnpm', 'pack', '--pack-destination', archives], directory);
  }
  // Only replace the consumed archives after both packages have packed successfully.
  for (const name of ['core', 'devices']) {
    const version = pin.packages[`@rackdown/${name}`];
    await rename(join(archives, `rackdown-${name}-${version}.tgz`), join(generated, `${name}.tgz`));
  }
  console.log(`Prepared private core and devices archives from ${pin.commit}. Nothing published.`);
} finally {
  // This invocation owns only the fresh mkdtemp directory, never another checkout.
  await rm(staging, { recursive: true, force: true });
}
