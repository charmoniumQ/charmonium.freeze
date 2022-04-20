from __future__ import annotations

import copyreg
import functools
import io
import json
import logging
import re
import sys
import textwrap
import types
from pathlib import Path
from typing import Any, Callable, Dict, Hashable, List, Set, Tuple, Type, cast

from .util import getclosurevars, has_callable, sort_dict, specializes_pickle

logger = logging.getLogger("charmonium.freeze")


# TODO: constant is a bad name
class Config:
    recursion_limit = 50

    # Put global variables which do not affect the result computation here.
    # Especially those which mutate without affecting the computation.
    ignore_globals = {
        ("tempfile", "tempdir"),
        ("tempfile", "_name_sequence"),
        ("threading", "_active"),
        ("threading", "_limbo"),
    }

    # Put paths to source code that where we can assume that source code is constant.
    # We will still track its statefulness though.
    constant_files = {
        Path(io.__file__).parent
    }

    # Put objects which do not affect the result computation here.
    # Especially those which are non-picklable or which will mutate (without affecting the computation).
    constant_objects = {
        ("builtins", "_abc_data"),
        ("_abc", "_abc_data"),
        ("_thread", "RLock"),
        ("_thread", "LockType"),
        ("_thread", "lock"),
        ("threading", "local"),
        ("multiprocessing.synchronize", "Lock"),
        ("multiprocessing.synchronize", "RLock"),
        ("builtins", "weakref"),
        ("builtins", "PyCapsule"),
        ("weakref", "WeakKeyDictionary"),
        ("weakref", "WeakValueDictionary"),
        ("weakref", "WeakSet"),
        ("weakref", "KeyedRef"),
        ("weakref", "WeakMethod"),
        ("weakref", "ReferenceType"),
        ("weakref", "ProxyType"),
        ("weakref", "CallableProxyType"),
        ("_weakrefset", "WeakSet"),
        # TODO: Remove these when we have caching
        # THey are purely performance (not correctness)
        ("threading", "Thread"),
        ("threading", "Event"),
        ("threading", "_DummyThread"),
        ("threading", "Condition"),
    }

    constant_classes = {
        ("builtins", None),

        # TODO: Remove these when we have caching
        # THey are purely performance (not correctness)
        ("ABC", None),
        ("ABCMeta", None),
        ("threading", "Event"),
        ("threading", "Condition"),
        ("threading", "RLock"),
        ("threading", "Thread"),
        ("logging", "Logger"),

        # TODO: investigate why naively freezing DataFrame is so long.
        ("pandas.core.frame", "DataFrame"),
        ("pandas.core.internals.managers", "BlockManager"),
        ("pandas.core.indexes.range", "RangeIndex"),
        ("pandas.core.indexes.base", "Index"),
        ("pandas.core.indexes.numeric", "Int64Index"),
        ("matplotlib.figure", "Figure"),
        ("tqdm.std", "tqdm"),
    }

    # TODO: think about this
    constant_functions = {
        ("copyreg", None),
    }


config = Config()

def is_relative_to(path: Path, source: Path) -> bool:
    # Note that `path.relative_to(source)` is >= 3.8 :'(
    return path.parts[:len(source.parts)] == source.parts


def freeze(obj: Any) -> Hashable:
    "Injectively, deterministically maps objects to hashable, immutable objects."
    logger.debug("freeze begin %r", obj)
    ret = _freeze(obj, set(), 1)
    logger.debug("freeze end")
    return ret


class FreezeError(Exception):
    pass


class UnfreezableTypeError(FreezeError):
    pass


class FreezeRecursionError(FreezeError):
    pass


simple_types = (
    type(None),
    bytes,
    str,
    int,
    float,
    complex,
    type(...),
    bytearray,
    memoryview,
)


