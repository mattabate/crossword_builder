"""Entry point for ``python -m crossword_builder``."""
from .cli import main

# The guard matters: worker processes started with the "spawn" method import
# this module again, and must not start a second command line run.
if __name__ == "__main__":
    raise SystemExit(main())
