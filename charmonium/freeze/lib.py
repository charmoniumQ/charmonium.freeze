from __future__ import annotations

import copyreg
import functools
import logging
import textwrap

from pathlib import Path
from typing import Any, Callable, Hashable, Mapping, Optional, cast

from .util import Ref, getclosurevars, is_relative_to

logger = logging.getLogger("charmonium.freeze")


class FreezeError(Exception):
    pass


class UnfreezableTypeError(FreezeError):
    pass


class FreezeRecursionError(FreezeError):
    pass


class Config:
    recursion_limit: Optional[int] = 150

    # Put ``(module, global_name)`` of which never change or whose changes do
    # not affect the result computation here (e.g. global caches). This will not
    # attempt to freeze their state.
    ignore_globals: set[tuple[str, str]] = {
        # tempdir caches the name of the temporary directory on this platorm.
        ("tempfile", "tempdir"),
        # thread status variables don't directly affect computation.
        ("threading", "_active"),
        ("threading", "_limbo"),
        ("re", "_cache"),
        ("charmonium.freeze.lib", "memo"),
    }

    # Put ``(function.__module__, function.__name__, nonlocal_name)`` of
    # nonlocal variables which never change or whose changes do not affect the
    # result computation here, (e.g. caches). This will not attempt to freeze
    # their state. Note that the module and name may be different than the
    # identifier you use to import the function. Use ``function.__module__`` and
    # ``function.__name__`` to be sure.
    ignore_nonlocals: set[tuple[str, str, str]] = {
        # Special case for functools.single_dispatch: We need to ignore the
        # following non-locals, as their mutation do not affect the actual
        # computation.
        ("functools", "dispatch", "cache_token"),
        ("functools", "dispatch", "dispatch_cache"),
        ("functools", "dispatch", "registry"),
    }

    # Put paths to source code that whose source code never changes or those
    # changes do not affect the result computation. I will still recurse into
    # the closure of these functions, just not its source code though.
    assume_constant_files: set[Path] = {Path(functools.__file__).parent}

    # Put ``(object.__module__, object.__class__.__name__, attribute)`` of
    # object attributes which never change or whose changes do not affect the
    # result computation here (e.g. cached attributes). This will not attempt to
    # freeze their state. Note that the module may be different than the name
    # you import it as. Use ``object.__module__`` to be sure.
    ignore_attributes: set[tuple[str, str, str]] = {
        ("pandas.core.internals.blocks", "Block", "_cache"),

        # There is some non-determinism in the order of the elements in this dict.
        # Not sure why.
        ("re", "RegexFlag", "_value2member_map_"),
    }

    # Put ``(object.__module__, object.__class__.__name__)`` of objects which do
    # not affect the result computation here (e.g. caches, locks, and
    # threads). Use ``object.__module__`` and ``object.__class__.__name__`` to
    # be sure.
    ignore_objects_by_class: set[tuple[str, str]] = {
        ("builtins", "_abc_data"),
        ("_abc", "_abc_data"),
        ("_thread", "RLock"),
        ("_thread", "LockType"),
        ("_thread", "lock"),
        ("_thread", "_local"),
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

        # see https://github.com/python/cpython/issues/92049
        ("sre_constants", "_NamedIntConstant"),

        # TODO: Remove these when we have caching
        # They are purely performance (not correctness)
        ("threading", "Thread"),
        ("threading", "Event"),
        ("threading", "_DummyThread"),
        ("threading", "Condition"),
    }

    # Put ``id(object)`` of objects which do not affect the result computation
    # here, especially those which mutate or are not picklable. Prefer to use
    # ``config.ignore_objects_by_class`` if applicable.
    ignore_objects_by_id: set[int] = set()

    # Put ``(class.__module__, class.__name__)`` of classes whose source code
    # and class attributes never change or those changes do not affect the
    # result computation.
    ignore_classes: set[tuple[str, Optional[str]]] = {
        # TODO: Remove these when we have caching
        # They are purely performance (not correctness)
        ("builtins", None),
        ("ABC", None),
        ("ABCMeta", None),
        ("_operator", None),
        ("typing", "Generic"),
        ("threading", "Event"),
        ("threading", "Condition"),
        ("threading", "RLock"),
        ("threading", "Thread"),
        ("logging", "Logger"),
        ("pandas.core.frame", "DataFrame"),
        ("pandas.core.internals.managers", "BlockManager"),
        ("pandas.core.indexes.range", "RangeIndex"),
        ("pandas.core.indexes.base", "Index"),
        ("pandas.core.indexes.numeric", "Int64Index"),
        ("matplotlib.figunre", "Figure"),
        ("tqdm.std", "tqdm"),
    }

    # Put ``(function.__module__, function.__name__)`` of functions whose source
    # code and class attributes never change or those changes are not relevant
    # to the resulting computation.
    ignore_functions: set[tuple[str, str]] = set()

    ignore_extensions = True

    log_width = 250


config = Config()


