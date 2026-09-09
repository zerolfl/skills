#!/usr/bin/env python3
"""Build a static Codex model catalog from bundled and custom entries."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from typing import Any

from catalog_config import (
    CONFIG_PATH,
    CONFIG_HOME,
    CODEX_HOME,
    POLICY_CHOICES,
    custom_source_key,
    load_config,
    resolve_config_paths,
)


JsonObject = dict[str, Any]
MISSING = object()
VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge current Codex bundled models with third-party models, "
            "apply the selected multi-agent policy, and normalize custom priorities."
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
        "--models-cache",
        type=Path,
        help="Override CODEX_CACHE_LATEST",
    )
    parser.add_argument(
        "--models-custom",
        type=Path,
        action="append",
        help="Override CODEX_CUSTOM_LIST; repeat in merge order",
    )
    parser.add_argument(
        "--models-output",
        type=Path,
        help="Override CODEX_CATALOG_OUTPUT",
    )
    parser.add_argument(
        "--multi-agent-policy",
        choices=POLICY_CHOICES,
        help=(
            "Override CODEX_MULTI_AGENT_POLICY. 'v1' rewrites "
            "existing values to v1 in both bundled and custom entries "
            "without adding the field where it is absent; 'custom-v1' rewrites "
            "existing values to v1 only in custom entries; 'preserve' keeps "
            "each source value unchanged."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and print diff without writing"
    )
    return parser.parse_args()


def load_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Top-level JSON value must be an object: {path}")
    if not isinstance(value.get("models"), list):
        raise ValueError(f"Top-level 'models' must be an array: {path}")
    return value


def load_models_cache(path: Path) -> tuple[JsonObject, str, str]:
    if not path.exists():
        raise ValueError(
            f"models-cache file does not exist: {path}; run "
            "codex debug models --bundled directly to CODEX_CACHE_LATEST and enrich "
            "it with scripts/prepare_bundled_cache.py first"
        )
    value = load_json(path)
    fetched_at = value.get("fetched_at")
    version = value.get("client_version")
    if not isinstance(fetched_at, str) or not fetched_at.strip():
        raise ValueError(
            f"Bundled cache is missing fetched_at: {path}; run "
            "scripts/prepare_bundled_cache.py first"
        )
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError(
            f"Bundled cache must contain a version-only client_version: {path}; "
            "run scripts/prepare_bundled_cache.py first"
        )
    return value, version, fetched_at


def utc_nanosecond_timestamp() -> str:
    now_ns = time.time_ns()
    seconds, nanos = divmod(now_ns, 1_000_000_000)
    base = dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
    return base.strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"


def model_map(models: list[Any], label: str) -> dict[str, JsonObject]:
    mapped: dict[str, JsonObject] = {}
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise ValueError(f"{label} model at index {index} must be an object")
        slug = model.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(f"{label} model at index {index} has no valid slug")
        if slug in mapped:
            raise ValueError(f"Duplicate {label} model slug: {slug}")
        mapped[slug] = model
    return mapped


def validate_custom_models(models: list[Any]) -> dict[str, JsonObject]:
    mapped = model_map(models, "custom")
    for slug, model in mapped.items():
        levels = model.get("supported_reasoning_levels")
        if not isinstance(levels, list):
            raise ValueError(f"{slug}: supported_reasoning_levels must be an array")
        efforts = {
            item.get("effort") for item in levels if isinstance(item, dict)
        }
        default = model.get("default_reasoning_level")
        if default is not None and default not in efforts:
            raise ValueError(
                f"{slug}: default_reasoning_level {default!r} is not supported"
            )
        context = model.get("context_window")
        maximum = model.get("max_context_window")
        if not isinstance(context, int) or context <= 0:
            raise ValueError(f"{slug}: context_window must be a positive integer")
        if maximum is not None and (
            not isinstance(maximum, int) or maximum < context
        ):
            raise ValueError(
                f"{slug}: max_context_window must be at least context_window"
            )
    return mapped


def apply_multi_agent_policy(
    models: list[Any], policy: str, *, source: str
) -> list[JsonObject]:
    if policy not in POLICY_CHOICES:
        raise ValueError(f"unsupported multi-agent policy: {policy}")
    normalized = copy.deepcopy(models)
    rewrite_to_v1 = policy == "v1" or (
        policy == "custom-v1" and source == "custom"
    )
    if rewrite_to_v1:
        for model in normalized:
            if isinstance(model, dict) and "multi_agent_version" in model:
                model["multi_agent_version"] = "v1"
    return normalized


def merge_catalog(
    bundled: JsonObject,
    custom_sources: list[tuple[Path, JsonObject]],
    multi_agent_policy: str,
) -> JsonObject:
    bundled_models = apply_multi_agent_policy(
        bundled["models"], multi_agent_policy, source="bundled"
    )
    bundled_by_slug = model_map(bundled_models, "bundled")
    custom_models: list[JsonObject] = []
    custom_by_slug: dict[str, JsonObject] = {}
    for source_path, source in custom_sources:
        source_models = apply_multi_agent_policy(
            source["models"], multi_agent_policy, source="custom"
        )
        source_map = validate_custom_models(source_models)
        conflicts = sorted(set(bundled_by_slug) & set(source_map))
        if conflicts:
            raise ValueError(
                f"{source_path}: custom models cannot override bundled slugs: "
                + ", ".join(conflicts)
            )
        duplicate_custom = sorted(set(custom_by_slug) & set(source_map))
        if duplicate_custom:
            raise ValueError(
                f"{source_path}: duplicate custom slugs across custom sources: "
                + ", ".join(duplicate_custom)
            )
        custom_by_slug.update(source_map)
        custom_models.extend(source_models)
    for index, model in enumerate(custom_models):
        model["priority"] = 1000 + index
    merged = copy.deepcopy(bundled)
    merged["models"] = bundled_models + custom_models
    return merged


def read_previous(path: Path) -> JsonObject:
    if not path.exists():
        return {"models": []}
    return load_json(path)


def sidecar_dir() -> Path:
    return CONFIG_HOME


def sidecar(path: Path, suffix: str) -> Path:
    return sidecar_dir() / (path.name + suffix)


def legacy_sidecar_dirs() -> tuple[Path, ...]:
    return (
        CODEX_HOME / ".codex-model-catalog-manager",
        CODEX_HOME / "codex-model-catalog-manager",
    )


def migrate_legacy_sidecars() -> None:
    target_dir = sidecar_dir()
    for legacy_dir in legacy_sidecar_dirs():
        if not legacy_dir.is_dir() or legacy_dir == target_dir:
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in legacy_dir.iterdir():
            target = target_dir / source.name
            if target.exists():
                continue
            shutil.move(str(source), str(target))
        try:
            legacy_dir.rmdir()
        except OSError:
            pass


def read_state(output: Path) -> JsonObject | None:
    state_path = sidecar(output, ".state.json")
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def read_previous_bundled_slugs(output: Path) -> set[str]:
    state = read_state(output)
    slugs = state.get("bundled_slugs", []) if state is not None else []
    return {slug for slug in slugs if isinstance(slug, str)}


def read_previous_custom_slugs(output: Path) -> set[str]:
    state = read_state(output)
    if state is None:
        return set()
    grouped = state.get("custom_slugs")
    if isinstance(grouped, dict):
        return {
            slug
            for slugs in grouped.values()
            if isinstance(slugs, list)
            for slug in slugs
            if isinstance(slug, str)
        }
    if isinstance(grouped, list):
        return {slug for slug in grouped if isinstance(slug, str)}
    return set()


def field_changes(
    old: Any, new: Any, path: str = ""
) -> list[JsonObject]:
    if isinstance(old, dict) and isinstance(new, dict):
        changes: list[JsonObject] = []
        for key in sorted(set(old) | set(new)):
            child_path = f"{path}.{key}" if path else key
            changes.extend(
                field_changes(old.get(key, MISSING), new.get(key, MISSING), child_path)
            )
        return changes
    if old is not MISSING and new is not MISSING and old == new:
        return []
    return [
        {
            "path": path or "$",
            "old_present": old is not MISSING,
            "old": None if old is MISSING else old,
            "new_present": new is not MISSING,
            "new": None if new is MISSING else new,
        }
    ]


def build_diff(
    old_catalog: JsonObject,
    new_catalog: JsonObject,
    previous_bundled: set[str],
    previous_custom: set[str],
    current_bundled: set[str],
    current_custom: set[str],
    version: str,
) -> JsonObject:
    old_map = model_map(old_catalog["models"], "previous")
    new_map = model_map(new_catalog["models"], "generated")
    ordered_slugs = list(old_map) + [slug for slug in new_map if slug not in old_map]
    groups: dict[str, list[JsonObject]] = {
        "bundled": [],
        "custom": [],
        "unclassified": [],
    }
    for slug in ordered_slugs:
        old = old_map.get(slug, MISSING)
        new = new_map.get(slug, MISSING)
        changes = field_changes(old, new)
        if not changes:
            continue
        if slug in current_bundled or slug in previous_bundled:
            group = "bundled"
        elif slug in current_custom or slug in previous_custom:
            group = "custom"
        else:
            group = "unclassified"
        status = "modified"
        if old is MISSING:
            status = "added"
        elif new is MISSING:
            status = "removed"
        groups[group].append(
            {"slug": slug, "status": status, "changes": changes}
        )
    counts = {
        group: {
            status: sum(item["status"] == status for item in items)
            for status in ("added", "modified", "removed")
        }
        for group, items in groups.items()
    }
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "codex_version": version,
        "summary": counts,
        "bundled_changes": groups["bundled"],
        "custom_changes": groups["custom"],
        "unclassified_changes": groups["unclassified"],
    }


def compact(value: Any, present: bool) -> str:
    if not present:
        return "<missing>"
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) <= 180:
        return rendered
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:12]
    return f"<abbreviated len={len(rendered)} sha256={digest}>"


def markdown_diff(diff: JsonObject) -> str:
    lines = [
        "# Codex Model Catalog Diff",
        "",
        f"Codex: `{diff['codex_version']}`",
        f"Generated: `{diff['generated_at']}`",
        "",
    ]
    sections = (
        ("Bundled", "bundled_changes"),
        ("Custom", "custom_changes"),
        ("Unclassified", "unclassified_changes"),
    )
    for title, key in sections:
        lines.extend([f"## {title}", ""])
        items = diff[key]
        if not items:
            lines.extend(["No changes.", ""])
            continue
        for item in items:
            lines.append(f"- `{item['slug']}`: {item['status']}")
            for change in item["changes"]:
                old = compact(change["old"], change["old_present"])
                new = compact(change["new"], change["new_present"])
                lines.append(f"  - `{change['path']}`: `{old}` -> `{new}`")
        lines.append("")
    lines.extend(
        [
            "Full, unabbreviated old/new values are stored in the JSON diff.",
            "",
        ]
    )
    return "\n".join(lines)


def write_text_temp(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return temporary
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str) -> None:
    temporary = write_text_temp(path, text)
    try:
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_and_validate_candidate(
    catalog: JsonObject, output: Path
) -> Path:
    candidate = write_text_temp(output, json_text(catalog))
    try:
        parsed = load_json(candidate)
        expected = set(model_map(catalog["models"], "generated"))
        actual = set(model_map(parsed["models"], "candidate"))
        if expected != actual:
            raise ValueError("Candidate changed the generated model slug set")
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    return candidate


def main() -> int:
    args = parse_args()
    candidate: Path | None = None
    try:
        migrate_legacy_sidecars()
        config = load_config(args.config)
        snapshot_path, custom_paths, output = resolve_config_paths(config)
        if args.models_cache is not None:
            snapshot_path = args.models_cache.resolve()
        if args.models_custom:
            custom_paths = [path.resolve() for path in args.models_custom]
        if args.models_output is not None:
            output = args.models_output.resolve()
        policy = args.multi_agent_policy or config["CODEX_MULTI_AGENT_POLICY"]
        bundled, version, fetched_at = load_models_cache(snapshot_path)
        custom_sources = [
            (path, load_json(path)) for path in custom_paths
        ]
        previous = read_previous(output)
        merged = merge_catalog(
            bundled, custom_sources, policy
        )
        generated = {
            "fetched_at": fetched_at,
            "client_version": version,
            **merged,
        }
        current_bundled = set(model_map(bundled["models"], "bundled"))
        current_custom: set[str] = set()
        for path, custom in custom_sources:
            current_custom.update(model_map(custom["models"], str(path)))
        diff = build_diff(
            previous,
            generated,
            read_previous_bundled_slugs(output),
            read_previous_custom_slugs(output),
            current_bundled,
            current_custom,
            version,
        )
        report = markdown_diff(diff)
        candidate = write_and_validate_candidate(generated, output)
        if args.dry_run:
            candidate.unlink(missing_ok=True)
            print(report)
            return 0
        print(f"Using bundled cache: {snapshot_path}")
        for path in custom_paths:
            print(f"Using custom source: {path}")
        custom_slugs_by_source: dict[str, list[str]] = {}
        for path, custom in custom_sources:
            custom_slugs_by_source[custom_source_key(path)] = list(
                model_map(custom["models"], str(path))
            )
        state = {
            "generated_at": diff["generated_at"],
            "client_version": version,
            "multi_agent_policy": policy,
            "bundled_slugs": list(model_map(bundled["models"], "bundled")),
            "custom_slugs": custom_slugs_by_source,
            "custom_sources": [path.name for path in custom_paths],
        }
        sidecar_dir().mkdir(parents=True, exist_ok=True)
        write_text_atomic(sidecar(output, ".diff.json"), json_text(diff))
        write_text_atomic(sidecar(output, ".diff.md"), report)
        write_text_atomic(sidecar(output, ".state.json"), json_text(state))
        if output.exists():
            shutil.copy2(output, sidecar(output, ".bak"))
        os.replace(candidate, output)
        print(f"Updated: {output}")
        print(f"Diff: {sidecar(output, '.diff.md')}")
        print(f"State: {sidecar(output, '.state.json')}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
