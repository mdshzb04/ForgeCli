"""TOML writer helper to update ForgeCLI config settings on the fly."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]


def dump_toml(data: dict[str, Any]) -> str:
    """Serialize a dictionary to a basic TOML string (handles flat tables and primitive values)."""
    lines = []
    # Write top-level key-values first
    for k, v in sorted(data.items()):
        if not isinstance(v, dict):
            if isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, list):
                items = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
                lines.append(f"{k} = [{items}]")

    # Write tables
    for section_name, section_val in sorted(data.items()):
        if isinstance(section_val, dict):
            lines.append(f"\n[{section_name}]")
            for k, v in sorted(section_val.items()):
                if isinstance(v, bool):
                    lines.append(f"{k} = {str(v).lower()}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{k} = {v}")
                elif isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                elif isinstance(v, list):
                    items = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
                    lines.append(f"{k} = [{items}]")

    return "\n".join(lines).strip() + "\n"


def update_config(default_provider: str | None = None, default_model: str | None = None) -> Path:
    """Update defaults in the active forgecli.toml configuration file."""
    from forgecli.config.loader import ConfigLoader

    loader = ConfigLoader()
    # Find existing writeable candidate config file
    candidates = loader._candidate_paths()
    target_path = None
    for p in candidates:
        if p.exists() and p.name != "pyproject.toml":
            target_path = p
            break

    if not target_path:
        target_path = Path("./forgecli.toml")

    data: dict[str, Any] = {}
    if target_path.exists():
        with contextlib.suppress(Exception):
            data = tomllib.loads(target_path.read_text(encoding="utf-8"))

    if "providers" not in data:
        data["providers"] = {}

    if default_provider is not None:
        data["providers"]["default"] = default_provider

    if default_model is not None:
        data["providers"]["default_model"] = default_model

    content = dump_toml(data)
    target_path.write_text(content, encoding="utf-8")
    return target_path
