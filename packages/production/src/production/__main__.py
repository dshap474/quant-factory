"""Run the explicit production operator CLI as a Python module.

Usage:
    python -m production --help
"""

from production.cli import main

# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    raise SystemExit(main())
