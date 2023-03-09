from __future__ import annotations

import io
import pickle
from typing import Any, Dict, Hashable, Optional, Tuple

from .config import Config
from .lib import UnfreezableTypeError, freeze_dispatch, freeze_sequence

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
        return freeze_sequence(
            (str(obj.dtype), obj.tobytes()),
            is_immutable=False,
            order_matters=True,
            config=config,
            tabu=tabu,
            depth=depth,
        )


try:
    import matplotlib.figure  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(
        obj: matplotlib.figure.Figure,
        config: Config,
        _tabu: Dict[int, Tuple[int, int]],
        _depth: int,
        _index: int,
    ) -> Tuple[Hashable, bool, Optional[int]]:
        file = io.BytesIO()
        obj.savefig(file, format="raw")
        if config.use_hash:
            return config.hasher(file.getvalue()), False, None
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
        if config.use_hash:
            return config.hasher(pickle.dumps(obj)), False, None
        return pickle.dumps(obj), False, None


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
