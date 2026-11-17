# Third-party notices

The Obsidian adapter, bundled `@rackdown/core` and catalogue loader code come from
[RackDown](https://github.com/mediocreatmybest/RackDown) and are licensed under
AGPL-3.0-only. The complete licence is in [LICENSE](LICENSE). The exact source
commit, package versions and extraction path are in
[rackdown-provenance.json](rackdown-provenance.json). Plugin source is preserved
from that commit; local changes concern dependency preparation, configuration,
distribution notices and verification.

Catalogue data comes from the
[NetBox Community Device Type Library](https://github.com/netbox-community/devicetype-library)
at `f2d95de24cb3bdd780b93bd7d46d489be3789a8a`, under CC0-1.0. Its contributors
maintain the hardware definitions used for optional enrichment. The upstream
licence is reproduced in [licenses/netbox-CC0.txt](licenses/netbox-CC0.txt), with
its source pin and licence blob in [licenses/netbox.lock.json](licenses/netbox.lock.json).
RackDown is independent of the NetBox project and hardware manufacturers.

Obsidian is provided by the host application and remains external to the bundle.
Build and test tools are development dependencies; they are not installed in the
vault or downloaded when the plugin runs.

When redistributing a build, retain these notices and provide the corresponding
source for the adapter and bundled AGPL code, including local build scripts and
the recorded upstream commit, as required by the licence. No public release or
package publication is performed by this project.