def freeze(obj: Any) -> Hashable:
    "Injectively, deterministically maps objects to hashable, immutable objects."
    logger.debug("freeze begin %r", obj)
    is_mutable = Ref(True)
    ret = _freeze(obj, {}, 0, 0)[0]
    logger.debug("freeze end")
    return ret


simple_types = (
    type(None),
    bytes,
    str,
    int,
    float,
    complex,
    bytearray,
    memoryview,
)


memo: dict[int, Hashable] = {}


def _freeze(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    if config.recursion_limit is not None and depth > config.recursion_limit:
        raise FreezeRecursionError(f"Maximum recursion depth {config.recursion_limit}")

    if logger.isEnabledFor(logging.DEBUG):
        if isinstance(obj, simple_types):
            logger.debug(
                "%s %s",
                depth * " ",
                textwrap.shorten(repr(obj), width=config.log_width),
            )
        else:
            logger.debug(
                "%s %s %s",
                depth * " ",
                type(obj).__name__,
                textwrap.shorten(repr(obj), width=config.log_width),
            )

    cached_result = memo.get(id(obj))
    if id(obj) in config.ignore_objects_by_id:
        return b"ignored by id", True
    if cached_result:
        return cached_result, True
    else:
        result = tabu.get(id(obj))
        if result:
            return (b"cycle", result), True
        else:
            if not isinstance(obj, simple_types):
                tabu[id(obj)] = (depth, index)
            ret, is_immutable = freeze_dispatch(obj, tabu, depth + 1, 0)
            if not isinstance(obj, simple_types):
                # del tabu[id(obj)]
                if is_immutable:
                    memo[id(obj)] = ret
                    # TODO: Don't put ret in the cache if ret contains a cycle which refers to a depth less than this frame.
            return ret, is_immutable


def immutable_if_children_are(
    freeze_ret: tuple[Hashable, bool], is_immutable: Ref[bool]
) -> Hashable:
    if not freeze_ret[1]:
        is_immutable(False)
    return freeze_ret[0]


@functools.singledispatch
def freeze_dispatch(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    type_pair = (obj.__class__.__module__, obj.__class__.__name__)
    if type_pair in config.ignore_objects_by_class:
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return type_pair, True

    getfrozenstate = getattr(obj, "__getfrozenstate__", None)
    if hasattr(obj, "__getfrozenstate__"):
        # getfrozenstate is custom-built for charmonium.freeze
        # It should take precedence.
        is_immutable = Ref(True)
        ret = (
            immutable_if_children_are(
                _freeze(type(obj), tabu, depth, index + 0), is_immutable
            ),
            immutable_if_children_are(
                _freeze(getfrozenstate(), tabu, depth, index + 0), is_immutable
            ),
        )
        return ret, is_immutable()

    pickle_data = freeze_pickle(obj, tabu, depth, index)
    # Otherwise, we may be able to use the Pickle protocol.
    if pickle_data:
        return pickle_data

    # Otherwise, give up.
    raise UnfreezableTypeError("not implemented")


def freeze_pickle(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    dispatch_table = cast(
        Mapping[type, Callable[[Any], Any]],
        copyreg.dispatch_table,  # type: ignore
    )
    if type(obj) in dispatch_table:
        reduced = dispatch_table[type(obj)](obj)
    else:
        reducer = getattr(obj, "__reduce_ex__", None)
        if reducer:
            reduced = reducer(4)
        else:
            reducer = getattr(obj, "__reduce__", None)
            if reducer:
                reduced = reducer()
            else:
                return None, True

    data: list[Hashable] = []
    if isinstance(reduced, str):
        data.append(reduced)
    elif isinstance(reduced, tuple) and 2 <= len(reduced) <= 5:
        constructor = _freeze(reduced[0], tabu, depth, index)[0]
        args = tuple(_freeze(arg, tabu, depth, index)[0] for arg in reduced[1])
        data.append((constructor, *args))
        # reduced may only have two items, or the third one may be None or empty containers.
        if len(reduced) > 2 and reduced[2]:
            state: Hashable
            if isinstance(reduced[2], dict):
                state = tuple(
                    sorted(
                        (
                            # TODO: Don't freeze var; it's already a string
                            _freeze(var, tabu, depth*2+0, index)[0],
                            _freeze(val, tabu, depth*2+1, index)[0],
                        )
                        for var, val in reduced[2].items()
                        if (obj.__module__, obj.__class__.__name__, var)
                        not in config.ignore_attributes
                    )
                )
            else:
                state = _freeze(reduced[2], tabu, depth, index)[0]
            if state:
                data.append(state)
        if len(reduced) > 3 and reduced[3]:
            list_items = _freeze(list(reduced[3]), tabu, depth, index)[0]
            if list_items:
                data.append(list_items)
        if len(reduced) > 4 and reduced[4]:
            dict_items = _freeze(dict(reduced[4]), tabu, depth, index)[0]
            if dict_items:
                data.append(dict_items)
    else:
        return None, True

    return (b"pickle", *data), False
