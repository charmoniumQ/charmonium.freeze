from .lib import FreezeError as FreezeError
from .lib import FreezeRecursionError as FreezeRecursionError
from .lib import UnfreezableTypeError as UnfreezableTypeError
from .lib import config as config
from .lib import freeze as freeze

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "freeze",
    "config",
    "UnfreezableTypeError",
    "FreezeRecursionError",
    "FreezeError",
]
