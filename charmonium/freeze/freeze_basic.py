import io
import logging
import re
import types
from typing import Any, Hashable

from .lib import _freeze, config, freeze_dispatch, immutable_if_children_are, logger
from .util import Ref

@freeze_dispatch.register(type(None))
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(int)
@freeze_dispatch.register(float)
@freeze_dispatch.register(complex)
@freeze_dispatch.register(type(...))
def _(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    # We must exclude obj if it occurs in the forbidden class, even though it is a subclass of a simple type.
    type_pair = (obj.__class__.__module__, obj.__class__.__name__)
    if type_pair in config.ignore_objects_by_class:
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return type_pair, True
    # Object is already hashable.
    # No work to be done.
    return obj, True


@freeze_dispatch.register
def _(
    obj: bytearray, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return bytes(obj), False


@freeze_dispatch.register(tuple)
def _(
    obj: tuple[Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    is_immutable = Ref(True)
    ret = tuple(
        immutable_if_children_are(_freeze(elem, tabu, depth, index), is_immutable)
        for index, elem in enumerate(obj)
    )
    return ret, is_immutable()


@freeze_dispatch.register(list)
def _(
    obj: list[Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return (
        tuple(_freeze(elem, tabu, depth, index)[0] for index, elem in enumerate(obj)),
        False,
    )


@freeze_dispatch.register(set)
def _(
    obj: set[Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return (
        frozenset(
            _freeze(elem, tabu, depth, index)[0] for index, elem in enumerate(obj)
        ),
        False,
    )


@freeze_dispatch.register(frozenset)
def _(
    obj: frozenset[Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    is_immutable = Ref(True)
    ret = frozenset(
        immutable_if_children_are(_freeze(elem, tabu, depth, index), is_immutable)
        for index, elem in enumerate(obj)
    )
    return ret, is_immutable()


@freeze_dispatch.register(types.MappingProxyType)
def _(
    obj: types.MappingProxyType[Hashable, Any],
    tabu: dict[int, tuple[int, int]],
    depth: int,
    index: int,
) -> tuple[Hashable, bool]:
    is_immutable = Ref(True)
    ret = tuple(
        (
            immutable_if_children_are(
                _freeze(key, tabu, depth, index * 2 + 0), is_immutable
            ),
            immutable_if_children_are(
                _freeze(val, tabu, depth, index * 2 + 1), is_immutable
            ),
        )
        for index, (key, val) in enumerate(sorted(obj.items()))
    )
    return ret, is_immutable()


@freeze_dispatch.register(dict)
def _(
    obj: dict[Hashable, Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    # The elements of a dict remember their insertion order, as of Python 3.7.
    # So I will hash this as an ordered collection.
    return (
        tuple(
            (
                _freeze(key, tabu, depth, index * 2 + 0),
                _freeze(val, tabu, depth, index * 2 + 1),
            )
            for index, (key, val) in enumerate(obj.items())
        ),
        False,
    )


@freeze_dispatch.register
def _(
    obj: staticmethod, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return _freeze(obj.__func__, tabu, depth, index)


@freeze_dispatch.register
def _(
    obj: classmethod, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return _freeze(obj.__func__, tabu, depth, index)


@freeze_dispatch.register
def _(
    obj: types.MethodType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    self_, self_immutable = _freeze(obj.__self__, tabu, depth, 0)
    func, func_immutable = _freeze(obj.__func__, tabu, depth, 1)
    return (self_, func), self_immutable and func_immutable


@freeze_dispatch.register
def _(
    obj: property, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    fget, fget_immutable = _freeze(obj.fget, tabu, depth, index)
    fset, fset_immutable = _freeze(obj.fset, tabu, depth, index)
    fdel, fdel_immutable = _freeze(obj.fdel, tabu, depth, index)
    return (fget, fset, fdel), fget_immutable and fset_immutable and fdel_immutable


@freeze_dispatch.register(types.WrapperDescriptorType)
@freeze_dispatch.register(types.MethodWrapperType)
@freeze_dispatch.register(types.MethodDescriptorType)
@freeze_dispatch.register(types.ClassMethodDescriptorType)
@freeze_dispatch.register(types.GetSetDescriptorType)
@freeze_dispatch.register(types.MemberDescriptorType)
def _(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return (obj.__class__.__name__, obj.__name__), True


@freeze_dispatch.register
def _(
    obj: types.BuiltinFunctionType,
    tabu: dict[int, tuple[int, int]],
    depth: int,
    index: int,
) -> tuple[Hashable, bool]:
    return ("builtin func", obj.__name__), True


@freeze_dispatch.register
def _(
    obj: types.ModuleType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    if config.ignore_extensions and not getattr(obj, "__module__", None):
        return obj.__name__, True
    is_immutable = Ref(True)
    ret = tuple(
        (
            attr_name,
            immutable_if_children_are(_freeze(getattr(obj, attr_name, None), tabu, depth, index), is_immutable)
        )
        for index, attr_name in enumerate(dir(obj))
        if hasattr(obj, attr_name)
    )
    return ret, is_immutable()


# pylint: disable=unused-argument
@freeze_dispatch.register
def _(
    obj: memoryview, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return obj.tobytes(), False


@freeze_dispatch.register
def _(
    obj: types.GeneratorType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return _freeze(obj.gi_frame, tabu, depth, index)


@freeze_dispatch.register
def _(
    obj: logging.Logger, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    # The client should be able to change the logger without changing the computation.
    # But the _name_ of the logger specifies where the side-effect goes, so it should matter.
    return obj.name, True


@freeze_dispatch.register(re.Match)
def _(obj: re.Match[str], tabu: set[int], depth: int, index: int) -> Hashable:
    return (obj.regs, _freeze(obj.re, tabu, depth, index)[0], obj.string), True


@freeze_dispatch.register
def _(
    obj: io.BytesIO, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return obj.getvalue(), False


@freeze_dispatch.register
def _(
    obj: io.StringIO, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    return obj.getvalue(), False
