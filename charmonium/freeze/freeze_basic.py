from __future__ import annotations

import io
import logging
import re
import types
from typing import Any, Dict, Hashable, Optional, Tuple

from .lib import _freeze, config, freeze_attrs, freeze_dispatch, freeze_sequence, logger


@freeze_dispatch.register(type(None))
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(int)
@freeze_dispatch.register(float)
@freeze_dispatch.register(complex)
@freeze_dispatch.register(type(...))
def _(
    obj: Any, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    # We must exclude obj if it occurs in the forbidden class, even though it is a subclass of a simple type.
    type_pair = (obj.__class__.__module__, obj.__class__.__name__)
    if type_pair in config.ignore_objects_by_class:
        logger.debug("%s ignoring %s (basic type) by class", " " * depth, type_pair)
        return type_pair, True, None
    # Object is already hashable.
    # No work to be done.
    return obj, True, None


@freeze_dispatch.register
def _(
    obj: bytearray, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return bytes(obj), False, None


@freeze_dispatch.register(set)
def _(
    obj: set[Any], tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, False, False, tabu, depth, 0)


@freeze_dispatch.register(frozenset)
def _(
    obj: frozenset[Any], tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, True, False, tabu, depth, 0)


@freeze_dispatch.register(list)
def _(
    obj: list[Any], tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, False, True, tabu, depth, 0)


@freeze_dispatch.register(tuple)
def _(
    obj: Tuple[Any], tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(obj, True, True, tabu, depth, 0)


@freeze_dispatch.register(types.MappingProxyType)
def _(
    obj: types.MappingProxyType[Hashable, Any],
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        obj.items(), True, not config.ignore_dict_order, tabu, depth, 0
    )


@freeze_dispatch.register(dict)
def _(
    obj: Dict[Hashable, Any], tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        obj.items(), False, not config.ignore_dict_order, tabu, depth, 0
    )


@freeze_dispatch.register
def _(
    obj: types.ModuleType, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.ignore_extensions and not getattr(obj, "__module__", None):
        return obj.__name__, True, None
    attrs = {
        attr_name: getattr(obj, attr_name, None)
        for index, attr_name in enumerate(dir(obj))
        if hasattr(obj, attr_name)
        and (obj.__name__, attr_name) not in config.ignore_globals
    }
    return freeze_attrs(attrs, True, tabu, depth, 0)


# pylint: disable=unused-argument
@freeze_dispatch.register
def _(
    obj: memoryview, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return obj.tobytes(), False, None


@freeze_dispatch.register
def _(
    obj: logging.Logger, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    # The client should be able to change the logger without changing the computation.
    # But the _name_ of the logger specifies where the side-effect goes, so it should matter.
    return obj.name, True, None


@freeze_dispatch.register(re.Match)
def _(
    obj: re.Match[str], tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return (obj.regs, _freeze(obj.re, tabu, depth, 0)[0], obj.string), True, None


@freeze_dispatch.register
def _(
    obj: io.BytesIO, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return obj.getvalue(), False, None


@freeze_dispatch.register
def _(
    obj: io.StringIO, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return obj.getvalue(), False, None
