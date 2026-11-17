#!/usr/bin/env python3
"""Create the assets for a manual GitHub release of the built Obsidian plugin.

No GitHub API, npm publishing, network access, or changes to the build output.
Run after npm run build && npm run test:dist.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RUNTIME_ASSETS = ("main.js", "manifest.json", "styles.css")
NOTICE_ASSETS = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "rackdown-provenance.json",
    "licenses/netbox-CC0.txt",
    "licenses/netbox.lock.json",
)
INSTALL_ASSETS = RUNTIME_ASSETS + NOTICE_ASSETS


def fail(message: str) -> None:
    raise ValueError(message)


def json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version_tuple(value: object, field: str) -> tuple[int, int, int]:
    """Obsidian plugin and app versions use numeric x.y.z."""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value
    ):
        fail(f"{field} must use numeric x.y.z without a leading v")
    return tuple(int(part) for part in value.split("."))


def validate_compatibility(versions: object, version: str, min_app: object) -> None:
    """Only a changed minAppVersion requires a new versions.json entry."""
    current = version_tuple(version, "Manifest version")
    version_tuple(min_app, "Manifest minAppVersion")
    if not isinstance(versions, dict) or not versions:
        fail("versions.json must contain at least one compatibility entry")
    eligible: list[tuple[tuple[int, int, int], str]] = []
    for plugin_version, required_app in versions.items():
        parsed = version_tuple(plugin_version, "versions.json plugin version")
        version_tuple(required_app, "versions.json minimum app version")
        if parsed <= current:
            eligible.append((parsed, required_app))
    if not eligible:
        fail("versions.json has no entry for or before this plugin version")
    effective_min = max(eligible, key=lambda entry: entry[0])[1]
    if effective_min != min_app:
        fail("versions.json latest applicable minAppVersion differs from manifest.json")


def validate() -> str:
    manifest = json_file(ROOT / "manifest.json")
    package = json_file(ROOT / "package.json")
    lock = json_file(ROOT / "package-lock.json")
    versions = json_file(ROOT / "versions.json")
    version = manifest.get("version")
    if manifest.get("id") != "rackdown":
        fail("Plugin ID must remain rackdown")
    version_tuple(version, "Manifest version")
    if package.get("version") != version:
        fail("package.json version differs from manifest.json")
    if lock.get("version") != version or lock.get("packages", {}).get("", {}).get("version") != version:
        fail("package-lock.json version differs from manifest.json")
    validate_compatibility(versions, version, manifest.get("minAppVersion"))
    for filename in INSTALL_ASSETS:
        source = DIST / filename
        if not source.is_file() or source.is_symlink():
            fail(f"Missing or unsafe built asset: dist/{filename}")
        if filename != "main.js" and source.read_bytes() != (ROOT / filename).read_bytes():
            fail(f"Stale built asset, rebuild before packaging: dist/{filename}")
    if not (DIST / "main.js").stat().st_size:
        fail("Built main.js is empty")
    return version


def make_zip(path: Path) -> None:
    # Fixed entry order, timestamps and modes keep packaging reproducible.
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for filename in sorted(INSTALL_ASSETS):
            info = ZipInfo(f"rackdown/{filename}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (DIST / filename).read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    version = validate()
    destination = ROOT / ".rackdown" / "release" / version
    destination.mkdir(parents=True, exist_ok=True)
    archive_name = f"rackdown-{version}.zip"
    for filename in RUNTIME_ASSETS:
        shutil.copyfile(DIST / filename, destination / filename)
    make_zip(destination / archive_name)
    published = [*RUNTIME_ASSETS, archive_name]
    (destination / "SHA256SUMS").write_text(
        "".join(f"{sha256(destination / filename)}  {filename}\n" for filename in published),
        encoding="utf-8",
    )
    print(f"Prepared {destination.relative_to(ROOT)}")
    for filename in (*published, "SHA256SUMS"):
        print(f"  {filename}")
    print(f"Use exact GitHub release tag: {version} (no leading v)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"release packaging failed: {exc}", file=sys.stderr)
        sys.exit(1)
