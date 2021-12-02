from .lib import (
    freeze as freeze,
    freeze_dispatch as freeze_dispatch,
    get_recursion_limit as get_recursion_limit,
    set_recursion_limit as set_recursion_limit,
    with_recursion_limit as with_recursion_limit,
)

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "freeze",
    "get_recursion_limit",
    "set_recursion_limit",
    "with_recursion_limit",
]
