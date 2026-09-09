---
name: codex-model-catalog-manager
description: Create, update, validate, and diff a Codex model_catalog_json that combines the installed CLI's bundled models with custom third-party model metadata. Use when adding a custom model, refreshing bundled model entries after a Codex update, repairing catalog schema drift, or explaining catalog changes. Do not use for model-provider credentials or endpoint configuration alone.
---

# Codex Model Catalog Manager

Read `~/.config/codex-model-catalog-manager/config.json` before doing any work. If it is missing, stop and tell the user to run `python scripts/init_config.py` from the skill directory. The script prompts for each setting; press Esc to return to the previous setting. It prints a configuration summary and writes the file only after confirmation. Re-run it to update existing settings. Example:

```json
{
  "CODEX_CACHE_LATEST": "models_cache_latest.json",
  "CODEX_CUSTOM_LIST": [
    "models_custom.json",
    "models_deepseek.json"
  ],
  "CODEX_CATALOG_OUTPUT": "models_catalog.json",
  "CODEX_MULTI_AGENT_POLICY": "v1"
}
```

- `CODEX_CACHE_LATEST`: bundled baseline captured from `codex debug models --bundled` and enriched in place with `fetched_at` and `client_version` (version number only).
- `CODEX_CUSTOM_LIST`: custom model sources, merged in list order.
- `CODEX_CATALOG_OUTPUT`: generated merged catalog output.
- `CODEX_MULTI_AGENT_POLICY`: `v1`, `custom-v1`, or `preserve`, controlling `multi_agent_version` during merge.

`CODEX_CACHE_LATEST`, every `CODEX_CUSTOM_LIST` entry, and `CODEX_CATALOG_OUTPUT` may be relative to `~/.codex/` or absolute paths. Relative paths cannot contain `..`. `models_cache.json` is Codex's own login cache; never use or overwrite it. Before each capture, back up the existing baseline to `~/.config/codex-model-catalog-manager/<CODEX_CACHE_LATEST>.bak`.

The generated catalog contains the bundled models followed by all custom entries, with `fetched_at` and `client_version` (version number only) at the top. Its `.state.json`, `.diff.json`, `.diff.md`, and `.bak` sidecars are stored under `~/.config/codex-model-catalog-manager/`. The `.state.json` records `generated_at`, `client_version`, `multi_agent_policy`, the custom source list, `bundled_slugs`, and `custom_slugs` grouped by source, for example `{"models_custom": [...], "models_deepseek": [...]}`.

`<sidecar-dir>` means `~/.config/codex-model-catalog-manager/`.

The sidecar directory is fixed and is not configurable. On startup, `scripts/update_catalog.py` moves any existing `~/.codex/.codex-model-catalog-manager/` or `~/.codex/codex-model-catalog-manager/` contents into the fixed directory before reading state or writing output.

This skill only writes `CODEX_CATALOG_OUTPUT`. Do not modify `config.toml`, `model_catalog_json`, or any Codex configuration. After generating the catalog, read the current `model_catalog_json` value from `~/.codex/config.toml` and report: `model_catalog_json is currently <value>; to use the generated catalog, change it to <CODEX_CATALOG_OUTPUT>.` If `model_catalog_json` is not set, report that the generated catalog must be configured manually.

## Workflow

1. Check `~/.config/codex-model-catalog-manager/config.json`. If it is missing, stop and tell the user to run `python scripts/init_config.py` from the skill directory. The script prompts for each setting; press Esc to return to the previous setting. It prints a configuration summary and writes the file only after confirmation. Re-run it to update existing settings.
2. Run `codex --version` with elevated privileges and retain the version number only. Then pipe `codex debug models --bundled` into `python scripts/prepare_bundled_cache.py --client-version <version-number-only>` with elevated privileges. The script validates the capture, backs up an existing baseline, and atomically writes the configured `CODEX_CACHE_LATEST` with `fetched_at` and version-only `client_version`. If the Codex CLI is not found, stop and tell the user to install it. The merge script refuses a cache missing either metadata field.
3. Check the configured custom sources and output path. The merge script requires the prepared cache from step 2 to exist; it does not fetch bundled models. If only an old merged catalog exists, separate third-party entries before generating. Entries absent from both the current bundled slugs and an existing state file under `~/.config/codex-model-catalog-manager/` are ambiguous; ask before classifying or deleting them.
4. For additions or metadata updates, start from [assets/custom-models.example.json](assets/custom-models.example.json), then replace values supported by current vendor documentation. Validate schema and field semantics against the Codex source for the installed CLI version. If the user has not provided a source location, inspect the official repository at https://github.com/openai/codex. Validate that each custom JSON contains only third-party entries and satisfies the required fields before merging.
5. If the user supplies only a model identifier, search the vendor's official documentation for its `models.json` / `model_catalog_json` configuration first. Use the vendor's documented model metadata. Record source URLs and access date in the response. Use the Codex source only for catalog schema and field semantics. Do not use blogs or aggregators when primary sources exist.
6. Ask only for required facts that remain unresolved or conflict across official sources. Never invent a context window, modalities, reasoning efforts, request semantics, or support for native search and original image detail.
7. Read the multi-agent policy from `config.json`. If the user explicitly asks to change it for this run, pass `--multi-agent-policy v1`, `--multi-agent-policy custom-v1`, or `--multi-agent-policy preserve` as an override; otherwise use `CODEX_MULTI_AGENT_POLICY` as configured.
8. Run `scripts/update_catalog.py` with elevated privileges to validate all custom sources, merge them with the prepared bundled cache in `CODEX_CUSTOM_LIST` order, apply the selected multi-agent policy, reassign custom priorities to `1000`, `1001`, ... in merged order, and write the configured `CODEX_CATALOG_OUTPUT` plus concise Markdown diffs. The normal run creates `<sidecar-dir>/<CODEX_CATALOG_OUTPUT>.bak` before replacing the output. Source files are not modified.
9. Review the generated diff and state after the update. Report bundled and custom changes separately, including added/removed models and old/new field values. Tell the user they can inspect the current update diff at `<sidecar-dir>/<CODEX_CATALOG_OUTPUT>.diff.md` and the models included in the current update at `<sidecar-dir>/<CODEX_CATALOG_OUTPUT>.state.json`. If the diff is unexpected, restore `<sidecar-dir>/<CODEX_CATALOG_OUTPUT>.bak`. Do not run `--dry-run` as a routine extra step; use it only when the user explicitly asks for a preview or when replacing the output must be avoided.

