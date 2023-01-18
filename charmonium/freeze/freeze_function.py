from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Dict, Hashable, Optional, Tuple, cast

from . import util
from .config import Config
from .lib import combine_frozen, freeze_attrs, freeze_dispatch, freeze_sequence, logger


@freeze_dispatch.register
def _(
    obj: types.FunctionType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    type_pair = (obj.__module__, obj.__name__)
    if type_pair in config.ignore_functions:
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return type_pair, True, None
    closure = util.get_closure_attrs(obj)
    ret = freeze_code(obj.__code__, config, tabu, depth, index)
    myglobals = {
        ".".join((var_name, *attr_path)): val
        for var_name, attr_path, _, val in closure.myglobals
        if (obj.__module__, var_name) not in config.ignore_globals
        and (not attr_path or (var_name, attr_path[0]) not in config.ignore_globals)
    }
    if myglobals:
        ret = combine_frozen(
            ret, freeze_attrs(myglobals, True, True, config, tabu, depth)
        )
    nonlocals = {
        ".".join((var_name, *attr_path)): val
        for var_name, attr_path, _, val in closure.nonlocals
        if (
            (obj.__module__, var_name) not in config.ignore_nonlocals
            and (
                not attr_path
                or (obj.__module__, attr_path[0]) not in config.ignore_nonlocals
            )
        )
    }
    if nonlocals:
        ret = combine_frozen(
            ret, freeze_attrs(nonlocals, True, True, config, tabu, depth)
        )
    return (b"function", *cast(Tuple[Any], ret[0])), ret[1], ret[2]


@freeze_dispatch.register
def _(
    obj: types.CodeType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_code(obj, config, tabu, depth, index)


def freeze_code(
    obj: types.CodeType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    _index: int,
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
        ret = freeze_sequence(obj.co_consts, True, True, config, tabu, depth)
        return (obj.co_name, obj.co_code, ret[0]), ret[1], ret[2]


@freeze_dispatch.register
def _(
    obj: types.FrameType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_frame(obj, config, tabu, depth, index)


def freeze_frame(
    obj: types.FrameType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    ret = combine_frozen(
        freeze_code(obj.f_code, config, tabu, depth, index),
        freeze_attrs(obj.f_locals, True, True, config, tabu, depth),
    )
    return (b"frame", *ret[0], obj.f_lasti), ret[1], ret[2]


@freeze_dispatch.register
def _(
    obj: types.BuiltinFunctionType,
    _config: Config,
    _tabu: Dict[int, Tuple[int, int]],
    _depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return ("builtin func", obj.__name__), True, None


@freeze_dispatch.register(types.GeneratorType)
def _(
    obj: types.GeneratorType[Any, Any, Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_frame(obj.gi_frame, config, tabu, depth, 0)
