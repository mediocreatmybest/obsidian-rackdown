import { copyFile, cp, mkdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';
import { parseCataloguePayload } from '@rackdown/devices/full-catalogue';

import { build } from 'esbuild';

const packageDir = fileURLToPath(new URL('.', import.meta.url));
const distDir = join(packageDir, 'dist');
const encodedCatalogue = (
  await readFile(
    new URL(import.meta.resolve('@rackdown/devices/full-catalogue.b64')),
    'utf8',
  )
).trim();
// Validate the committed payload against the pinned catalogue source before
// bundling. The return value is intentionally discarded: this is a build gate.
parseCataloguePayload(
  JSON.parse(
    gunzipSync(Buffer.from(encodedCatalogue, 'base64')).toString('utf8'),
  ),
);

await rm(distDir, { recursive: true, force: true });
await mkdir(distDir, { recursive: true });

await build({
  absWorkingDir: packageDir,
  entryPoints: ['src/main.ts'],
  bundle: true,
  define: {
    __RACKDOWN_CATALOGUE_PAYLOAD__: JSON.stringify(encodedCatalogue),
  },
  external: ['obsidian'],
  platform: 'browser',
  format: 'cjs',
  target: 'es2021',
  outfile: join(distDir, 'main.js'),
});

for (const asset of ['manifest.json', 'styles.css']) {
  await copyFile(join(packageDir, asset), join(distDir, asset));
}

// Keep the source pin and code/data licences with every installable build.
for (const asset of ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'rackdown-provenance.json', 'licenses']) {
  await cp(join(packageDir, asset), join(distDir, asset), { recursive: true });
}
