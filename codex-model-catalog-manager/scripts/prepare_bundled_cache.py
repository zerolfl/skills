#!/usr/bin/env python3
"""Prepare the configured Codex bundled model cache."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

from catalog_config import (
    CONFIG_HOME,
    CONFIG_PATH,
    load_config,
    resolve_config_path,
)


JsonObject = dict[str, Any]
VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a captured Codex bundled model catalog, back up the "
            "existing configured cache, and write metadata."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=(
            "Catalog manager config path (default: "
            "~/.config/codex-model-catalog-manager/config.json)"
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Captured JSON path; read stdin when omitted",
    )
    parser.add_argument(
        "--client-version",
        required=True,
        help="Codex version number only, for example 0.152.1",
    )
    parser.add_argument(
        "--fetched-at",
        help="UTC ISO-8601 timestamp; defaults to the current UTC time",
    )
    return parser.parse_args()


def load_catalog(path: Path | None) -> JsonObject:
    try:
        text = path.read_text(encoding="utf-8-sig") if path else sys.stdin.read()
    except FileNotFoundError as exc:
        raise ValueError(f"Captured JSON does not exist: {path}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid captured JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("models"), list):
        raise ValueError("Captured JSON must contain a top-level models array")
    return value


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, value: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    args = parse_args()
    try:
        version = args.client_version.strip()
        if not VERSION_PATTERN.fullmatch(version):
            raise ValueError("client-version must be a version number only")
        fetched_at = (args.fetched_at or utc_timestamp()).strip()
        if not fetched_at:
            raise ValueError("fetched-at must be a non-empty UTC timestamp")
        config = load_config(args.config)
        output_path = resolve_config_path(
            config["CODEX_CACHE_LATEST"], "CODEX_CACHE_LATEST"
        )
        catalog = load_catalog(args.input.resolve() if args.input else None)

        CONFIG_HOME.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            backup_path = CONFIG_HOME / (output_path.name + ".bak")
            shutil.copy2(output_path, backup_path)
            print(f"Backed up: {backup_path}")

        catalog.pop("fetched_at", None)
        catalog.pop("client_version", None)
        prepared = {
            "fetched_at": fetched_at,
            "client_version": version,
            **catalog,
        }
        atomic_write(output_path, prepared)
        print(f"Prepared: {output_path}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
