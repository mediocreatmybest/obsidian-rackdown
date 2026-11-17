import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');

test('installable distribution carries unchanged assets, licences and provenance', () => {
  for (const path of [
    'manifest.json', 'styles.css', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'rackdown-provenance.json', 'licenses/netbox-CC0.txt', 'licenses/netbox.lock.json',
  ]) {
    assert.equal(read(`dist/${path}`), read(path));
  }
  const manifest = JSON.parse(read('dist/manifest.json'));
  const sourceManifest = JSON.parse(read('manifest.json'));
  const pkg = JSON.parse(read('package.json'));
  const lock = JSON.parse(read('package-lock.json'));
  assert.equal(manifest.id, 'rackdown');
  assert.equal(manifest.version, sourceManifest.version);
  assert.equal(manifest.version, pkg.version);
  assert.equal(manifest.version, lock.version);
  assert.equal(manifest.version, lock.packages[''].version);
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
});

test('built plugin loads with only Obsidian supplied and registers the existing fence', async () => {
  class Plugin {
    async loadData() { return { theme: 'dark', connectionThickness: 2.75 }; }
    addSettingTab(tab) { this.tab = tab; }
    registerMarkdownCodeBlockProcessor(fence, processor) {
      this.fence = fence;
      this.processor = processor;
    }
  }
  const module = { exports: {} };
  vm.runInNewContext(read('dist/main.js'), {
    module,
    exports: module.exports,
    require(specifier) {
      assert.equal(specifier, 'obsidian', `Unbundled runtime dependency: ${specifier}`);
      return {
        Plugin,
        MarkdownRenderChild: class {},
        PluginSettingTab: class {},
        Modal: class {},
      };
    },
  });
  const instance = new module.exports.default();
  await instance.onload();
  assert.equal(instance.fence, 'rackdown');
  assert.equal(typeof instance.processor, 'function');
  assert.ok(instance.tab);
  assert.equal(instance.settings.theme, 'dark');
  assert.equal(instance.settings.connectionThickness, 2.75);
  // The full offline payload is in the actual installable bundle.
  const encoded = readFileSync(new URL(import.meta.resolve('@rackdown/devices/full-catalogue.b64')), 'utf8').trim();
  assert.ok(read('dist/main.js').includes(encoded));
});
