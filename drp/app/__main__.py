"""Allow `python -m drp.app` as well as the `drp` console script."""
from drp.app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
