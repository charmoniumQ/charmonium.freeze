from . import (
    freeze_basic,
    freeze_files,
    freeze_function,
    freeze_objects,
    freeze_thirdparty,
    freeze_type,
)
import importlib.metadata
from .config import Config as Config
from .config import global_config as global_config
from .lib import FreezeError as FreezeError
from .lib import FreezeRecursionError as FreezeRecursionError
from .lib import UnfreezableTypeError as UnfreezableTypeError
from .lib import freeze as freeze
from .summarize_diff import ObjectLocation as ObjectLocation
from .summarize_diff import iterate_diffs as iterate_diffs
from .summarize_diff import iterate_diffs_of_frozen as iterate_diffs_of_frozen
from .summarize_diff import summarize_diffs as summarize_diffs
from .summarize_diff import summarize_diffs_of_frozen as summarize_diffs_of_frozen

__version__ = importlib.metadata.version("charmonium.freeze")
