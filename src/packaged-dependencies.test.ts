import { realpathSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fullCatalogueSource } from '@rackdown/devices/full-catalogue';
import { describe, expect, it } from 'vitest';
import { CatalogueProvider } from './catalogue.js';
import { prepareRackDown, renderPreparedRackDown } from './render-rackdown.js';

describe('packaged RackDown dependencies', () => {
  it('loads installed public exports and renders with the full offline catalogue', async () => {
    const project = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
    const core = realpathSync(fileURLToPath(import.meta.resolve('@rackdown/core')));
    expect(core).toBe(join(project, 'node_modules/@rackdown/core/dist/index.mjs'));
    const pin = JSON.parse(readFileSync(new URL('../rackdown-provenance.json', import.meta.url), 'utf8'));
    expect(fullCatalogueSource.ref).toBe(pin.catalogue.commit);
    expect(fullCatalogueSource.repository).toBe(pin.catalogue.repository);
    const encoded = readFileSync(new URL(import.meta.resolve('@rackdown/devices/full-catalogue.b64')), 'utf8');
    const catalogue = await new CatalogueProvider(encoded).load();
    expect(catalogue.scope).toBe('full');
    expect(Object.keys(catalogue.devices).length).toBeGreaterThan(6000);
    expect(Object.keys(catalogue.racks).length).toBeGreaterThan(100);

    const prepared = prepareRackDown(
      'rack "Example" 8U\n4 dell-poweredge-r740 "Host" as host',
      catalogue.devices,
    );
    expect(prepared.diagnostics).toEqual([]);
    expect(prepared.layout.devices[0]?.uHeight).toBe(2);
    expect(renderPreparedRackDown(prepared).svg).toContain('Host');
  });
});
