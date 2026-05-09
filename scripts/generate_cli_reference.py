#!/usr/bin/env python3
"""Generate the CLI command reference markdown from the live dispatcher.

Run with::

    python scripts/generate_cli_reference.py > CLI_REFERENCE.md

Reads :data:`reasitic.cli._COMMAND_HELP` and emits a sorted Markdown
table. Run after adding new commands to keep the reference in sync.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reasitic.cli import _COMMAND_CATEGORIES, _COMMAND_HELP


def main() -> None:
    print("# reASITIC CLI command reference")
    print()
    print(
        "Auto-generated from `reasitic.cli._COMMAND_HELP`. "
        "Re-run `python scripts/generate_cli_reference.py` after adding new commands."
    )
    print()
    print(_COMMAND_CATEGORIES)
    print()
    print("## Command details")
    print()
    print("| Command | Description |")
    print("|---|---|")
    for name in sorted(_COMMAND_HELP):
        desc = _COMMAND_HELP[name]
        # Markdown table row escaping
        desc_md = desc.replace("|", "\\|")
        print(f"| `{name}` | {desc_md} |")


if __name__ == "__main__":
    main()
