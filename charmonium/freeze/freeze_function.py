import types
from pathlib import Path
from typing import Dict, Hashable, Optional, Tuple

from . import util
from .lib import (
    combine_frozen,
    config,
    freeze_attrs,
    freeze_dispatch,
    freeze_sequence,
    logger,
)


@freeze_dispatch.register
def _(
    obj: types.FunctionType,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    type_pair = (obj.__module__, obj.__name__)
    if type_pair in config.ignore_functions:
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return type_pair, True, None
    closure = util.get_closure_attrs(obj)
    ret = freeze_code(obj.__code__, tabu, depth, 0)
    myglobals = {
        ".".join((key, *attr_path)): val
        for key, attr_path, _, val in closure.myglobals
        if (obj.__module__, key) not in config.ignore_globals
        and (not attr_path or (key, attr_path[0]) not in config.ignore_globals)
    }
    if myglobals:
        ret = combine_frozen(ret, freeze_attrs(myglobals, True, tabu, depth, 1))
    nonlocals = {
        ".".join((key, *attr_path)): val
        for key, attr_path, _, val in closure.nonlocals
        if (obj.__module__, key) not in config.ignore_nonlocals
        and (not attr_path or (key, attr_path[0]) not in config.ignore_nonlocals)
    }
    if nonlocals:
        ret = combine_frozen(ret, freeze_attrs(nonlocals, True, tabu, depth, 2))
    return (b"function", *ret[0]), ret[1], ret[2]


@freeze_dispatch.register
def _(
    obj: types.CodeType, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_code(obj, tabu, depth, index)


def freeze_code(
    obj: types.CodeType, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    source_loc = Path(obj.co_filename)
    if config.ignore_all_code or any(
        util.is_relative_to(source_loc, constant_file)
        for constant_file in config.ignore_files
    ):
        return (
            (
                b"builtin code",
                obj.co_name,
            ),
            True,
            None,
        )
    else:
        ret = freeze_sequence(obj.co_consts, True, True, tabu, depth, 1)
        return (b"code", obj.co_name, obj.co_code, ret[0]), ret[1], ret[2]


@freeze_dispatch.register
def _(
    obj: types.FrameType, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_frame(obj, tabu, depth, index)


def freeze_frame(
    obj: types.FrameType, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    ret = combine_frozen(
        freeze_code(obj.f_code, tabu, depth, 0),
        freeze_attrs(obj.f_locals, True, tabu, depth, 1),
    )
    return (b"frame", *ret[0], obj.f_lasti), ret[1], ret[2]


@freeze_dispatch.register
def _(
    obj: types.BuiltinFunctionType,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return ("builtin func", obj.__name__), True, None


@freeze_dispatch.register
def _(
    obj: types.GeneratorType, tabu: Dict[int, Tuple[int, int]], depth: int, index: int
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_frame(obj.gi_frame, tabu, depth, 0)
