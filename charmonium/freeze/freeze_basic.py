from __future__ import annotations

import io
import logging
import pathlib
import re
import types
from typing import Any, Dict, Hashable, Optional, Tuple

from .config import Config
from .lib import _freeze, freeze_attrs, freeze_dispatch, freeze_sequence


@freeze_dispatch.register(type(None))
@freeze_dispatch.register(int)
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(float)
@freeze_dispatch.register(complex)
@freeze_dispatch.register(type(...))
def _(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    # Object is already hashable.
    # No work to be done.
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: bytearray,
    _config: Config,
    _tabu: Dict[int, Tuple[int, int]],
    _depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return bytes(obj), False, None


@freeze_dispatch.register(set)
def _(
    obj: set[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, False, False, config, tabu, depth)


@freeze_dispatch.register(frozenset)
def _(
    obj: frozenset[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, True, False, config, tabu, depth)


@freeze_dispatch.register(list)
def _(
    obj: list[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, False, True, config, tabu, depth)


@freeze_dispatch.register(tuple)
def _(
    obj: Tuple[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, True, True, config, tabu, depth)


@freeze_dispatch.register(types.MappingProxyType)
def _(
    obj: types.MappingProxyType[Hashable, Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        obj.items(),
        True,
        not config.ignore_dict_order,
        config,
        tabu,
        depth,
    )


@freeze_dispatch.register(dict)
def _(
    obj: Dict[Hashable, Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        obj.items(),
        False,
        not config.ignore_dict_order,
        config,
        tabu,
        depth,
    )


@freeze_dispatch.register
def _(
    obj: types.ModuleType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.ignore_extensions and not hasattr(obj, "__file__"):
        return (obj.__name__, True, None)
    if hasattr(obj, "__file__") and any(
            ancestor in config.ignore_files
            for ancestor in pathlib.Path(obj.__file__).resolve().parents
    ):
        return (obj.__name__, True, None)
    attrs = {
        attr_name: getattr(obj, attr_name, None)
        for index, attr_name in enumerate(dir(obj))
        if hasattr(obj, attr_name)
        and attr_name not in config.ignore_module_attrs
        and (obj.__name__, attr_name) not in config.ignore_globals
    }
    return freeze_attrs(attrs, True, True, config, tabu, depth)


# pylint: disable=unused-argument
@freeze_dispatch.register
def _(
    obj: memoryview,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return obj.tobytes(), False, None


@freeze_dispatch.register
def _(
    obj: logging.Logger,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    # The client should be able to change the logger without changing the computation.
    # But the _name_ of the logger specifies where the side-effect goes, so it should matter.
    return obj.name, True, None


@freeze_dispatch.register(re.Match)
def _(
    obj: re.Match[str],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    ret = (obj.regs, _freeze(obj.re, config, tabu, depth, 0)[0], obj.string)
    return ret, True, None


@freeze_dispatch.register
def _(
    obj: io.BytesIO,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return obj.getvalue(), False, None


@freeze_dispatch.register
def _(
    obj: io.StringIO,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return obj.getvalue(), False, None
