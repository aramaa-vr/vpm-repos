#!/usr/bin/env python3
"""Prepare VPM listings from a required local ZIP without network access. Python 3.10+."""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import quote
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


def version_key(version: str) -> tuple:
    """SemVer precedence: numeric prereleases first; build metadata ignored."""
    match = SEMVER.fullmatch(version) if isinstance(version, str) else None
    if not match:
        raise ValueError(f"Invalid SemVer version: {version!r}")
    major, minor, patch, prerelease, _ = match.groups()
    identifiers = []
    if prerelease:
        for part in prerelease.split("."):
            if part.isdigit() and len(part) > 1 and part.startswith("0"):
                raise ValueError(f"Numeric prerelease has a leading zero: {version}")
            identifiers.append((0, int(part)) if part.isdigit() else (1, part))
    return (int(major), int(minor), int(patch), prerelease is None, tuple(identifiers))


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def read_json(raw: bytes) -> dict:
    value = json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def validate_source(repo: str, tag: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("--repo must be OWNER/REPOSITORY")
    if any(part in {".", ".."} for part in repo.split("/")) or not tag:
        raise ValueError("Invalid repository or empty release tag")


def archive_manifest(archive: zipfile.ZipFile) -> dict:
    manifests = [info for info in archive.infolist() if info.filename == "package.json"]
    if len(manifests) != 1 or manifests[0].file_size > 1024 * 1024:
        raise ValueError("ZIP must have exactly one root package.json (at most 1 MiB)")
    manifest = read_json(archive.read(manifests[0]))
    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        raise ValueError("package.json has no package name")
    version_key(manifest.get("version"))
    return manifest


def local_manifest(path: Path, repo: str, tag: str) -> dict:
    """Read the frozen ZIP without network access or extraction."""
    validate_source(repo, tag)
    version_key(tag)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            manifest = archive_manifest(archive)
    if manifest["version"] != tag:
        raise ValueError("Local ZIP version and --tag must match exactly (no v prefix)")
    if path.name != f"{manifest['name']}-{manifest['version']}.zip":
        raise ValueError("Local ZIP filename must be <package-name>-<version>.zip")
    url = f"https://github.com/{repo}/releases/download/{quote(tag, safe='')}/{quote(path.name, safe='')}"
    if "url" in manifest and manifest["url"] != url:
        raise ValueError("Local ZIP manifest URL differs from the planned release URL")
    if "zipSHA256" in manifest:
        raise ValueError("zipSHA256 belongs in the listing, not inside the ZIP manifest")
    return {**manifest, "url": url, "zipSHA256": digest.hexdigest()}


def plan_updates(listing: dict, latest: dict, entry: dict) -> tuple[dict, dict]:
    new_listing, new_latest = copy.deepcopy(listing), copy.deepcopy(latest)
    packages = new_listing.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("vpm.json must have a packages object")
    package_id, version = entry["name"], entry["version"]
    package = packages.setdefault(package_id, {"versions": {}})
    if not isinstance(package, dict) or not isinstance(package.get("versions"), dict):
        raise ValueError(f"Invalid versions object for {package_id}")
    versions = package["versions"]
    if version in versions and versions[version] != entry:
        raise ValueError(f"Conflict: {package_id} {version} already has different metadata or hash")
    versions[version] = copy.deepcopy(entry)
    for key, value in versions.items():
        version_key(key)
        if not isinstance(value, dict) or value.get("version") != key:
            raise ValueError(f"Version key and manifest disagree: {package_id} {key}")
    newest = max(versions, key=version_key)
    items = new_latest.get("packages")
    if new_latest.get("schemaVersion") != 1 or not isinstance(items, list):
        raise ValueError("latest.json must have schemaVersion 1 and a packages array")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("latest.json contains an invalid package entry")
    matches = [item for item in items if item.get("id") == package_id]
    if len(matches) > 1:
        raise ValueError(f"Duplicate package in latest.json: {package_id}")
    if not matches:
        items.append({"id": package_id, "version": newest})
    elif version_key(matches[0].get("version")) < version_key(newest):
        matches[0]["version"] = newest
    return new_listing, new_latest


def encode_json(value: dict, indent: int) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=indent) + "\n").encode("utf-8")


