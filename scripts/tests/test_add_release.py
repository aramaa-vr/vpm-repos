"""Offline behavior tests: python -B -m unittest discover -s scripts/tests -v."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import add_release as tool


PACKAGE = "jp.aramaa.player-carry-and-throw"


def manifest(version="0.2.0"):
    return {"name": PACKAGE, "version": version, "displayName": "だこちてギミック【ワールド版】",
            "description": "Read from the ZIP, not the previous version",
            "author": {"name": "あらまあ"}, "license": "See LICENSE.md file",
            "vpmDependencies": {"example.dependency": ">=1.0.0"}}


class LocalReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.listing_path, self.latest_path, self.index_path = (self.root/name for name in ['vpm.json', 'latest.json', 'index.json'])
        self.listing = {'name': 'Existing listing', 'packages': {'another.package': {'versions': {'9.0.0': {'keep': True}}}}}
        self.latest = {'schemaVersion': 1, 'packages': [{'id': 'another.package', 'version': '9.0.0'}]}
        self.index = {'name': 'Distribution index', 'url': 'https://example.org/index.json', 'packages': {PACKAGE: {'versions': {}}}}
        self.write_inputs()
        self.make_zip()

    def write_inputs(self):
        for path, value in [(self.listing_path, self.listing), (self.latest_path, self.latest), (self.index_path, self.index)]:
            path.write_bytes(tool.encode_json(value, 2))

    def make_zip(self, version='0.2.0-beta.2', changes=None, filename=None, extra='original', root_name='package.json'):
        self.version = version
        self.package = {**manifest(version), **(changes or {})}
        self.archive = self.root/(filename or f'{PACKAGE}-{version}.zip')
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr(root_name, json.dumps(self.package, ensure_ascii=False))
            archive.writestr('README.md', extra)

    def run_local(self, *extra, tag=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return tool.main(['--repo', 'owner/repo', '--tag', tag or self.version, '--zip', str(self.archive),
                              '--path', str(self.listing_path), '--latest-path', str(self.latest_path),
                              '--index-path', str(self.index_path), *extra])

    def snapshot(self):
        return tuple(path.read_bytes() for path in [self.listing_path, self.latest_path, self.index_path])

    def test_stable_alpha_beta_use_same_zip_entry_in_all_outputs(self):
        for version in ['0.2.0', '0.2.0-alpha.1', '0.2.0-beta.2']:
            with self.subTest(version=version):
                self.write_inputs()
                self.make_zip(version)
                self.assertEqual(self.run_local(), 0)
                entry = {**self.package, 'url': f'https://github.com/owner/repo/releases/download/{version}/{self.archive.name}',
                         'zipSHA256': hashlib.sha256(self.archive.read_bytes()).hexdigest()}
                listing = tool.read_json(self.listing_path.read_bytes())
                self.assertEqual(listing['packages'][PACKAGE]['versions'][version], entry)
                self.assertEqual(tool.read_json(self.index_path.read_bytes())['packages'][PACKAGE]['versions'][version], entry)
                self.assertEqual(listing['packages']['another.package'], self.listing['packages']['another.package'])
                self.assertEqual(tool.read_json(self.latest_path.read_bytes())['packages'], self.latest['packages']+[{'id': PACKAGE, 'version': version}])
                self.assertEqual(tool.read_json(self.index_path.read_bytes())['url'], self.index['url'])

    def test_dry_run_and_identical_rerun_do_not_write(self):
        before = self.snapshot()
        self.assertEqual(self.run_local('--dry-run'), 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.run_local(), 0)
        before = self.snapshot()
        with patch.object(tool, 'write_changes') as writes:
            self.assertEqual(self.run_local(), 0)
            writes.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_prerelease_order_and_older_version_keep_latest(self):
        versions = ['0.2.0-alpha.1', '0.2.0-beta.2', '0.2.0-beta.10', '0.2.0-rc.1', '0.2.0']
        for version in versions:
            self.make_zip(version)
            self.assertEqual(self.run_local(), 0)
            self.assertEqual(tool.read_json(self.latest_path.read_bytes())['packages'][-1]['version'], version)
        self.make_zip('0.1.99')
        self.assertEqual(self.run_local(), 0)
        self.assertEqual(tool.read_json(self.latest_path.read_bytes())['packages'][-1]['version'], '0.2.0')
        self.assertEqual(set(tool.read_json(self.listing_path.read_bytes())['packages'][PACKAGE]['versions']), set(versions+['0.1.99']))

    def test_compact_latest_changes_only_the_target_version(self):
        original = ('{\n  "schemaVersion": 1,\n  "packages": [\n'
                    '    { "id": "another.package", "version": "9.0.0" },\n'
                    '    { "id": "' + PACKAGE + '", "version": "0.1.99" }\n'
                    '  ]\n}\n').encode('utf-8')
        self.latest_path.write_bytes(original)
        self.assertEqual(self.run_local(), 0)
        self.assertEqual(self.latest_path.read_bytes(),
                         original.replace(b'0.1.99', self.version.encode('utf-8')))

    def test_first_latest_entry_preserves_extra_top_level_metadata(self):
        self.latest = {'schemaVersion': 1, 'packages': [],
                       'metadata': {'description': '既存の情報', 'enabled': True}}
        self.write_inputs()
        self.assertEqual(self.run_local(), 0)
        self.assertEqual(tool.read_json(self.latest_path.read_bytes()),
                         {**self.latest, 'packages': [{'id': PACKAGE, 'version': self.version}]})

    def test_local_input_mismatches_and_unsafe_options_do_not_write(self):
        cases = [({'changes': {'version': '0.2.0'}}, {}, ()),
                 ({'filename': 'wrong.zip'}, {}, ()),
                 ({'changes': {'url': 'https://example.org/stale.zip'}}, {}, ()),
                 ({'changes': {'zipSHA256': 'self hash'}}, {}, ()),
                 ({'root_name': 'package/package.json'}, {}, ()),
                 ({}, {'tag': '0.2.0-beta.01'}, ()),
                 ({}, {'tag': 'v0.2.0-beta.2'}, ()),
                 ({}, {}, ('--index-path', str(self.listing_path)))]
        for zip_options, call_options, extra in cases:
            with self.subTest(zip_options=zip_options, call_options=call_options, extra=extra):
                self.make_zip(**zip_options)
                before = self.snapshot()
                self.assertEqual(self.run_local(*extra, **call_options), 1)
                self.assertEqual(self.snapshot(), before)

    def test_registered_version_conflicts_preserve_all_three_files(self):
        self.assertEqual(self.run_local(), 0)
        before = self.snapshot()
        self.make_zip(extra='different bytes at the same version')
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_distribution_index_conflict_prevents_any_writes(self):
        self.index['packages'][PACKAGE]['versions'][self.version] = {**self.package, 'description': 'different'}
        self.write_inputs()
        before = self.snapshot()
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_third_file_failure_restores_listing_and_latest(self):
        before = self.snapshot()
        replace = os.replace
        def fail_index(source, target):
            if Path(target) == self.index_path:
                raise OSError('simulated index write failure')
            return replace(source, target)
        with patch.object(tool.os, 'replace', side_effect=fail_index):
            self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)


    def test_same_version_edited_listing_metadata_is_rejected(self):
        self.assertEqual(self.run_local(), 0)
        data = tool.read_json(self.listing_path.read_bytes())
        data["packages"][PACKAGE]["versions"][self.version]["description"] = "manually edited"
        self.listing_path.write_bytes(tool.encode_json(data, 4))
        before = self.snapshot()
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_missing_latest_uses_highest_registered_version(self):
        self.listing["packages"][PACKAGE] = {"versions": {"2.0.0": manifest("2.0.0")}}
        self.write_inputs()
        self.assertEqual(self.run_local(), 0)
        self.assertEqual(tool.read_json(self.latest_path.read_bytes())["packages"][-1],
                         {"id": PACKAGE, "version": "2.0.0"})

    def test_invalid_latest_fails_before_any_write(self):
        self.latest_path.write_text('{"schemaVersion": 2, "packages": []}', encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_json_key_is_rejected(self):
        self.listing_path.write_text('{"packages": {}, "packages": {}}', encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_second_file_write_failure_restores_first_file(self):
        before = self.snapshot()
        before_files = set(self.root.iterdir())
        replace = os.replace
        def fail_latest(source, target):
            if Path(target) == self.latest_path:
                raise OSError("simulated second-file failure")
            return replace(source, target)
        with patch.object(tool.os, "replace", side_effect=fail_latest):
            self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(set(self.listing_path.parent.iterdir()), before_files)

    def test_concurrent_edit_is_not_overwritten(self):
        before_listing, before_latest, _ = self.snapshot()
        self.latest_path.write_bytes(b"concurrent edit")
        with self.assertRaisesRegex(ValueError, "File changed"):
            tool.write_changes([(self.listing_path, before_listing, b"new listing"),
                                (self.latest_path, before_latest, b"new latest")])
        self.assertEqual(self.listing_path.read_bytes(), before_listing)
        self.assertEqual(self.latest_path.read_bytes(), b"concurrent edit")

    def test_failed_rollback_keeps_a_recoverable_original(self):
        original_listing, original_latest, _ = self.snapshot()
        replace = os.replace
        calls = 0
        def fail_after_first(source, target):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("simulated write and rollback failure")
            return replace(source, target)
        with patch.object(tool.os, "replace", side_effect=fail_after_first), \
             self.assertRaisesRegex(RuntimeError, "Original data preserved"):
            tool.write_changes([(self.listing_path, original_listing, b"new listing"),
                                (self.latest_path, original_latest, b"new latest")])
        recovery = list(self.listing_path.parent.glob(".vpm.json.*.tmp"))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0].read_bytes(), original_listing)
        self.assertEqual(self.latest_path.read_bytes(), original_latest)

    def test_zip_is_required_before_reading_any_inputs(self):
        before = self.snapshot()
        errors = io.StringIO()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No input should be read')), \
             contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as result:
            tool.main(['--repo', 'owner/repo', '--tag', self.version])
        self.assertEqual(result.exception.code, 2)
        self.assertIn('--zip', errors.getvalue())
        self.assertEqual(self.snapshot(), before)

    def test_removed_asset_option_is_rejected(self):
        before = self.snapshot()
        with self.assertRaises(SystemExit) as result:
            self.run_local('--asset', 'asset.zip')
        self.assertEqual(result.exception.code, 2)
        self.assertEqual(self.snapshot(), before)

    def test_missing_or_invalid_zip_does_not_write(self):
        before = self.snapshot()
        self.archive.unlink()
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)
        self.archive.write_bytes(b'not a ZIP')
        self.assertEqual(self.run_local(), 1)
        self.assertEqual(self.snapshot(), before)


class VersionTests(unittest.TestCase):
    def test_semver_prerelease_order_and_build_metadata(self):
        versions = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                    "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1"]
        self.assertEqual(sorted(reversed(versions), key=tool.version_key), versions)
        self.assertEqual(tool.version_key("1.0.0+first"), tool.version_key("1.0.0+second"))

    def test_invalid_versions_are_rejected(self):
        for version in ["1.0", "01.0.0", "1.0.0-01", "v1.0.0", "1.0.0-", "1.0.0+"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                tool.version_key(version)


if __name__ == "__main__":
    unittest.main()
