from __future__ import annotations

import copyreg
import functools
import importlib
import io
import json
import logging
import re
import sys
import textwrap
import types
import weakref
from typing import Any, Callable, Dict, Hashable, List, Set, Tuple, Type, cast

from .util import getclosurevars, has_callable, specializes_pickle

logger = logging.getLogger("charmonium.freeze")


class Config:
    recursion_limit = 50
    constant_modules = {
        "copyreg",
    }
    constant_modules_regex = [
        re.compile("matplotlib[.].*"),
        re.compile("theano[.].*"),
        re.compile("numpy[.].*"),
    ]


config = Config()


def freeze(obj: Any) -> Hashable:
    "Injectively, deterministically maps objects to hashable, immutable objects."
    logger.debug("freeze begin")
    ret = freeze_helper(obj, set(), 0)
    logger.debug("freeze end")
    return ret


class FreezeError(Exception):
    pass


class UnfreezableTypeError(FreezeError):
    pass


class FreezeRecursionError(FreezeError):
    pass


def freeze_helper(obj: Any, tabu: Set[int], level: int) -> Hashable:
    if level > config.recursion_limit:
        raise FreezeRecursionError(f"Maximum recursion depth {config.recursion_limit}")

    if logger.isEnabledFor(logging.DEBUG):
        if not isinstance(obj, (str, bytes, int, float, complex, type(None))):
            logger.debug(
                " ".join(
                    [
                        level * " ",
                        type(obj).__name__,
                        textwrap.shorten(repr(obj), width=150),
                    ]
                )
            )
    if id(obj) in tabu:
        return b"cycle"
    else:
        return freeze_dispatch(obj, tabu, level)


def freeze_pickle(obj: Any, tabu: Set[int], level: int) -> Hashable:
    # I wish I didn't support 3.7, so I could use walrus operator
    getnewargs_ex = has_callable(obj, "__getnewargs_ex__")
    getnewargs = has_callable(obj, "__getnewargs__")
    reduce_ex = cast(
        Callable[[int], Tuple[Any, ...]], has_callable(obj, "__reduce_ex__")
    )
    reduce = cast(Callable[[int], Tuple[Any, ...]], has_callable(obj, "__reduce__"))

    if reduce_ex:
        reduced = reduce_ex(4)
    elif reduce:
        reduced = reduce()
    else:
        raise TypeError(f"{type(obj)} {obj} is not picklable")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            " ".join(
                [
                    level * " ",
                    "reduce",
                    textwrap.shorten(repr(obj), width=150),
                ]
            )
        )

    if getnewargs_ex:
        new_args, new_kwargs = getnewargs_ex()
    elif getnewargs:
        new_args, new_kwargs = getnewargs(), {}
    else:
        new_args, new_kwargs = (), {}

    if isinstance(reduced, str):
        return reduced
    else:
        assert isinstance(reduced, tuple)
        assert 2 <= len(reduced) <= 5
        constructor = reduced[0]
        constructor_args = reduced[1]
        state = reduced[2] if len(reduced) > 2 else getattr(obj, "__dict__", {})
        list_items = list(reduced[3]) if len(reduced) > 3 and reduced[3] else []
        dict_items = list(reduced[4]) if len(reduced) > 4 and reduced[4] else []
        return freeze_helper(
            (
                *(
                    (constructor,)
                    if constructor not in {getattr(copyreg, "__newobj__", None)}
                    else ()
                ),
                *(constructor_args if constructor_args else ()),
                *((state,) if state else ()),
                *((list_items,) if list_items else ()),
                *((dict_items,) if dict_items else ()),
                *((new_args,) if new_args else ()),
                *((new_kwargs,) if new_kwargs else ()),
            ),
            tabu,
            level + 1,
        )


@functools.singledispatch
def freeze_dispatch(obj: Any, tabu: Set[int], level: int) -> Hashable:
    getfrozenstate = has_callable(obj, "__getfrozenstate__")
    tabu = tabu | {id(obj)}
    if getfrozenstate:
        return freeze_helper(getfrozenstate(), tabu, level + 1)
    if specializes_pickle(obj):
        return freeze_pickle(obj, tabu, level)
    else:
        raise UnfreezableTypeError("not implemented")


@freeze_dispatch.register(type(None))
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(int)
@freeze_dispatch.register(float)
@freeze_dispatch.register(complex)
@freeze_dispatch.register(type(...))
def _(obj: Hashable, tabu: Set[int], level: int) -> Hashable:
    return obj


