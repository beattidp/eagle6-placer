#!/usr/bin/env python3
"""Install the eagle6-placer Antigravity global plugin into ~/.gemini/config/plugins/."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "eagle6-placer"
ENTRY_POINT = "eagle6-placer-mcp"


def resolve_entry_point() -> str:
    """Resolve the active virtualenv entry point so Antigravity GUI finds it without shell shims."""
    candidate = Path(sys.executable).parent / ENTRY_POINT
    if candidate.is_file():
        return str(candidate)
    which = shutil.which(ENTRY_POINT)
    return which or ENTRY_POINT


def build_mcp_config(command: str) -> dict[str, object]:
    return {"mcpServers": {PLUGIN_NAME: {"command": command}}}


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Install the {PLUGIN_NAME} Antigravity plugin.")
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path.home() / ".gemini" / "config" / "plugins" / PLUGIN_NAME,
        help="Target plugin directory (default: ~/.gemini/config/plugins/eagle6-placer)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be installed without modifying disk.",
    )
    args = parser.parse_args()

    src_dir = Path(__file__).resolve().parent.parent / "plugin"
    if not (src_dir / "plugin.json").is_file():
        print(f"Error: plugin bundle not found at {src_dir}", file=sys.stderr)
        return 1

    command = resolve_entry_point()
    mcp_cfg = build_mcp_config(command)

    if args.dry_run:
        print(f"[dry-run] Would copy {src_dir} -> {args.dest}")
        print("[dry-run] Would write mcp_config.json:")
        print(json.dumps(mcp_cfg, indent=2))
        return 0

    dest: Path = args.dest.expanduser()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dest)
    (dest / "mcp_config.json").write_text(json.dumps(mcp_cfg, indent=2) + "\n", encoding="utf-8")

    print(f"Installed {PLUGIN_NAME} plugin to {dest}")
    print(f"  MCP command : {command}")
    print(f"  Logo asset  : {dest / 'assets' / 'logo.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
