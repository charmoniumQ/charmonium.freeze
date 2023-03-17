
from __future__ import annotations

import types
from typing import Any, Dict, Hashable, Optional, Tuple, Type

from .config import Config
from .lib import (
    _freeze,
    combine_frozen,
    freeze_attrs,
    freeze_dispatch,
    freeze_sequence,
    logger,
)


# Note that
#
#    nix shell nixpkgs#python310 --command python -c 'print(set[int].__class__)'
#    <class 'type'>
#
# while
#
#    nix shell nixpkgs#python310 --command python -c 'print(set[int].__class__)'
#    <class 'types.GenericAlias'>
#
# (as it should)
# Therefore, singledispatch doesn't dispatch generic aliases correctly until 3.11
def freeze_generic_alias(
    obj: types.GenericAlias,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        (obj.__origin__, *obj.__args__),
        order_matters=True,
        is_immutable=True,
        config=config,
        tabu=tabu,
        depth=depth,
    )


@freeze_dispatch.register(type)
def _(
    obj: Type[Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if hasattr(obj, "__origin__") and hasattr(obj, "__args__"):
        return freeze_generic_alias(obj, config, tabu, depth, index)
    assert obj == obj.__mro__[0]
    ret = freeze_class(obj.__mro__[0], config, tabu, depth, index)
    if len(obj.__mro__) > 1:
        ret2 = _freeze(obj.__mro__[1], config, tabu, depth, index)
        return combine_frozen(ret, ret2, config)
    else:
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
        return freeze_sequence(type_pair, True, True, config, tabu, depth)
    attrs, attrs_immutable, attrs_level = freeze_attrs(
        {
            key: val
            for index, (key, val) in enumerate(sorted(obj.__dict__.items()))
            if key not in config.special_class_attributes
            and (obj.__module__, obj.__name__, key) not in config.ignore_attributes
        },
        # NOTE: this says that a class never gets new attributes and attributes never get reassigned.
        # E.g., If A.x is a list, A is mutable; if A.x is a tuple, A is immutable (assume no A.y = 3 and no A.y = different_tuple).
        is_immutable=True,
        write_attrs=True,
        config=config,
        tabu=tabu,
        depth=depth,
    )
    return freeze_sequence(
        (obj.__name__, attrs),
        is_immutable=attrs_immutable,
        order_matters=False,
        config=config,
        tabu=tabu,
        depth=depth,
    )


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
    return freeze_attrs(
        {
            "fget": obj.fget,
            "fset": obj.fset,
            "fdel": obj.fdel,
        },
        is_immutable=True,
        write_attrs=False,
        config=config,
        tabu=tabu,
        depth=depth,
    )


@freeze_dispatch.register(types.WrapperDescriptorType)
@freeze_dispatch.register(types.MethodWrapperType)
@freeze_dispatch.register(types.MethodDescriptorType)
@freeze_dispatch.register(types.ClassMethodDescriptorType)
@freeze_dispatch.register(types.GetSetDescriptorType)
@freeze_dispatch.register(types.MemberDescriptorType)
def _(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        (obj.__class__.__name__.encode(), obj.__name__.encode()),
        is_immutable=True,
        order_matters=True,
        config=config,
        tabu=tabu,
        depth=depth,
    )
