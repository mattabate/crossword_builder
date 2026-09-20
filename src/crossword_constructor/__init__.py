"""crossword_constructor: fill crossword grids from a template and a wordlist."""

__version__ = "0.1.0"

from .context import ConstructorConfig, ConstructorContext
from .grid import (
    C_UNKNOWN,
    C_WALL,
    Direction,
    Grid,
    TemplateError,
    parse_template,
    parse_templates,
    read_template,
    read_templates,
)
from .runner import RunOptions, RunResult, run_search
from .wordlist import WordIndex, load_wordlist

__all__ = [
    "C_UNKNOWN",
    "C_WALL",
    "ConstructorConfig",
    "ConstructorContext",
    "Direction",
    "Grid",
    "RunOptions",
    "RunResult",
    "TemplateError",
    "WordIndex",
    "__version__",
    "load_wordlist",
    "parse_template",
    "parse_templates",
    "read_template",
    "read_templates",
    "run_search",
]
