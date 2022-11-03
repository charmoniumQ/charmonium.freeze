from __future__ import annotations

import collections
import copyreg
import functools
import logging
import re
import textwrap
import types
from pathlib import Path
from typing import Any, Callable, Hashable, Mapping, Optional, Sequence, cast

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
    ignore_globals = {
        # tempdir caches the name of the temporary directory on this platorm.
        ("tempfile", "tempdir"),
        # thread status variables don't directly affect computation.
        ("threading", "_active"),
        ("threading", "_limbo"),
        ("re", "_cache"),
        ("charmonium.freeze.lib", "memo"),
        ("sys", "modules"),
        ("sys", "path"),
        ("linecache", "cache"),
        ("inspect", "_filesbymodname"),
        ("inspect", "modulesbyfile"),
        ("sre_compile", "compile"),
        ("os", "environ"),
    }

    # Put ``(function.__module__, function.__name__, nonlocal_name)`` of
    # nonlocal variables which never change or whose changes do not affect the
    # result computation here, (e.g. caches). This will not attempt to freeze
    # their state. Note that the module and name may be different than the
    # identifier you use to import the function. Use ``function.__module__`` and
    # ``function.__name__`` to be sure.
    ignore_nonlocals = {
        # Special case for functools.single_dispatch: We need to ignore the
        # following non-locals, as their mutation do not affect the actual
        # computation.
        ("functools", "dispatch", "cache_token"),
        ("functools", "dispatch", "dispatch_cache"),
    }

    # Put paths to source code that whose source code never changes or those
    # changes do not affect the result computation. I will still recurse into
    # the closure of these functions, just not its source code though.
    ignore_files = {Path(functools.__file__).parent}

    # Whether to assume that all code is constant
    ignore_all_code = False

    # Put ``(object.__module__, object.__class__.__name__, attribute)`` of
    # object attributes which never change or whose changes do not affect the
    # result computation here (e.g. cached attributes). This will not attempt to
    # freeze their state. Note that the module may be different than the name
    # you import it as. Use ``object.__module__`` to be sure.
    ignore_attributes = {
        ("pandas.core.internals.blocks", "Block", "_cache"),
    }

    # Put ``(object.__module__, object.__class__.__name__)`` of objects which do
    # not affect the result computation here (e.g. caches, locks, and
    # threads). Use ``object.__module__`` and ``object.__class__.__name__`` to
    # be sure.
    ignore_objects_by_class = {
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
        ("threading", "Thread"),
        ("threading", "Event"),
        ("threading", "_DummyThread"),
        ("threading", "Condition"),
        ("typing", "Generic"),
        ("re", "RegexFlag"),
        # see https://github.com/python/cpython/issues/92049
        ("sre_constants", "_NamedIntConstant"),
        # TODO: Remove these when we have caching
        # They are purely performance (not correctness)
        ("pandas.core.dtypes.base", "Registry"),
    }

    # Put ``id(object)`` of objects which do not affect the result computation
    # here, especially those which mutate or are not picklable. Prefer to use
    # ``config.ignore_objects_by_class`` if applicable.
    ignore_objects_by_id: set[int] = set()

    # Whether to ignore all classes
    ignore_all_classes = False

    # Put ``(class.__module__, class.__name__)`` of classes whose source code
    # and class attributes never change or those changes do not affect the
    # result computation.
    ignore_classes = {
        # TODO[research]: Remove these when we have caching
        # They are purely performance (not correctness)
        ("pathlib", "PurePath"),
        ("builtins", None),
        ("ABC", None),
        ("ABCMeta", None),
        ("_operator", None),
        ("numpy", "ndarray"),
        ("pandas.core.frame", "DataFrame"),
        ("pandas.core.series", "Series"),
        ("pandas.core.indexes.base", "Index"),
        ("matplotlib.figure", "Figure"),
        ("tqdm.std", "tqdm"),
        ("re", "RegexFlag"),
        ("typing", "Generic"),
    }

    # Put ``(function.__module__, function.__name__)`` of functions whose source
    # code and class attributes never change or those changes are not relevant
    # to the resulting computation.
    ignore_functions: set[tuple[str, str]] = set()

    ignore_extensions = True

    ignore_dict_order = False

    log_width = 250


config = Config()


def freeze(obj: Any) -> Hashable:
    "Injectively, deterministically maps objects to hashable, immutable objects."
    logger.debug("freeze begin %r", obj)
    is_mutable = Ref(True)
    ret = _freeze(obj, {}, 0, 0)[0]
    logger.debug("freeze end")
    return ret


printable_types = (
    type(None),
    bytes,
    str,
    int,
    float,
    complex,
    bytearray,
    memoryview,
)

untabuable_types = (
    type(None),
    int,
    float,
    complex,
    type(...),
)

permanent_types = (
    types.ModuleType,
    types.FunctionType,
    types.CodeType,
    type,
)

memo: dict[int, Hashable] = {}


