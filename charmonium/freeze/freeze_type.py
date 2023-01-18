from __future__ import annotations

import types
from typing import Any, Dict, Hashable, Optional, Tuple, Type

from .config import Config
from .lib import _freeze, combine_frozen, freeze_attrs, freeze_dispatch, logger


@freeze_dispatch.register(type)
def _(
    obj: Type[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    assert obj == obj.__mro__[0]
    ret = freeze_class(obj.__mro__[0], config, tabu, depth, index)
    for subindex, class_ in enumerate(obj.__mro__[1:]):
        ret = combine_frozen(ret, freeze_class(class_, config, tabu, depth, subindex))
    return ret


def freeze_class(
    obj: Type[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    type_pair = (obj.__module__, obj.__name__)
    if (
        config.ignore_all_classes
        or (type_pair[0], None) in config.ignore_classes
        or type_pair in config.ignore_classes
        or obj is object
        # or (config.ignore_extensions and (
        #     not getattr(obj, "__module__", None)
        #     or (obj.__module__ != "__main__" and not getattr(sys.modules.get(object.__module__), "__file__", None))
        # ))
    ):
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return (b"class", ".".join(type_pair)), True, None
    # NOTE: this says that a class never gets new attributes and attributes never get reassigned.
    # E.g., If A.x is a list, A is mutable; if A.x is a tuple, A is immutable (assume no A.y = 3 and no A.y = different_tuple).
    ret = freeze_attrs(
        {
            key: val
            for index, (key, val) in enumerate(sorted(obj.__dict__.items()))
            if key not in config.special_class_attributes
            and (obj.__module__, obj.__name__, key) not in config.ignore_attributes
        },
        True,
        True,
        config,
        tabu,
        depth,
    )
    return (b"class", obj.__name__, ret[0]), ret[1], ret[2]


@freeze_dispatch.register(staticmethod)
def _(
    obj: staticmethod[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return _freeze(obj.__func__, config, tabu, depth - 1, index)


@freeze_dispatch.register(classmethod)
def _(
    obj: classmethod[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return _freeze(obj.__func__, config, tabu, depth - 1, index)


@freeze_dispatch.register
def _(
    obj: types.MethodType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return _freeze((obj.__self__, obj.__func__), config, tabu, depth - 1, index)


@freeze_dispatch.register
def _(
    obj: property,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    ret: tuple[Hashable, bool, Optional[int]] = (), True, None
    ret = combine_frozen(ret, _freeze(obj.fget, config, tabu, depth, 0))
    ret = combine_frozen(ret, _freeze(obj.fset, config, tabu, depth, 1))
    ret = combine_frozen(ret, _freeze(obj.fdel, config, tabu, depth, 2))
    return (b"property", *ret[0]), ret[1], ret[2]


@freeze_dispatch.register(types.WrapperDescriptorType)
@freeze_dispatch.register(types.MethodWrapperType)
@freeze_dispatch.register(types.MethodDescriptorType)
@freeze_dispatch.register(types.ClassMethodDescriptorType)
@freeze_dispatch.register(types.GetSetDescriptorType)
@freeze_dispatch.register(types.MemberDescriptorType)
def _(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return (obj.__class__.__name__.encode(), obj.__name__), True, None