During merging:

- `--multi-agent-policy` controls `multi_agent_version`:
  - `v1` rewrites existing `multi_agent_version` values to `"v1"` in both bundled and custom entries; it does not add the field to entries that omit it. Use `v1` when custom models must be usable as GPT models' subagents.
  - `custom-v1` rewrites existing `multi_agent_version` values to `"v1"` only in custom entries; bundled cache entries remain unchanged. It does not add the field to entries that omit it.
  - `preserve` keeps each source file's values unchanged.
- The merge concatenates custom sources in `CODEX_CUSTOM_LIST` order and reassigns custom `priority` values to `1000`, `1001`, ... in that merged order. Reorder the list or the custom arrays to change custom ordering.
- Neither policy modifies the source bundled or custom files.

## Permissions

Run these commands with elevated privileges:

- `codex --version`
- `codex debug models --bundled`
- `python scripts/prepare_bundled_cache.py`
- `python scripts/update_catalog.py`, including when `--dry-run` is used

For the Codex command tool, use `sandbox_permissions: "require_escalated"` with a short justification. If a command required by this workflow fails with an access or permission error, retry the same command with elevated privileges and request user approval when the execution environment requires it. Preserve the original arguments and working directory; do not change the catalog or delete processes as a workaround.

## Commands

Capture and prepare the bundled baseline first (step 2). The pipe syntax works in both bash and PowerShell:

```shell
codex --version  # requires elevated privileges
codex debug models --bundled | python scripts/prepare_bundled_cache.py --client-version <version-number-only>  # requires elevated privileges
```

`prepare_bundled_cache.py` never invokes Codex. If piping is unavailable, capture to a file and pass `--input <captured.json>`. The script overwrites `<CODEX_CACHE_LATEST>.bak` with the immediately previous baseline; if the cache does not exist yet, no backup is created. It validates the capture and atomically replaces `CODEX_CACHE_LATEST` with the complete catalog plus `fetched_at` and the version-only `client_version`.

Generate or update a catalog:

```shell
python scripts/update_catalog.py --multi-agent-policy <v1|custom-v1|preserve>  # requires elevated privileges
```

Optional preview without replacing the output (not part of the normal workflow):

```shell
python scripts/update_catalog.py --multi-agent-policy <v1|custom-v1|preserve> --dry-run  # requires elevated privileges; still creates a temporary file
```

`--multi-agent-policy` is optional and overrides `CODEX_MULTI_AGENT_POLICY` from `config.json`. `v1` rewrites existing values in both bundled and custom sources; `custom-v1` rewrites existing values only in custom sources; `preserve` keeps each source file unchanged.

Use this only when the user explicitly requests a preview or when replacing the output must be avoided. The normal update command already writes `.diff.md`, `.diff.json`, and `.bak` sidecars under `~/.config/codex-model-catalog-manager/`, so a separate dry run is not required.

`update_catalog.py` reads `config.json` by default. The configured `CODEX_CACHE_LATEST` must already exist from the preparation step and contain both required metadata fields; otherwise the merge script fails before writing anything. The merge script never fetches or invokes Codex. It uses the prepared cache as the bundled baseline and combines it with every `CODEX_CUSTOM_LIST` source in order.

`init_config.py` writes the config. `prepare_bundled_cache.py` validates a captured catalog, backs up the previous baseline, and writes metadata; it never invokes Codex. `update_catalog.py` merges the prepared cache with all configured custom sources, applies the selected multi-agent policy, normalizes custom priorities, and performs structural JSON and slug-set checks.
