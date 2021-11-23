from __future__ import annotations

import builtins
import dis
import functools
import inspect
import logging
import textwrap
import types
from typing import Any, Callable, Set, Dict, Hashable, List, Optional, Set, Tuple, Type, cast

logger = logging.getLogger("charmonium.freeze")


def freeze(obj: Any) -> Hashable:
    "Injectively, deterministically maps objects to hashable, immutable objects."
    logger.debug("freeze begin")
    ret = freeze_helper(obj, set(), 0)
    logger.debug("freeze end")
    return ret


def freeze_helper(obj: Any, tabu: Set[int], level: int) -> Hashable:
    if level > 50:
        raise ValueError("Maximum recursion")

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            " ".join(
                [
                    level * " ",
                    type(obj).__name__,
                    textwrap.shorten(repr(obj), width=200),
                ]
            )
        )
    if id(obj) in tabu:
        return b"cycle"
    else:
        return freeze_dispatch(obj, tabu, level)


def specializes_pickle(obj: Any) -> bool:
    return any(
        [
            has_callable(obj, "__reduce_ex__"),
            has_callable(obj, "__reduce__"),
        ]
    )


def freeze_pickle(obj: Any, level: int) -> Any:
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
    logger.debug("%s (reduced=%s)", " " * (level + 1), reduced)

    if getnewargs_ex:
        new_args, new_kwargs = getnewargs_ex()
    elif getnewargs:
        new_args, new_kwargs = getnewargs(), {}
    else:
        new_args, new_kwargs = (), {}

    init_args = reduced[1]
    state = reduced[2] if len(reduced) > 2 else getattr(obj, "__dict__", {})
    list_items = list(reduced[3]) if len(reduced) > 3 and reduced[3] else []
    dict_items = list(reduced[4]) if len(reduced) > 4 and reduced[4] else []
    return (
        str(type),
        *((init_args,) if init_args else ()),
        *((state,) if state else ()),
        *((list_items,) if list_items else ()),
        *((dict_items,) if dict_items else ()),
        *((new_args,) if new_args else ()),
        *((new_kwargs,) if new_kwargs else ()),
    )

@functools.singledispatch
def freeze_dispatch(obj: Any, tabu: Set[int], level: int) -> Hashable:
    getfrozenstate = has_callable(obj, "__getfrozenstate__")
    tabu = tabu | {id(obj)}
    if getfrozenstate:
        return freeze_helper(getfrozenstate(), tabu, level + 1)
    if specializes_pickle(obj):
        return freeze_helper(freeze_pickle(obj, level), tabu, level + 1)
    else:
        raise NotImplementedError("not implemented")


@freeze_dispatch.register(type(None))
@freeze_dispatch.register(bytes)
@freeze_dispatch.register(str)
@freeze_dispatch.register(int)
@freeze_dispatch.register(float)
def _(obj: Hashable, tabu: Set[int], level: int) -> Hashable:
    return obj


@freeze_dispatch.register
def _(obj: types.BuiltinFunctionType, _tabu: Set[int], _level: int) -> Hashable:
    return obj.__name__


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
def _(obj: Set[Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    return frozenset(
        freeze_helper(elem, tabu, level + 1) for elem in cast(Set[Any], obj)
    )


@freeze_dispatch.register(dict)
@freeze_dispatch.register(types.MappingProxyType)
def _(obj: dict[Any, Any], tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    # The elements of a dict remember their insertion order, as of Python 3.7.
    # So I will hash this as an ordered collection.
    return tuple(
        (key, freeze_helper(val, tabu, level + 1))
        for key, val in cast(Dict[Any, Any], obj).items()
    )


@freeze_dispatch.register
def _(obj: memoryview, tabu: Set[int], level: int) -> Hashable:
    return freeze_helper(
        obj.tobytes(),
        tabu | {id(obj)},
        level + 1,
    )


@freeze_dispatch.register
def _(obj: types.FunctionType, tabu: Set[int], level: int) -> Hashable:
    tabu = tabu | {id(obj)}
    closure = getclosurevars(obj)
    return (
        freeze_helper(obj.__code__, tabu, level + 1),
        freeze_helper(closure.nonlocals, tabu, level + 1),
        freeze_helper(closure.globals, tabu, level + 1),
    )


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
    return (obj.__name__, getattr(obj, "__version__", None))


@freeze_dispatch.register(type)
def _(obj: Type[Any], tabu: Set[int], level: int) -> Hashable:
    return obj.__qualname__
    # raise NotImplementedError("`freeze` is Not implemented for types")


def has_callable(
    obj: object,
    attr: str,
    default: Optional[Callable[[], Any]] = None,
) -> Optional[Callable[[], Any]]:
    "Returns a callble if attr of obj is a function or bound method."
    func = cast(Optional[Callable[[], Any]], getattr(obj, attr, default))
    if all(
        [
            func,
            callable(func),
            (not isinstance(func, types.MethodType) or hasattr(func, "__self__")),
        ]
    ):
        return func
    else:
        return None


def getclosurevars(func: types.FunctionType) -> inspect.ClosureVars:
    """A clone of inspect.getclosurevars that is robust to [this bug][1]

    [1]: https://stackoverflow.com/a/61964607/1078199"""
    nonlocal_vars = {
        var: cell.cell_contents
        for var, cell in zip(func.__code__.co_freevars, func.__closure__ or [])
    }

    global_names = set()
    local_varnames = set(func.__code__.co_varnames)
    for instruction in dis.get_instructions(func):
        if instruction.opname in {
            "LOAD_GLOBAL",
            "STORE_GLOBAL",
            "LOAD_DEREF",
            "STORE_DEREF",
        }:
            name = instruction.argval
            if name not in local_varnames:
                global_names.add(name)

    # Global and builtin references are named in co_names and resolved
    # by looking them up in __globals__ or __builtins__
    global_ns = func.__globals__
    builtin_ns = global_ns.get("__builtins__", builtins.__dict__)
    if inspect.ismodule(builtin_ns):
        builtin_ns = builtin_ns.__dict__
    global_vars = {}
    builtin_vars = {}
    unbound_names = set()
    for name in global_names:
        if name in ("None", "True", "False"):
            # Because these used to be builtins instead of keywords, they
            # may still show up as name references. We ignore them.
            continue
        try:
            global_vars[name] = global_ns[name]
        except KeyError:
            try:
                builtin_vars[name] = builtin_ns[name]
            except KeyError:
                unbound_names.add(name)

    return inspect.ClosureVars(
        nonlocal_vars,
        global_vars,
        builtin_vars,
        unbound_names,
    )
