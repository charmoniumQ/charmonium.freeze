import types
from typing import Any, Hashable, Optional

from .lib import _freeze, combine_frozen, config, freeze_attrs, freeze_dispatch, logger


@freeze_dispatch.register(type)
def _(
    obj: type[Any],
    tabu: dict[int, tuple[int, int]],
    depth: int,
    index: int,
) -> tuple[Hashable, bool, Optional[int]]:
    assert obj == obj.__mro__[0]
    ret = freeze_class(obj.__mro__[0], tabu, depth, 0)
    for index, class_ in enumerate(obj.__mro__[1:]):
        # TODO: use index to freeze_class properly
        ret = combine_frozen(ret, freeze_class(class_, tabu, depth, index))
    return ret


def freeze_class(
    obj: type[Any],
    tabu: dict[int, tuple[int, int]],
    depth: int,
    index: int,
) -> tuple[Hashable, bool, Optional[int]]:
    type_pair = (obj.__module__, obj.__name__)
    if (
        (type_pair[0], None) in config.ignore_classes
        or type_pair in config.ignore_classes
        or obj is object
        # or (config.ignore_extensions and (
        #     not getattr(obj, "__module__", None)
        #     or (obj.__module__ != "__main__" and not getattr(sys.modules.get(object.__module__), "__file__", None))
        # ))
    ):
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return (b"class", ".".join(type_pair)), True, None
    ret = freeze_attrs(
        {
            key: val
            for index, (key, val) in enumerate(sorted(obj.__dict__.items()))
            if key not in special_class_attributes
            and (obj.__module__, obj.__name__, key) not in config.ignore_attributes
        },
        True,
        tabu,
        depth,
        index,
    )
    return (b"class", obj.__name__, ret[0]), ret[1], ret[2]


# TODO: Put this in config
special_class_attributes = {
    "__orig_bases__",
    "__dict__",
    "__weakref__",
    "__doc__",
    "__parameters__",
    "__slots__",
    "__slotnames__",
    "__mro_entries__",
    "__annotations__",
    "__hash__",
    # Some scripts are designed to be either executed or imported.
    # In that case, the __module__ can be either __main__ or a qualified module name.
    # As such, I exclude the name of the module containing the class.
    "__module__",
}


@freeze_dispatch.register
def _(
    obj: staticmethod, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    return _freeze(obj.__func__, tabu, depth - 1, index)


@freeze_dispatch.register
def _(
    obj: classmethod, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    return _freeze(obj.__func__, tabu, depth - 1, index)


@freeze_dispatch.register
def _(
    obj: types.MethodType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    return _freeze((obj.__self__, obj.__func__), tabu, depth - 1, index)


@freeze_dispatch.register
def _(
    obj: property, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    ret = (), True, None
    ret = combine_frozen(ret, _freeze(obj.fget, tabu, depth, 0))
    ret = combine_frozen(ret, _freeze(obj.fset, tabu, depth, 1))
    ret = combine_frozen(ret, _freeze(obj.fdel, tabu, depth, 2))
    return (b"property", *ret[0]), ret[1], ret[2]


@freeze_dispatch.register(types.WrapperDescriptorType)
@freeze_dispatch.register(types.MethodWrapperType)
@freeze_dispatch.register(types.MethodDescriptorType)
@freeze_dispatch.register(types.ClassMethodDescriptorType)
@freeze_dispatch.register(types.GetSetDescriptorType)
@freeze_dispatch.register(types.MemberDescriptorType)
def _(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    return (obj.__class__.__name__.encode(), obj.__name__), True, None