def _freeze(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    # Check recursion limit
    if config.recursion_limit is not None and depth > config.recursion_limit:
        raise FreezeRecursionError(f"Maximum recursion depth {config.recursion_limit}")

    # Write log
    indent = depth * " "
    if logger.isEnabledFor(logging.DEBUG):
        if isinstance(obj, printable_types):
            logger.debug(
                "%s %s",
                indent,
                textwrap.shorten(repr(obj), width=config.log_width),
            )
        else:
            target = freeze_dispatch.dispatch(type(obj))
            logger.debug(
                "%s %s %s",
                indent,
                type(obj).__name__,
                textwrap.shorten(repr(obj), width=config.log_width),
            )

    # Check objects ignore by id
    if id(obj) in config.ignore_objects_by_id:
        logger.debug("%s ignoring object because of id %d", indent, id(obj))
        return b"ignored by id", True, None

    # Check objects ignore by class
    type_pair = (obj.__class__.__module__, obj.__class__.__name__)
    if type_pair in config.ignore_objects_by_class:
        logger.debug("%s ignoring object because of class %s", " " * depth, type_pair)
        return type_pair, True, None

    # Check memo
    if id(obj) in memo:
        logger.debug("%s memo hit for %d", indent, id(obj))
        cached_result = memo[id(obj)]
        return cached_result, True, None

    # Check tabu
    if id(obj) in tabu:
        depth2, index2 = tabu[id(obj)]
        obj_str = re.sub("0x[a-f0-9]*", "", str(obj))
        logger.debug(
            "%s tabu hit for %d: %d %d %s",
            indent,
            id(obj),
            depth - depth2,
            index2,
            obj_str,
        )
        return (
            (
                b"cycle",
                obj_str,
                depth - depth2,
            ),
            True,
            None,
        )

    # Ok, no more tricks; actually do the work.
    if not isinstance(obj, untabuable_types):
        tabu[id(obj)] = (depth, index)
    ret, is_immutable, ref_depth = freeze_dispatch(obj, tabu, depth + 1, 0)
    if not isinstance(obj, untabuable_types):
        del tabu[id(obj)]

    # TODO: Look at ref_depth here.
    # Suppose obj1 -> obj2, obj2 -> obj1 and obj1prime -> obj2.
    # freeze(obj1)      = [("data", obj1     .data), ("children", [("data", obj2.data, ("children", [("cycle", 1, 0)]))])]
    # freeze(obj2)      = [("data", obj1     .data), ("children", [("data", obj2.data, ("children", [("cycle", 1, 0)]))])]
    # freeze(obj1prime) = [("data", obj1prime.data), ("children", [("data", obj2.data, ("children", [("cycle", 1, 0)]))])]
    # Note that freeze(obj2) is invoked by freeze(obj1), and freeze(obj1) is cached.
    # Suppose the program evolves and
    # Suppose obj1 -> obj2, obj2 -> obj1prime and obj1prime -> obj2.
    # obj2 should have a different hash, but if we call `freeze(obj1prime)` first, none of the hashes change.

    # lambdas _would_ be included, because FunctionType is a permanant_type, so exclude them manually.
    if (
        is_immutable
        and isinstance(obj, permanent_types)
        and not isinstance(obj, types.LambdaType)
    ):
        memo[id(obj)] = ret
    return ret, is_immutable, ref_depth


@functools.singledispatch
def freeze_dispatch(
    obj: Any, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool, Optional[int]]:
    raise NotImplementedError


def min_with_none_inf(x: Optional[int], y: Optional[int]) -> Optional[int]:
    """min of x and y, where None represents positive infinity."""
    if x is None:
        return y
    elif y is None:
        return x
    else:
        return min(x, y)


def freeze_sequence(
    obj: Sequence[Any],
    obj_is_immutable: bool,
    order_matters: bool,
    tabu: dict[int, tuple[int, int]],
    depth: int,
    index: int,
) -> tuple[Hashable, bool, Optional[int]]:
    all_is_immutable = obj_is_immutable
    all_min_ref = None
    frozen_elems: list[Any] = [None] * len(obj)
    for index, elem in enumerate(obj):
        frozen_elem, is_immutable, min_ref = _freeze(elem, tabu, depth, index)
        frozen_elems[index] = frozen_elem
        all_is_immutable = all_is_immutable and is_immutable
        all_min_ref = min_with_none_inf(all_min_ref, min_ref)
    ret = cast(
        Hashable, tuple(frozen_elems) if order_matters else frozenset(frozen_elems)
    )
    return ret, all_is_immutable, all_min_ref


un_reassignable_types = (type, types.FunctionType, types.ModuleType)


def freeze_attrs(
    obj: Mapping[str, Any],
    obj_is_immutable: bool,
    tabu: dict[int, tuple[int, int]],
    depth: int,
    index: int,
) -> tuple[Hashable, bool, Optional[int]]:
    all_min_ref = None
    all_is_immutable = obj_is_immutable
    frozen_items: list[tuple[str, Any]] = [("", None)] * len(obj)
    # sorted so we iterate over the members in a consistent order.
    for index, (key, val) in enumerate(sorted(obj.items())):
        logger.debug("%s %s", " " * depth, key)
        frozen_val, _, min_ref = _freeze(val, tabu, depth, index)
        frozen_items[index] = (key, frozen_val)
        is_immutable = isinstance(val, un_reassignable_types)
        if min_ref is not None:
            all_min_ref = min_with_none_inf(min_ref, all_min_ref)
        all_is_immutable = all_is_immutable and is_immutable
    return tuple(frozen_items), all_is_immutable, all_min_ref


def combine_frozen(
    t0: tuple[Hashable, bool, Optional[int]], t1: tuple[Hashable, bool, Optional[int]]
) -> tuple[tuple[Hashable, ...], bool, Optional[int]]:
    return (
        (t0[0], t1[0]),
        t0[1] and t1[1],
        min_with_none_inf(t0[2], t1[2]),
    )
