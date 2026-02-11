#!/usr/bin/env python3
"""Add a new version entry for ochibi-chans-converter-tool.

This duplicates the latest version entry and updates only the version
number and download URL to the specified version.

Usage:
    # デフォルトのパスのファイルを更新
    $ python3 add_version.py 0.3.2

    # 入力ファイルを指定して更新
    $ python3 add_version.py 0.3.2 --path my-vpm-repo.json

    # 別のファイル名で保存
    $ python3 add_version.py 0.3.2 --path dev.json --output release.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Tuple, Union


SEMVER_PATTERN = re.compile(
    r"^(?P<core>\d+(?:\.\d+)*)(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)
PRERELEASE_IDENTIFIER_PATTERN = re.compile(r"^[0-9A-Za-z-]+$")
PACKAGE_ID = "jp.aramaa.ochibi-chans-converter-tool"
TOOL_NAME = "ochibi-chans-converter-tool"
DEFAULT_INPUT_PATH = Path("develop/vpm-ochibi-chans-converter-tool-dev.json")


PrereleaseToken = Tuple[int, Union[int, str]]
VersionSortKey = Tuple[Tuple[int, ...], Tuple[int, Tuple[PrereleaseToken, ...]]]


def _parse_prerelease_identifier(identifier: str) -> PrereleaseToken:
    if not identifier:
        raise ValueError("Prerelease identifier must not be empty.")
    if not PRERELEASE_IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(
            f"Invalid prerelease identifier '{identifier}'. "
            "Only [0-9A-Za-z-] is allowed."
        )
    if identifier.isdigit():
        if len(identifier) > 1 and identifier.startswith("0"):
            raise ValueError(
                f"Invalid numeric prerelease identifier '{identifier}': "
                "leading zeroes are not allowed."
            )
        return (0, int(identifier))
    return (1, identifier)


def parse_version(version: str) -> VersionSortKey:
    match = SEMVER_PATTERN.match(version)
    if not match:
        raise ValueError(
            f"Version '{version}' is invalid. "
            "Use numeric dot notation, optionally with prerelease suffix "
            "(example: 0.5.3-beta or 0.5.3-beta.1)."
        )

    core = tuple(int(part) for part in match.group("core").split("."))
    prerelease = match.group("prerelease")
    if prerelease is None:
        # Stable releases should sort after prerelease entries with the same core.
        return (core, (1, tuple()))

    parsed_prerelease = tuple(
        _parse_prerelease_identifier(identifier)
        for identifier in prerelease.split(".")
    )
    return (core, (0, parsed_prerelease))


def load_json(path: Path) -> Dict:
    if not path.exists():
        hints = []
        candidates = ", ".join(
            sorted(str(candidate) for candidate in Path.cwd().glob("*.json"))
        )
        if candidates:
            hints.append(f"Available JSON files in current directory: {candidates}.")
        if DEFAULT_INPUT_PATH.exists():
            hints.append(f"For this tool, default --path is '{DEFAULT_INPUT_PATH}'.")
        hint = f" {' '.join(hints)}" if hints else ""
        raise FileNotFoundError(f"Input file not found: {path}.{hint}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    )
    temp_path = Path(temp_handle.name)
    try:
        with temp_handle:
            json.dump(payload, temp_handle, ensure_ascii=False, indent=4)
            temp_handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def add_version(input_path: Path, output_path: Path, new_version: str) -> str:
    # Validate early so the user gets a clear error before file mutation.
    parse_version(new_version)

    data = load_json(input_path)
    versions = data["packages"][PACKAGE_ID]["versions"]

    if new_version in versions:
        raise ValueError(f"Version {new_version} already exists in {input_path}.")

    latest_version = max(versions.keys(), key=parse_version)
    latest_entry = versions[latest_version]
    if latest_entry.get("version") != latest_version:
        raise ValueError(
            f"Latest entry version '{latest_entry.get('version')}' "
            f"does not match key '{latest_version}'."
        )
    new_entry = copy.deepcopy(latest_entry)

    new_entry["version"] = new_version
    if "url" in new_entry and isinstance(new_entry["url"], str):
        if latest_version not in new_entry["url"]:
            raise ValueError(
                f"Latest version '{latest_version}' not found in URL "
                f"'{new_entry['url']}'."
            )
        new_entry["url"] = new_entry["url"].replace(latest_version, new_version, 1)

    items = list(versions.items())
    insert_index = next(
        (index for index, (key, _) in enumerate(items) if key == latest_version),
        len(items) - 1,
    )
    items.insert(insert_index + 1, (new_version, new_entry))
    data["packages"][PACKAGE_ID]["versions"] = dict(items)

    write_json(output_path, data)
    return latest_version


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"Add a new {PACKAGE_ID} ({TOOL_NAME}) version entry by copying the "
            "latest one."
        )
    )
    parser.add_argument("version", help="New version string, e.g. 0.3.2")
    parser.add_argument(
        "--path",
        default=DEFAULT_INPUT_PATH,
        type=Path,
        help=f"Path to the input vpm JSON file for {TOOL_NAME}.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write the updated vpm JSON file (defaults to input path).",
    )
    args = parser.parse_args()

    output_path = args.output or args.path

    try:
        latest_version = add_version(args.path, output_path, args.version)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Error: {error}\n")

    print(
        f"Added version {args.version} based on {latest_version} to {output_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
