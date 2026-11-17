"""Offline tests for the release packager. No real plugin build or GitHub access."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "package-release.py"
ASSETS = (
    "main.js", "manifest.json", "styles.css", "LICENSE",
    "THIRD_PARTY_NOTICES.md", "rackdown-provenance.json",
    "licenses/netbox-CC0.txt", "licenses/netbox.lock.json",
)


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copyfile(SOURCE, self.root / "scripts" / "package-release.py")
        self.write_json("manifest.json", {
            "id": "rackdown", "version": "0.1.0", "minAppVersion": "1.0.0",
        })
        self.write_json("package.json", {"version": "0.1.0"})
        self.write_json("package-lock.json", {
            "version": "0.1.0", "packages": {"": {"version": "0.1.0"}},
        })
        self.write_json("versions.json", {"0.1.0": "1.0.0"})
        for asset in ASSETS:
            source = self.root / asset
            source.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                source.write_text(f"example {asset}\n", encoding="utf-8")
            built = self.root / "dist" / asset
            built.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, built)

    def write_json(self, path, data):
        (self.root / path).write_text(json.dumps(data), encoding="utf-8")

    def run_packager(self):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "package-release.py")],
            capture_output=True, text=True, check=False,
        )

    def test_release_contains_direct_assets_and_reproducible_zip(self):
        result = self.run_packager()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.root / ".rackdown" / "release" / "0.1.0"
        for asset in ("main.js", "manifest.json", "styles.css", "SHA256SUMS"):
            self.assertTrue((output / asset).is_file())
        archive = output / "rackdown-0.1.0.zip"
        with ZipFile(archive) as zipped:
            self.assertEqual(
                sorted(zipped.namelist()),
                sorted(f"rackdown/{asset}" for asset in ASSETS),
            )
            self.assertEqual(
                zipped.read("rackdown/manifest.json"),
                (self.root / "manifest.json").read_bytes(),
            )
        first_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertEqual(self.run_packager().returncode, 0)
        self.assertEqual(first_hash, hashlib.sha256(archive.read_bytes()).hexdigest())
        checksums = (output / "SHA256SUMS").read_text(encoding="utf-8")
        self.assertIn(first_hash + "  rackdown-0.1.0.zip", checksums)

    def test_mismatched_version_is_rejected(self):
        self.write_json("package.json", {"version": "0.1.1"})
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version differs", result.stderr)

    def test_stale_manifest_is_rejected(self):
        self.write_json("manifest.json", {
            "id": "rackdown", "version": "0.1.0", "minAppVersion": "1.0.1",
        })
        self.write_json("versions.json", {"0.1.0": "1.0.1"})
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Stale built asset", result.stderr)

    def test_missing_notice_is_rejected(self):
        (self.root / "dist" / "THIRD_PARTY_NOTICES.md").unlink()
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing or unsafe built asset", result.stderr)

    def set_release_version(self, version, min_app="1.0.0"):
        self.write_json("manifest.json", {
            "id": "rackdown", "version": version, "minAppVersion": min_app,
        })
        self.write_json("package.json", {"version": version})
        self.write_json("package-lock.json", {
            "version": version, "packages": {"": {"version": version}},
        })
        shutil.copyfile(self.root / "manifest.json", self.root / "dist" / "manifest.json")

    def test_future_patch_inherits_minimum_without_new_mapping(self):
        self.set_release_version("0.1.1")
        result = self.run_packager()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((
            self.root / ".rackdown" / "release" / "0.1.1" / "rackdown-0.1.1.zip"
        ).is_file())
        self.assertEqual(
            json.loads((self.root / "versions.json").read_text()),
            {"0.1.0": "1.0.0"},
        )

    def test_changed_minimum_requires_new_compatibility_entry(self):
        self.set_release_version("0.1.1", "1.2.0")
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("minAppVersion differs", result.stderr)
        self.write_json("versions.json", {
            "0.1.0": "1.0.0", "0.1.1": "1.2.0",
        })
        result = self.run_packager()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mapping_must_have_entry_at_or_before_release(self):
        self.write_json("versions.json", {"0.1.1": "1.0.0"})
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no entry for or before", result.stderr)

    def test_numeric_version_order_not_lexical(self):
        self.set_release_version("0.10.0", "1.2.0")
        self.write_json("versions.json", {
            "0.1.0": "1.0.0", "0.10.0": "1.2.0", "0.9.0": "1.1.0",
        })
        result = self.run_packager()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_version_and_compatibility_values_are_rejected(self):
        self.set_release_version("v0.1.1")
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("numeric x.y.z", result.stderr)
        self.set_release_version("0.1.0")
        self.write_json("versions.json", {"0.1.0": "not-a-version"})
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("minimum app version", result.stderr)

    def test_missing_compatibility_mapping_is_rejected(self):
        self.write_json("versions.json", {})
        result = self.run_packager()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least one compatibility entry", result.stderr)


if __name__ == "__main__":
    unittest.main()
