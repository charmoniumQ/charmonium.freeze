from __future__ import annotations

import functools
import logging
import re
import textwrap
import types
from typing import Any, Collection, Dict, Hashable, List, Mapping, Optional, Tuple, cast

from .config import Config, global_config
from .util import circular_bit_shift, int_to_bytes, min_with_none_inf

logger = logging.getLogger("charmonium.freeze")


class FreezeError(Exception):
    pass


class UnfreezableTypeError(FreezeError, NotImplementedError):
    pass


class FreezeRecursionError(FreezeError):
    pass


def freeze(obj: Any, config: Optional[Config] = None) -> Hashable:
    "Injectively, deterministically maps objects to hashable, immutable objects."
    logger.debug("freeze begin %r", obj)
    if config is None:
        config = global_config
    ret = _freeze(obj, config, {}, 0, 0)[0]
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


def _freeze(
    obj: Any, config: Config, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    # Check recursion limit
    if config.recursion_limit is not None and depth > config.recursion_limit:
        raise FreezeRecursionError(
            f"Maximum recursion depth {config.recursion_limit}. "
            "See <https://github.com/charmoniumQ/charmonium.freeze#debugging> for debugging help"
        )

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
            logger.debug(
                "%s %s %s",
                indent,
                type(obj).__name__,
                textwrap.shorten(repr(obj), width=config.log_width),
            )

    # Check objects ignore by id
    if id(obj) in config.ignore_objects_by_id:
        logger.debug("%s ignoring object because of id %d", indent, id(obj))
        if config.use_hash:
            return 0, True, None
        return b"ignored by id", True, None

    # Check objects ignore by class
    type_pair = (obj.__class__.__module__, obj.__class__.__name__)
    if type_pair in config.ignore_objects_by_class:
        logger.debug("%s ignoring object because of class %s", " " * depth, type_pair)
        if config.use_hash:
            return _freeze(type_pair, config, tabu, depth + 1, 0)
        return type_pair, True, None

    # Check memo
    if id(obj) in config.memo:
        logger.debug("%s memo hit for %d", indent, id(obj))
        cached_result = config.memo[id(obj)]
        return cached_result, True, None

    # Check tabu
    ret: Hashable
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
        if config.use_hash:
            ret = config.hasher(obj_str.encode()) ^ (depth - depth2)
        else:
            ret = (b"cycle", obj_str, depth - depth2)
        return (
            ret,
            True,
            None,
        )

    # Ok, no more tricks; actually do the work.
    if not isinstance(obj, untabuable_types):
        tabu[id(obj)] = (depth, index)
    ret, is_immutable, ref_depth = freeze_dispatch(obj, config, tabu, depth + 1, 0)
    if not isinstance(obj, untabuable_types):
        del tabu[id(obj)]

    # TODO[1]: Look at ref_depth here.
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
        config.memo[id(obj)] = ret

    if logger.isEnabledFor(logging.DEBUG) and config.use_hash:
        logger.debug("%s -> %s", indent, ret)

    return ret, is_immutable, ref_depth


@functools.singledispatch
def freeze_dispatch(
    obj: Any,
    _config: Config,
    _tabu: dict[int, Tuple[int, int]],
    _depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    raise UnfreezableTypeError(
        f"charmonium.freeze is not implemented for {type(obj).__name__}."
        "See <https://github.com/charmoniumQ/charmonium.time_block/blob/master/README.rst> for how to add a new type."
    )


def freeze_sequence(
    obj: Collection[Any],
    is_immutable: bool,
    order_matters: bool,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    """Freeze a sequence by freezing each element.

    is_immutable: pass True if the container you are seeking to
       freeze should be considered "immutable", which is that it will
       not change during the program's execution (e.g., tuple). This
       determiniation permits caching its hash over the lifetime of
       the process. This function will still check that each element
       in the tuple is also immutable before declaring the result
       immutable (e.g., ([]) is not immutable).

    order_matters: pass True if the object's order matters (e.g., for [] but not for set()).

    """
    all_is_immutable = is_immutable
    all_min_ref = None
    ret: Hashable
    if config.use_hash:
        ret = 0
        for index, elem in enumerate(obj):
            frozen_elem, is_immutable, min_ref = _freeze(
                elem, config, tabu, depth, index
            )
            if order_matters:
                ret = config.hasher(int_to_bytes(ret) + int_to_bytes(cast(int, frozen_elem)))
                # ret ^= circular_bit_shift(cast(int, frozen_elem), index, config.hash_length)
            else:
                ret ^= cast(int, frozen_elem)
            all_is_immutable = all_is_immutable and is_immutable
            all_min_ref = min_with_none_inf(all_min_ref, min_ref)
    else:
        frozen_elems: List[Any] = [None] * len(obj)
        for index, elem in enumerate(obj):
            frozen_elem, is_immutable, min_ref = _freeze(
                elem, config, tabu, depth, index
            )
            frozen_elems[index] = frozen_elem
            all_is_immutable = all_is_immutable and is_immutable
            all_min_ref = min_with_none_inf(all_min_ref, min_ref)
        ret = (
            cast(Hashable, tuple(frozen_elems))
            if order_matters
            else frozenset(frozen_elems)
        )
    return ret, all_is_immutable, all_min_ref


un_reassignable_types = (type, types.FunctionType, types.ModuleType)


def freeze_attrs(
    obj: Mapping[str, Any],
    is_immutable: bool,
    write_attrs: bool,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    """Freeze an Mapping[str, Any], by freezing each element.

    is_immutable: See the same argument in freeze_sequence.

    write_attrs: Set to True to write the attributes in the frozen
        result. Otherwise, we can assume that other objects will have
        the same attribute keys. E.g., if freeze_functions always
        freezes an object like {"code": <code>, "name": <name>}, then
        we don't need to write "code" and "name".

    """
    all_min_ref = None
    all_is_immutable = is_immutable
    ret: Hashable
    if config.use_hash:
        ret = 0
        for index, (key, val) in enumerate(obj.items()):
            if write_attrs:
                ret ^= config.hasher(key.encode())
            frozen_val, is_immutable, min_ref = _freeze(val, config, tabu, depth, index)
            ret ^= cast(int, frozen_val)
            if min_ref is not None:
                all_min_ref = min_with_none_inf(min_ref, all_min_ref)
            all_is_immutable = all_is_immutable and is_immutable
    else:
        frozen_items: List[Any] = [None] * len(obj)
        # sorted so we iterate over the members in a consistent order.
        for index, (key, val) in enumerate(sorted(obj.items())):
            frozen_val, is_immutable, min_ref = _freeze(val, config, tabu, depth, index)
            frozen_items[index] = (key, frozen_val) if write_attrs else frozen_val
            if min_ref is not None:
                all_min_ref = min_with_none_inf(min_ref, all_min_ref)
            all_is_immutable = all_is_immutable and is_immutable
        ret = tuple(frozen_items)
    return ret, all_is_immutable, all_min_ref


def combine_frozen(
    t0: Tuple[Hashable, bool, Optional[int]],
    t1: Tuple[Hashable, bool, Optional[int]],
    config: Config,
) -> Tuple[Hashable, bool, Optional[int]]:
    ret: Hashable
    if config.use_hash:
        ret = cast(int, t0[0]) ^ circular_bit_shift(
            cast(int, t1[0]), 1, config.hash_length
        )
    else:
        ret = (t0[0], t1[0])
    return (
        ret,
        t0[1] and t1[1],
        min_with_none_inf(t0[2], t1[2]),
    )