def _freeze(obj: Any, tabu: Set[int], level: int) -> Hashable:
    if level > config.recursion_limit:
        raise FreezeRecursionError(f"Maximum recursion depth {config.recursion_limit}")

    if logger.isEnabledFor(logging.DEBUG):
        if isinstance(obj, simple_types):
            logger.debug("%s%s", level * " ", textwrap.shorten(repr(obj), width=250))
        else:
            logger.debug(
                "%s%s %s",
                level * " ",
                type(obj).__name__,
                textwrap.shorten(repr(obj), width=250),
            )
    if id(obj) in tabu:
        return b"cycle"
    else:
        return freeze_dispatch(obj, tabu, level)


def freeze_pickle(obj: Any) -> Dict[str, Any]:
    # I wish I didn't support 3.7, so I could use walrus operator
    getnewargs_ex = has_callable(obj, "__getnewargs_ex__")
    getnewargs = has_callable(obj, "__getnewargs__")
    reduce_ex = cast(
        Callable[[int], Tuple[Any, ...]], has_callable(obj, "__reduce_ex__")
    )
    reduce = cast(Callable[[int], Tuple[Any, ...]], has_callable(obj, "__reduce__"))

    try:
        if reduce_ex:
            reduced = reduce_ex(4)
        elif reduce:
            reduced = reduce()
        else:
            raise TypeError(f"{type(obj)} {obj} is not picklable")
    except TypeError as e:
        raise TypeError(f"Consider adding {(obj.__class__.__module__, obj.__class__.__name__)} to config.constant_objects") from e

    data: Dict[str, Any] = {}

    if getnewargs_ex:
        data["new_args"], data["new_kwargs"] = getnewargs_ex()
    elif getnewargs:
        data["new_args"] = getnewargs()

    if isinstance(reduced, str):
        data["str"] = reduced
    else:
        assert isinstance(reduced, tuple)
        assert 2 <= len(reduced) <= 5
        # pylint: disable=comparison-with-callable
        if reduced[0] != getattr(copyreg, "__newobj__", None):
            data["constructor"] = reduced[0]
        data["args"] = reduced[1]
        data["state"] = reduced[2] if len(reduced) > 2 else getattr(obj, "__dict__", {})
        # reduced may only hae two items, or the third one may be None.
        if len(reduced) > 3 and reduced[3]:
            data["list_items"] = list(reduced[3])
        if len(reduced) > 4 and reduced[4]:
            data["dict_items"] = list(reduced[4])

    # Simplify by deleting "false-y" values.
    data = {key: value for key, value in data.items() if value}
    return data


@functools.singledispatch
def freeze_dispatch(obj: Any, tabu: Set[int], level: int) -> Hashable:
    getfrozenstate = has_callable(obj, "__getfrozenstate__")
    tabu = tabu | {id(obj)}
    type_pair = (obj.__class__.__module__, obj.__class__.__name__)
    if type_pair in config.constant_objects:
        return cast(str, type_pair[1])
    if getfrozenstate:
        # getfrozenstate is custom-built for charmonium.freeze
        # It should take precedence.
        return (
            _freeze(type(obj), tabu | {id(obj)}, level + 1),
            _freeze(getfrozenstate(), tabu | {id(obj)}, level + 1),
        )
    if specializes_pickle(obj):
        # Otherwise, we may be able to use the Pickle protocol.
        data = freeze_pickle(obj)
        return _freeze(data, tabu | {id(obj)}, level + 1)
    else:
        # Otherwise, give up.
        raise UnfreezableTypeError("not implemented")


@freeze_dispatch.register(type(None))
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(int)
@freeze_dispatch.register(float)
@freeze_dispatch.register(complex)
@freeze_dispatch.register(type(...))
def _(obj: Hashable, tabu: Set[int], level: int) -> Hashable:
    # Object is already hashable.
    # No work to be done.
    return obj


@freeze_dispatch.register
def _(obj: bytearray, _tabu: Set[int], _level: int) -> Hashable:
    return bytes(obj)


