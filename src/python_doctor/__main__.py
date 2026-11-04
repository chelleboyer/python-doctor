"""Allow ``python -m python_doctor``."""

from python_doctor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
