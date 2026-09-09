#!/usr/bin/env python3
"""Shared configuration helpers for the Codex model catalog manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


JsonObject = dict[str, Any]
CONFIG_HOME = Path.home() / ".config" / "codex-model-catalog-manager"
CONFIG_PATH = CONFIG_HOME / "config.json"
CODEX_HOME = Path.home() / ".codex"
DEFAULT_CACHE_LATEST = "models_cache_latest.json"
DEFAULT_CATALOG_OUTPUT = "models_catalog.json"
POLICY_CHOICES = ("v1", "custom-v1", "preserve")
REQUIRED_KEYS = {
    "CODEX_CACHE_LATEST",
    "CODEX_CUSTOM_LIST",
    "CODEX_CATALOG_OUTPUT",
    "CODEX_MULTI_AGENT_POLICY",
}


def _config_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path")
    return Path(value).expanduser()


def resolve_config_path(value: str, field: str) -> Path:
    root = CODEX_HOME.resolve()
    path = _config_path(value, field)
    if path.is_absolute():
        return path.resolve()
    if ".." in path.parts:
        raise ValueError(f"{field} relative path cannot contain '..': {value!r}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"{field} must be relative to ~/.codex or an absolute path: {value!r}"
        ) from exc
    return resolved


def _normalize_config_path(value: Any, field: str) -> str:
    path = _config_path(value, field)
    if not path.is_absolute() and ".." in path.parts:
        raise ValueError(f"{field} relative path cannot contain '..': {value!r}")
    return path.as_posix()


def validate_config(value: Any) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("config.json must contain a JSON object")
    missing = sorted(REQUIRED_KEYS - set(value))
    if missing:
        raise ValueError("config.json is missing: " + ", ".join(missing))
    unknown = sorted(set(value) - REQUIRED_KEYS)
    if unknown:
        raise ValueError("config.json has unknown keys: " + ", ".join(unknown))

    cache_latest = _normalize_config_path(
        value["CODEX_CACHE_LATEST"], "CODEX_CACHE_LATEST"
    )
    catalog_output = _normalize_config_path(
        value["CODEX_CATALOG_OUTPUT"], "CODEX_CATALOG_OUTPUT"
    )
    custom_value = value["CODEX_CUSTOM_LIST"]
    if not isinstance(custom_value, list):
        raise ValueError("CODEX_CUSTOM_LIST must be an array")
    policy = value["CODEX_MULTI_AGENT_POLICY"]
    if policy not in POLICY_CHOICES:
        raise ValueError(
            "CODEX_MULTI_AGENT_POLICY must be one of: "
            + ", ".join(POLICY_CHOICES)
        )

    custom_list: list[str] = []
    for index, item in enumerate(custom_value):
        custom_list.append(
            _normalize_config_path(
                item, f"CODEX_CUSTOM_LIST[{index}]"
            )
        )
    if len(set(custom_list)) != len(custom_list):
        raise ValueError("CODEX_CUSTOM_LIST contains duplicate paths")

    cache_name = cache_latest
    output_name = catalog_output
    if resolve_config_path(output_name, "CODEX_CATALOG_OUTPUT") == resolve_config_path(
        cache_name, "CODEX_CACHE_LATEST"
    ):
        raise ValueError("CODEX_CATALOG_OUTPUT must differ from CODEX_CACHE_LATEST")
    custom_resolved = {
        resolve_config_path(item, f"CODEX_CUSTOM_LIST[{index}]")
        for index, item in enumerate(custom_list)
    }
    if resolve_config_path(output_name, "CODEX_CATALOG_OUTPUT") in custom_resolved:
        raise ValueError("CODEX_CATALOG_OUTPUT must differ from every custom source")

    return {
        "CODEX_CACHE_LATEST": cache_name,
        "CODEX_CUSTOM_LIST": custom_list,
        "CODEX_CATALOG_OUTPUT": output_name,
        "CODEX_MULTI_AGENT_POLICY": policy,
    }


def load_config(path: Path = CONFIG_PATH) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"Config file does not exist: {path}; run "
            "`python scripts/init_config.py` from the skill directory first"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    return validate_config(value)


def resolve_config_paths(
    config: JsonObject,
) -> tuple[Path, list[Path], Path]:
    cache = resolve_config_path(config["CODEX_CACHE_LATEST"], "CODEX_CACHE_LATEST")
    custom = [
        resolve_config_path(item, f"CODEX_CUSTOM_LIST[{index}]")
        for index, item in enumerate(config["CODEX_CUSTOM_LIST"])
    ]
    output = resolve_config_path(
        config["CODEX_CATALOG_OUTPUT"], "CODEX_CATALOG_OUTPUT"
    )
    return cache, custom, output


def custom_source_key(path: Path) -> str:
    root = CODEX_HOME.resolve()
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return path.stem
    return relative.with_suffix("").as_posix()


def write_config(
    config: JsonObject, path: Path = CONFIG_PATH, *, force: bool = False
) -> None:
    normalized = validate_config(config)
    if path.exists() and not force:
        raise ValueError(f"Config file already exists: {path}; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