@freeze_dispatch.register
def _(obj: bytearray, _tabu: Set[int], _level: int) -> Hashable:
    return bytes(obj)


@freeze_dispatch.register(tuple)
@freeze_dispatch.register(list)
def _(obj: List[Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return tuple(freeze_helper(elem, tabu, level + 1) for elem in cast(List[Any], obj))


@freeze_dispatch.register(set)
@freeze_dispatch.register(frozenset)
@freeze_dispatch.register(weakref.WeakSet)
def _(obj: Set[Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return frozenset(
        freeze_helper(elem, tabu, level + 1) for elem in cast(Set[Any], obj)
    )


@freeze_dispatch.register(dict)
@freeze_dispatch.register(types.MappingProxyType)
@freeze_dispatch.register(weakref.WeakKeyDictionary)
@freeze_dispatch.register(weakref.WeakValueDictionary)
def _(obj: dict[Any, Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    # The elements of a dict remember their insertion order, as of Python 3.7.
    # So I will hash this as an ordered collection.
    return tuple(
        (freeze_helper(key, tabu, level + 1), freeze_helper(val, tabu, level + 1))
        for key, val in list(cast(Dict[Any, Any], obj).items())
    )


@freeze_dispatch.register
def _(obj: memoryview, tabu: Set[int], level: int) -> Hashable:
    return freeze_helper(
        obj.tobytes(),
        tabu | {id(obj)},
        level + 1,
    )


def freeze_module(module: str) -> Hashable:
    parts = module.split(".")
    parent_modules = [parts[0]]
    for part in parts[1:]:
        parent_modules.append(parent_modules[-1] + "." + part)
    versions = list(
        filter(
            bool,
            [
                getattr(importlib.import_module(module), "__version__", None)
                for module in parent_modules
            ],
        )
    )
    return (module,) + tuple(versions)


@freeze_dispatch.register
def _(obj: types.FunctionType, tabu: Set[int], level: int) -> Hashable:
    if obj.__module__ in config.constant_modules:
        return (freeze_module(obj.__module__), obj.__qualname__)
    for module_regex in config.constant_modules_regex:
        if module_regex.search(obj.__module__):
            return (freeze_module(obj.__module__), obj.__qualname__)
    tabu = tabu | {id(obj)}
    closure = getclosurevars(obj)
    return (
        freeze_helper(obj.__code__, tabu, level + 1),
        freeze_helper(closure.nonlocals, tabu, level + 1),
        freeze_helper(closure.globals, tabu, level + 1),
    )


@freeze_dispatch.register
def _(obj: types.BuiltinFunctionType, _tabu: Set[int], _level: int) -> Hashable:
    return obj.__name__


@freeze_dispatch.register
def _(obj: types.CodeType, tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return (
        obj.co_name,  # name of function
        obj.co_varnames,  # argument names and local var names
        freeze_helper(obj.co_consts, tabu, level + 1),  # constants used by code
        freeze_helper(obj.co_code, tabu, level + 1),  # source code of function
    )


@freeze_dispatch.register
def _(obj: types.ModuleType, _tabu: Set[int], _level: int) -> Hashable:
    return freeze_module(obj.__name__)


@freeze_dispatch.register
def _(obj: logging.Logger, _tabu: Set[int], _level: int) -> Hashable:
    # The client should be able to change the logger without changing the computation.
    # But the _name_ of the logger specifies where the side-effect goes, so it should matter.
    return obj.name


@freeze_dispatch.register(type)
def _(obj: Type[Any], _tabu: Set[int], _level: int) -> Hashable:
    return obj.__qualname__
    # raise NotImplementedError("`freeze` is Not implemented for types")


@freeze_dispatch.register
def _(obj: io.BytesIO, _tabu: Set[int], _level: int) -> Hashable:
    return obj.getvalue()


@freeze_dispatch.register
def _(obj: io.StringIO, _tabu: Set[int], _level: int) -> Hashable:
    return obj.getvalue()


@freeze_dispatch.register
def _(obj: io.TextIOBase, tabu: Set[int], level: int) -> Hashable:
    if hasattr(obj, "buffer"):
        return freeze_helper(obj.buffer, tabu, level)
    else:
        raise UnfreezableTypeError(
            f"Don't know how to serialize {type(obj)} {obj}. See source code for special cases."
        )


@freeze_dispatch.register
def _(obj: io.BufferedWriter, _tabu: Set[int], _level: int) -> Hashable:
    # If a buffered writers is both pointing to the same file, writing on it has the same side-effect.
    # Otherwise, it has a different side-effect.
    name = getattr(obj, "name", None)
    if name:
        # Since pytest captures stderr and stdout, they are renamed to <stderr> and <stdout>, but not when run natively
        # This standardization helps me pass the tests.
        return {"stderr": "<stderr>", "stdout": "<stdout>"}.get(name, name)
    else:
        raise UnfreezableTypeError(
            "There's no way to know the side-effects of writing to an `io.BufferedWriter`, without knowing its filename."
        )


@freeze_dispatch.register
def _(obj: io.BufferedReader, _tabu: Set[int], _level: int) -> Hashable:
    raise UnfreezableTypeError(
        f"Cannot freeze readable non-seekable streams such as {obj}. I have no way of knowing your position in the stream without modifying it."
    )


@freeze_dispatch.register
def _(obj: io.BufferedRandom, _tabu: Set[int], _level: int) -> Hashable:
    name = getattr(obj, "name", None)
    if name is not None:
        cursor = obj.tell()
        obj.seek(0, io.SEEK_SET)
        value = obj.read()
        obj.seek(cursor, io.SEEK_SET)
        # `(value, cursor)` determines the side-effect of reading.
        # `(name, cursor)` determines the side-effect of writing.
        return (cursor, value, name)
    else:
        raise UnfreezableTypeError(
            f"Don't know how to serialize {type(obj)} {obj} because it doesn't have a filename."
        )


@freeze_dispatch.register
def _(obj: io.FileIO, _tabu: Set[int], _level: int) -> Hashable:
    if obj.fileno() == sys.stderr.fileno():
        return "<stderr>"
    elif obj.fileno() == sys.stdout.fileno():
        return "<stdout>"
    elif obj.mode in {"w", "x", "a", "wb", "xb", "ab"}:
        return obj.name
    elif obj.mode in {"r", "rb"}:
        raise UnfreezableTypeError(
            f"Cannot freeze readable non-seekable streams such as {obj}."
        )
    elif obj.mode in {"w+", "r+", "wb+", "rb+"}:
        name = getattr(obj, "name", None)
        if name is not None:
            cursor = obj.tell()
            obj.seek(0, io.SEEK_SET)
            value = obj.read()
            obj.seek(cursor, io.SEEK_SET)
            # `(value, cursor)` determines the side-effect of reading.
            # `(name, cursor)` determines the side-effect of writing.
            return (cursor, value, name)
        else:
            raise UnfreezableTypeError(
                f"Don't know how to serialize {type(obj)} {obj} because it doesn't have a filename."
            )
    else:
        raise UnfreezableTypeError(
            f"{obj.name} {obj.mode} must be a special kind of file."
        )


@freeze_dispatch.register(re.Pattern)
def _(obj: re.Pattern[str], tabu: Set[int], level: int) -> Hashable:
    return (obj.flags, obj.pattern)


@freeze_dispatch.register(re.Match)
def _(obj: re.Match[str], tabu: Set[int], level: int) -> Hashable:
    return (obj.regs, freeze_helper(obj.re, tabu, level + 1), obj.string)


try:
    import tqdm  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register(tqdm.tqdm)
    def _(obj: tqdm.tqdm[Any], tabu: Set[int], level: int) -> Hashable:
        # Unfortunately, the tqdm object contains the timestamp of the last pring, which would result in a different state every time.
        return freeze_helper(obj.iterable, tabu | {id(obj)}, level + 1)


try:
    import matplotlib.figure  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(obj: matplotlib.figure.Figure, tabu: Set[int], level: int) -> Hashable:
        try:
            import mpld3  # noqa: autoimport
        except ImportError as e:
            raise RuntimeError(
                "Can't serialize matplotlib figures without mpld3."
            ) from e
        file = io.StringIO()
        mpld3.save_json(obj, file)
        data = json.loads(file.getvalue())
        data = {key: value for key, value in data.items() if key != "id"}
        return freeze_helper(data, tabu | {id(obj)}, level + 1)


try:
    import pymc3  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(obj: pymc3.Model, tabu: Set[int], level: int) -> Hashable:
        raise UnfreezableTypeError(
            "pymc3.Model has been known to cause problems due to its not able to be pickled."
        )
