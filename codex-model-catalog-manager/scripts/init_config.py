#!/usr/bin/env python3
"""Interactively create or update the Codex model catalog manager config.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable

from catalog_config import (
    CONFIG_PATH,
    DEFAULT_CACHE_LATEST,
    DEFAULT_CATALOG_OUTPUT,
    POLICY_CHOICES,
    write_config,
)


InputFunction = Callable[[str], str]
BACK_VALUE = "\x1b"


class BackRequested(Exception):
    """Signal that the user wants to return to the previous setting."""


def _read_console(prompt: str) -> str:
    if not sys.stdin.isatty():
        return input(prompt)
    if os.name == "nt":
        return _read_windows_console(prompt)
    return _read_posix_console(prompt)


def _read_windows_console(prompt: str) -> str:
    import msvcrt

    print(prompt, end="", flush=True)
    characters: list[str] = []
    while True:
        character = msvcrt.getwch()
        if character == BACK_VALUE:
            print()
            return BACK_VALUE
        if character in {"\r", "\n"}:
            print()
            return "".join(characters)
        if character == "\x03":
            raise KeyboardInterrupt
        if character == "\b":
            _erase_last_character(characters)
            continue
        if character in {"\x00", "\xe0"}:
            msvcrt.getwch()
            continue
        _append_character(characters, character)


def _read_posix_console(prompt: str) -> str:
    import select
    import termios
    import tty

    file_descriptor = sys.stdin.fileno()
    previous_settings = termios.tcgetattr(file_descriptor)
    print(prompt, end="", flush=True)
    characters: list[str] = []
    try:
        tty.setraw(file_descriptor)
        while True:
            character = sys.stdin.read(1)
            if character == BACK_VALUE:
                if select.select([sys.stdin], [], [], 0.03)[0]:
                    while select.select([sys.stdin], [], [], 0)[0]:
                        sys.stdin.read(1)
                    continue
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return BACK_VALUE
            if character in {"\r", "\n"}:
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return "".join(characters)
            if character == "\x03":
                raise KeyboardInterrupt
            if character in {"\b", "\x7f"}:
                _erase_last_character(characters)
                continue
            _append_character(characters, character)
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous_settings)


def _erase_last_character(characters: list[str]) -> None:
    if characters:
        characters.pop()
        print("\b \b", end="", flush=True)


def _append_character(characters: list[str], character: str) -> None:
    if character.isprintable():
        characters.append(character)
        print(character, end="", flush=True)


def _prompt(
    label: str,
    *,
    variable_name: str,
    current: str | None = None,
    default: str | None = None,
    choices: tuple[str, ...] | None = None,
    required: bool = False,
    input_fn: InputFunction | None = None,
) -> str:
    fallback = current if current is not None else default
    while True:
        if choices:
            selected = (fallback or "").lower()
            rendered = "/".join(
                f"[{choice}]" if choice.lower() == selected else choice
                for choice in choices
            )
            suffix = f" ({rendered})"
        elif fallback:
            suffix = f" [{fallback}]"
        else:
            suffix = ""
        prompt = f"{variable_name} ({label}){suffix}: "
        value = (input_fn(prompt) if input_fn else _read_console(prompt)).strip()
        if value == BACK_VALUE:
            raise BackRequested
        if value:
            return value
        if fallback is not None:
            return fallback
        if not required:
            return ""
        print(f"{label} is required.")


def _prompt_custom_list(
    current: list[str],
    *,
    input_fn: InputFunction | None = None,
) -> list[str]:
    rendered = ", ".join(current) if current else "none"
    prompt = (
        "CODEX_CUSTOM_LIST (custom model JSON paths in merge order, "
        f"comma-separated; enter 'none' for none) [{rendered}]: "
    )
    value = (input_fn(prompt) if input_fn else _read_console(prompt)).strip()
    if value == BACK_VALUE:
        raise BackRequested
    if not value:
        return list(current)
    if value.lower() == "none":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _load_existing(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def collect_config(
    current: dict[str, object] | None = None,
    *,
    input_fn: InputFunction | None = None,
) -> dict[str, object]:
    """Prompt for each setting, allowing Esc to return to the previous one."""
    config = dict(current or {})
    keys = (
        "CODEX_CACHE_LATEST",
        "CODEX_CUSTOM_LIST",
        "CODEX_CATALOG_OUTPUT",
        "CODEX_MULTI_AGENT_POLICY",
    )
    defaults: dict[str, object] = {
        "CODEX_CACHE_LATEST": DEFAULT_CACHE_LATEST,
        "CODEX_CUSTOM_LIST": ["models_custom.json"],
        "CODEX_CATALOG_OUTPUT": DEFAULT_CATALOG_OUTPUT,
        "CODEX_MULTI_AGENT_POLICY": None,
    }
    index = 0
    history: list[int] = []
    while index < len(keys):
        key = keys[index]
        try:
            if key == "CODEX_CUSTOM_LIST":
                existing = config.get(key, defaults[key])
                if not isinstance(existing, list):
                    existing = defaults[key]
                value = _prompt_custom_list(
                    [str(item) for item in existing],
                    input_fn=input_fn,
                )
            else:
                existing = config.get(key)
                if not isinstance(existing, str):
                    existing = None
                fallback = existing
                if fallback is None:
                    default = defaults[key]
                    fallback = default if isinstance(default, str) else None
                value = _prompt(
                    {
                        "CODEX_CACHE_LATEST": "bundled baseline filename",
                        "CODEX_CATALOG_OUTPUT": "generated catalog filename",
                        "CODEX_MULTI_AGENT_POLICY": "v1, custom-v1, or preserve",
                    }[key],
                    variable_name=key,
                    current=fallback,
                    choices=POLICY_CHOICES if key == "CODEX_MULTI_AGENT_POLICY" else None,
                    required=True,
                    input_fn=input_fn,
                )
        except BackRequested:
            if not history:
                print("Already at the first setting.")
            else:
                index = history.pop()
            continue

        config[key] = value
        history.append(index)
        index += 1
    return {key: config[key] for key in keys}


def _confirm(input_fn: InputFunction | None = None) -> bool:
    while True:
        prompt = "Save this configuration? [y/N]: "
        value = (input_fn(prompt) if input_fn else _read_console(prompt)).strip().lower()
        if value in {"y", "yes"}:
            return True
        if value in {"", "n", "no", BACK_VALUE}:
            return False
        print("Enter 'y' or 'n'.")


def _display_path(path: Path) -> str:
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    return f"~/{relative.as_posix()}"


def configure(
    path: Path = CONFIG_PATH,
    *,
    input_fn: InputFunction | None = None,
) -> int:
    """Run the interactive configuration workflow."""
    print(f"Configure codex-model-catalog-manager and save to {_display_path(path)}.")
    print("Press Esc to return to the previous setting.")
    print()
    if path.is_file():
        current = _load_existing(path)
        print("Existing configuration loaded. Press Enter to keep each current value.")
    else:
        current = {}
    while True:
        config = collect_config(current, input_fn=input_fn)
        print("\nConfiguration summary:")
        print(json.dumps(config, ensure_ascii=False, indent=2))
        if _confirm(input_fn):
            write_config(config, path, force=True)
            print(f"Configuration saved to {path}")
            return 0
        current = config
        print("Configuration was not saved. Restarting with the entered values.\n")


def main() -> int:
    try:
        return configure()
    except (EOFError, KeyboardInterrupt):
        print("\nConfiguration cancelled. No changes were saved.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