@freeze_dispatch.register(tuple)
@freeze_dispatch.register(list)
def _(obj: List[Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return tuple(_freeze(elem, tabu, level + 1) for elem in cast(List[Any], obj))


@freeze_dispatch.register(set)
@freeze_dispatch.register(frozenset)
def _(obj: Set[Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    # "Python has never made guarantees about this ordering (and it typically varies between 32-bit and 64-bit builds)."
    # -- https://docs.python.org/3.8/reference/datamodel.html#object.__hash__
    return frozenset(_freeze(elem, tabu, level + 1) for elem in cast(Set[Any], obj))


@freeze_dispatch.register(dict)
@freeze_dispatch.register(types.MappingProxyType)
def _(obj: dict[Any, Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    # The elements of a dict remember their insertion order, as of Python 3.7.
    # So I will hash this as an ordered collection.
    return tuple(
        (_freeze(key, tabu, level + 1), _freeze(val, tabu, level + 1))
        for key, val in list(cast(Dict[Any, Any], obj).items())
    )


# pylint: disable=unused-argument
@freeze_dispatch.register
def _(obj: memoryview, tabu: Set[int], level: int) -> Hashable:
    return obj.tobytes()


@freeze_dispatch.register(type)
def _(obj: Type[Any], tabu: Set[int], level: int) -> Hashable:
    type_pair = (obj.__module__, obj.__name__)
    if (type_pair[0], None) in config.constant_classes or type_pair in config.constant_classes:
        return type_pair[1]
    else:
        # TODO: add classes on the __mro__
        attrs = {
            attr_key: attr_val
            for attr_key, attr_val in obj.__dict__.items()
            if not isinstance(attr_val, (types.GetSetDescriptorType, types.MemberDescriptorType, property)) and attr_key != "__module__" and attr_key != "__slotnames__"
            # Some scripts are designed to be either executed or imported.
            # In that case, the __module__ can be either __main__ or a qualified module name.
            # As such, I exclude the name of the module containing the class.
        }
        return (
            type_pair[1],
            _freeze(sort_dict(attrs), tabu | {id(obj)}, level + 1),
        )


@freeze_dispatch.register
def _(obj: types.FunctionType, tabu: Set[int], level: int) -> Hashable:
    type_pair = (obj.__module__, obj.__name__)
    if (type_pair[0], None) in config.constant_functions or type_pair in config.constant_functions:
        return type_pair[1]
    closure = getclosurevars(obj)
    myglobals = {
        var: val
        for var, val in closure.globals.items()
        if (obj.__module__, var) not in config.ignore_globals
    }
    nonlocals = sort_dict(closure.nonlocals)
    # Special case for functools.single_distapch:
    # We need to ignore the following non-locals, as their mutation do not affect the actual computation.
    if obj.__name__ == "dispatch" and obj.__module__ == "functools":
        del nonlocals["cache_token"]
        del nonlocals["dispatch_cache"]
        del nonlocals["registry"]
    data = {
        "code": obj.__code__,
        "closure nonlocals": sort_dict(nonlocals),
        "closure globals": sort_dict(myglobals),
    }
    # Simplify data by removeing empty items.
    data = {key: val for key, val in data.items() if val}
    return _freeze(data, tabu | {id(obj)}, level + 1)


@freeze_dispatch.register
def _(obj: types.GeneratorType, tabu: Set[int], level: int) -> Hashable:
    return _freeze(obj.gi_code, tabu | {id(obj)}, level + 1)

@freeze_dispatch.register
def _(obj: staticmethod, tabu: Set[int], level: int) -> Hashable:
    return _freeze(obj.__func__, tabu, level + 1)

@freeze_dispatch.register
def _(obj: classmethod, tabu: Set[int], level: int) -> Hashable:
    return _freeze(obj.__func__, tabu, level + 1)

@freeze_dispatch.register
def _(obj: types.MethodType, tabu: Set[int], level: int) -> Hashable:
    # Freezing self freezes the instance data and the methods.
    # obj was a method.
    # Therefore obj will be included.
    return _freeze(obj.__self__, tabu | {id(obj)}, level + 1)


@freeze_dispatch.register(types.WrapperDescriptorType)
@freeze_dispatch.register(types.MethodDescriptorType)
@freeze_dispatch.register(types.MethodDescriptorType)
@freeze_dispatch.register(types.ClassMethodDescriptorType)
def _(obj: Any, _tabu: Set[int], _level: int) -> Hashable:
    # Freezing self freezes the instance data and the methods.
    # obj was a method.
    # Therefore obj will be included.
    return obj.__name__

@freeze_dispatch.register
def _(obj: types.BuiltinFunctionType, _tabu: Set[int], _level: int) -> Hashable:
    return obj.__name__


@freeze_dispatch.register
def _(obj: types.CodeType, tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    source_loc = Path(obj.co_filename)
    if any(is_relative_to(source_loc, constant_file) for constant_file in config.constant_files):
        bytecode = "constant"
    else:
        bytecode = _freeze(obj.co_code, tabu, level + 1)
    return (
        ("name", obj.co_name),
        ("varnames", obj.co_varnames),
        ("constants", _freeze(obj.co_consts, tabu, level + 1)),
        ("bytecode", bytecode),
    )


@freeze_dispatch.register
def _(obj: types.ModuleType, tabu: Set[int], level: int) -> Hashable:
    # TODO: Make a comprehensive freeze for module types.
    # attrs = {
    #     attr_name: getattr(obj, attr_name, None)
    #     for attr_name in dir(obj)
    #     if hasattr(obj, attr_name)
    # }
    # return _freeze(sort_dict(attrs), tabu | {id(obj)}, level)
    return obj.__name__


@freeze_dispatch.register
def _(obj: logging.Logger, _tabu: Set[int], _level: int) -> Hashable:
    # The client should be able to change the logger without changing the computation.
    # But the _name_ of the logger specifies where the side-effect goes, so it should matter.
    return obj.name


@freeze_dispatch.register
def _(obj: io.BytesIO, _tabu: Set[int], _level: int) -> Hashable:
    return obj.getvalue()


@freeze_dispatch.register
def _(obj: io.StringIO, _tabu: Set[int], _level: int) -> Hashable:
    return obj.getvalue()


@freeze_dispatch.register
def _(obj: io.TextIOBase, tabu: Set[int], level: int) -> Hashable:
    if hasattr(obj, "buffer"):
        return _freeze(obj.buffer, tabu, level)
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
    return (obj.regs, _freeze(obj.re, tabu, level + 1), obj.string)


try:
    import tqdm  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register(tqdm.tqdm)
    def _(obj: tqdm.tqdm[Any], tabu: Set[int], level: int) -> Hashable:
        # Unfortunately, the tqdm object contains the timestamp of the last ping, which would result in a different state every time.
        return _freeze(obj.iterable, tabu | {id(obj)}, level + 1)


try:
    import matplotlib.figure  # noqa: autoimport
except ImportError:
    pass
else:

    try:
        import mpld3  # noqa: autoimport
    except ImportError:
        has_mpld3 = False
    else:
        has_mpld3 = True

    @freeze_dispatch.register
    def _(obj: matplotlib.figure.Figure, tabu: Set[int], level: int) -> Hashable:
        if not has_mpld3:
            raise RuntimeError("Can't serialize matplotlib figures without mpld3.")
        file = io.StringIO()
        mpld3.save_json(obj, file)
        data = json.loads(file.getvalue())
        data = {key: value for key, value in data.items() if key != "id"}
        return _freeze(data, tabu | {id(obj)}, level + 1)


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


try:
    from pandas.core.internals import Block  # noqa: autoimport
except ImportError:
    pass
else:

    @freeze_dispatch.register
    def _(obj: Block, tabu: Set[int], level: int) -> Hashable:
        data = freeze_pickle(obj)
        if "state" in data:
            data["state"] = {
                key: val for key, val in data["state"].items() if key != "_cache"
            }
            if not data["state"]:
                del data["state"]
        return _freeze(data, tabu | {id(obj)}, level + 1)
