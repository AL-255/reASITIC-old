"""Generate docs/repl/examples.json from tests/data/validation/*.json.

The REPL's Examples menu lets the user pick a captured design point
(from the binary-validated set) and play with it in the browser. To
make that work without round-trip server I/O, we materialise a slim
manifest at build time:

    [
      {"name": "...", "build_command": "...", "shape_name": "...",
       "tech_file": "..."},
      ...
    ]

The full validation JSONs are kept under tests/data/validation/ — we
only ship the four fields the REPL actually consumes.

Run from anywhere; the script resolves paths relative to its own
location:

    python docs/repl/build_examples.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPL_DIR = Path(__file__).resolve().parent
REPO_ROOT = REPL_DIR.parent.parent
VALIDATION_DIR = REPO_ROOT / "tests" / "data" / "validation"
OUT_PATH = REPL_DIR / "examples.json"


def main() -> None:
    if not VALIDATION_DIR.is_dir():
        raise SystemExit(f"validation directory not found: {VALIDATION_DIR}")

    examples = []
    for jf in sorted(VALIDATION_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        cmd = data.get("build_command")
        if not cmd:
            continue
        examples.append({
            "name": data.get("name", jf.stem),
            "build_command": cmd,
            "shape_name": data.get("shape_name", ""),
            "tech_file": data.get("tech_file", ""),
        })

    OUT_PATH.write_text(json.dumps(examples, indent=2))
    print(f"Wrote {OUT_PATH} ({len(examples)} entries)")


if __name__ == "__main__":
    main()
