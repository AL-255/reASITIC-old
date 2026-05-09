"""Top-level command-line entry: ``python -m reasitic``.

Default behaviour delegates to :func:`reasitic.cli.main` (the REPL).
A ``help`` sub-command prints the docstring of any public symbol::

    python -m reasitic help compute_self_inductance
    python -m reasitic help reasitic.network.spiral_y_at_freq
"""

from __future__ import annotations

import importlib
import sys


def _print_help_for(name: str) -> int:
    if "." in name:
        module, _, attr = name.rpartition(".")
        try:
            mod = importlib.import_module(module)
        except ImportError as e:
            print(f"Error: {e}")
            return 1
        if not hasattr(mod, attr):
            print(f"No attribute {attr!r} in module {module!r}")
            return 1
        target = getattr(mod, attr)
    else:
        # Try to resolve from the top-level reasitic package
        import reasitic
        target = getattr(reasitic, name, None)
        if target is None:
            print(f"No public symbol {name!r} in reasitic")
            print("Tip: prefix with module path, e.g. reasitic.network.spiral_y_at_freq")
            return 1
    doc = getattr(target, "__doc__", None) or "(no docstring)"
    print(f"=== {name} ===")
    print(doc)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m reasitic``."""
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] == "help" and len(args) >= 2:
        return _print_help_for(args[1])
    # Otherwise run the REPL
    from reasitic.cli import main as cli_main
    return cli_main(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
