"""``python -m reasitic.gui`` — open the reASITIC graphical workspace.

Usage::

    python -m reasitic.gui
    python -m reasitic.gui -t run/tek/BiCMOS.tek
    python -m reasitic.gui -s session.json
"""

from __future__ import annotations

import argparse
import sys

from reasitic.gui import run


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``reasitic-gui`` console script."""
    parser = argparse.ArgumentParser(prog="reasitic-gui")
    parser.add_argument("-t", "--tech", help="tech file to load on startup")
    parser.add_argument("-s", "--session",
                        help="JSON session to load on startup")
    args = parser.parse_args(argv)
    try:
        run(tech_path=args.tech, session_path=args.session)
    except RuntimeError as exc:
        # Tk raises RuntimeError when there's no display. Make the
        # failure explanation friendly.
        print(f"reasitic-gui: {exc}", file=sys.stderr)
        print("(no DISPLAY available — run on a desktop session, or under "
              "xvfb-run for tests)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
