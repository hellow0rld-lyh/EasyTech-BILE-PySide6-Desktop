"""Package entry point; keeps bile_workbench.app imported as a package."""
from bile_workbench.app import run


if __name__ == "__main__":
    raise SystemExit(run())