def encode_latest(value: dict) -> bytes:
    """Keep latest.json's one-package-per-line format."""
    fields = []
    for key, item in value.items():
        if key == "packages" and item:
            rows = ["    { " + json.dumps(package, ensure_ascii=False)[1:-1] + " }"
                    for package in item]
            fields.append('  "packages": [\n' + ",\n".join(rows) + '\n  ]')
        else:
            fields.append("\n".join(json.dumps(
                {key: item}, ensure_ascii=False, indent=2,
            ).splitlines()[1:-1]))
    return ("{\n" + ",\n".join(fields) + "\n}\n").encode("utf-8")


def write_changes(changes: list[tuple[Path, bytes, bytes]]) -> None:
    """Prepare all writes first; restore replaced files on an ordinary I/O error."""
    staged, replaced, recovery_files = [], [], set()
    try:
        for path, original, updated in changes:
            paths = []
            staged.append((path, paths))
            for content in (updated, original):
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                                 suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    paths.append(temporary)
                    handle.write(content)
                os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        # Preparing an update may take time. Never overwrite edits made meanwhile.
        for path, original, _ in changes:
            if path.read_bytes() != original:
                raise ValueError(f"File changed while preparing the update: {path}")
        for path, (updated_path, rollback_path) in staged:
            os.replace(updated_path, path)
            replaced.append((path, rollback_path))
    except Exception as error:
        for path, rollback_path in reversed(replaced):
            try:
                os.replace(rollback_path, path)
            except OSError:
                recovery_files.add(rollback_path)
        if recovery_files:
            raise RuntimeError(
                "Write and rollback failed. Original data preserved at: "
                + ", ".join(str(path) for path in recovery_files)
            ) from error
        raise
    finally:
        for _, paths in staged:
            for temporary in paths:
                if temporary not in recovery_files:
                    temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Public GitHub repository: OWNER/REPOSITORY")
    parser.add_argument("--tag", required=True, help="Planned release tag; must equal the ZIP manifest version")
    parser.add_argument("--zip", dest="local_zip", required=True, type=Path, help="Local package ZIP used to prepare all listing metadata")
    parser.add_argument("--path", type=Path, default=ROOT / "vpm.json", help="VPM listing path")
    parser.add_argument("--latest-path", type=Path, default=ROOT / "latest.json", help="latest.json path")
    parser.add_argument("--index-path", type=Path, help="Also update a distribution index.json with the same entry")
    parser.add_argument("--dry-run", action="store_true", help="Show the diff without updating any JSON")
    args = parser.parse_args(argv)
    try:
        listing_path, latest_path = args.path.resolve(), args.latest_path.resolve()
        index_path = args.index_path.resolve() if args.index_path else None
        paths = [listing_path, latest_path] + ([index_path] if index_path else [])
        if len(paths) != len(set(paths)):
            raise ValueError("The JSON output paths must be different")
        if args.local_zip.resolve() in paths:
            raise ValueError("The input ZIP must not be a JSON output path")
        original_listing, original_latest = listing_path.read_bytes(), latest_path.read_bytes()
        listing, latest = read_json(original_listing), read_json(original_latest)
        original_index = index_path.read_bytes() if index_path else None
        index = read_json(original_index) if index_path else None
        entry = local_manifest(args.local_zip, args.repo, args.tag)
        updated_listing, updated_latest = plan_updates(listing, latest, entry)
        outputs = [
            (listing_path, original_listing, listing, updated_listing, 4),
            (latest_path, original_latest, latest, updated_latest, 2),
        ]
        if index_path:
            updated_index, _ = plan_updates(index, {"schemaVersion": 1, "packages": []}, entry)
            outputs.append((index_path, original_index, index, updated_index, 2))
        changes = []
        for path, raw, old, new, indent in outputs:
            if old != new:
                updated = encode_latest(new) if path == latest_path else encode_json(new, indent)
                changes.append((path, raw, updated))
                print("".join(difflib.unified_diff(
                    raw.decode("utf-8-sig").splitlines(keepends=True),
                    updated.decode("utf-8").splitlines(keepends=True),
                    fromfile=str(path), tofile=str(path) + " (updated)",
                )), end="")
        print(f"Package: {entry['name']} {entry['version']}\nSHA-256: {entry['zipSHA256']}")
        print("Local ZIP preparation only: no release was fetched or published.")
        if not changes:
            print("No changes: this release is already registered.")
        elif args.dry_run:
            print("Dry run: no JSON files were changed.")
        else:
            write_changes(changes)
            print("Updated local JSON files. Review with git diff; commit/push manually.")
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
