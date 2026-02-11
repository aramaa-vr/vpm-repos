#!/usr/bin/env python3
"""Add a new version entry for ochibi-chans-converter-tool.

This duplicates the latest version entry and updates only the version
number and download URL to the specified version.

Usage:
    # デフォルトのパスのファイルを更新
    $ python3 scripts/add_ochibi-chans-converter-tool_version.py 0.3.2

    # 入力ファイルを指定して更新
    $ python3 scripts/add_ochibi-chans-converter-tool_version.py 0.3.2 --path vpm.json

    # 別のファイル名で保存
    $ python3 scripts/add_ochibi-chans-converter-tool_version.py 0.3.2 --path vpm.json --output dev.json
"""

from __future__ import annotations

import argparse
import copy
import re
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Tuple


VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")
PACKAGE_ID = "jp.aramaa.ochibi-chans-converter-tool"
TOOL_NAME = "ochibi-chans-converter-tool"


def parse_version(version: str) -> Tuple[int, ...]:
    if not VERSION_PATTERN.match(version):
        raise ValueError(f"Version '{version}' is not numeric dot notation.")
    return tuple(int(part) for part in version.split("."))


def load_json(path: Path) -> Dict:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Add a new {PACKAGE_ID} ({TOOL_NAME}) version entry by copying the "
            "latest one."
        )
    )
    parser.add_argument("version", help="New version string, e.g. 0.3.2")
    parser.add_argument(
        "--path",
        default="develop/vpm-ochibi-chans-converter-tool-dev.json",
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
    latest_version = add_version(args.path, output_path, args.version)
    print(
        f"Added version {args.version} based on {latest_version} to {output_path}."
    )


if __name__ == "__main__":
    main()
