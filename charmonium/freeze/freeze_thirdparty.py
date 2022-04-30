from __future__ import annotations

import io
from typing import Any, Hashable

from .lib import (
    UnfreezableTypeError,
    _freeze,
    config,
    freeze_dispatch,
    immutable_if_children_are,
)


try:
    import numpy
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(
        obj: numpy.ndarray, tabu: dict[int, tuple[int, int]], depth: int, index: int
    ) -> tuple[Hashable, bool]:
        return ("numpy.ndarray", obj.tobytes(), str(obj.dtype)), False

# TODO: use config.ignore_attributes instead.
try:
    import tqdm  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register(tqdm.tqdm)
    def _(
        obj: tqdm.tqdm[Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
    ) -> tuple[Hashable, bool]:
        # Unfortunately, the tqdm object contains the timestamp of the last ping, which would result in a different state every time.
        return _freeze(obj.iterable, tabu, depth, index)[0], False


try:
    import matplotlib.figure  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(
        obj: matplotlib.figure.Figure,
        tabu: dict[int, tuple[int, int]],
        depth: int,
        index: int,
    ) -> tuple[Hashable, bool]:
        file = io.BytesIO()
        obj.savefig(file, format="raw")
        return file.getvalue(), False


# TODO: use config.ignore_attributes instead.
try:
    import pymc3  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(
        obj: pymc3.Model, tabu: dict[int, tuple[int, int]], depth: int, index: int
    ) -> tuple[Hashable, bool]:
        raise UnfreezableTypeError(
            "pymc3.Model has been known to cause problems due to its not able to be pickled."
        )
