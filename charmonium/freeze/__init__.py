from .lib import FreezeError as FreezeError
from .lib import FreezeRecursionError as FreezeRecursionError
from .lib import UnfreezableTypeError as UnfreezableTypeError
from .lib import config as config
from .lib import freeze as freeze
from .lib import freeze_dispatch as _freeze_dispatch
from .lib import _freeze as _freeze

__version__ = "0.5.4"
