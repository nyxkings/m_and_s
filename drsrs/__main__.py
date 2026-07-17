"""Allow `python -m drsrs` and `python -m drsrs.main`."""

from drsrs.main import main

if __name__ == "__main__":
    raise SystemExit(main())
