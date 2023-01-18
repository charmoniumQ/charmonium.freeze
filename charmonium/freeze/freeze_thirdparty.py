from __future__ import annotations

import io
import pickle
from typing import Any, Dict, Hashable, Optional, Tuple

from .config import Config
from .lib import UnfreezableTypeError, freeze_dispatch

try:
    import numpy
except ImportError:
    pass
else:

    @freeze_dispatch.register(numpy.ndarray)
    def _(
        obj: numpy.typing.NDArray[Any],
        config: Config,
        tabu: Dict[int, Tuple[int, int]],
        depth: int,
        index: int,
    ) -> Tuple[Hashable, bool, Optional[int]]:
        return ("numpy.ndarray", obj.tobytes(), str(obj.dtype)), False, None


try:
    import matplotlib.figure  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(
        obj: matplotlib.figure.Figure,
        _config: Config,
        _tabu: Dict[int, Tuple[int, int]],
        _depth: int,
        _index: int,
    ) -> Tuple[Hashable, bool, Optional[int]]:
        file = io.BytesIO()
        obj.savefig(file, format="raw")
        return file.getvalue(), False, None


try:
    import pandas
except ImportError:
    pass
else:

    @freeze_dispatch.register(pandas.DataFrame)
    @freeze_dispatch.register(pandas.Series)  # type: ignore
    @freeze_dispatch.register(pandas.Index)  # type: ignore
    def _(
        obj: Any,
        config: Config,
        tabu: Dict[int, Tuple[int, int]],
        depth: int,
        index: int,
    ) -> Tuple[Hashable, bool, Optional[int]]:
        return pickle.dumps(obj), True, None


# TODO: See if we can support this anyway.
# If not, use config.ignore attributes instead.
try:
    import pymc3  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(
        obj: pymc3.Model,
        config: Config,
        tabu: Dict[int, Tuple[int, int]],
        depth: int,
        index: int,
    ) -> Tuple[Hashable, bool, Optional[int]]:
        raise UnfreezableTypeError(
            "pymc3.Model has been known to cause problems due to its not able to be pickled."
        )
